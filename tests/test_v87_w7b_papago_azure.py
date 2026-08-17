"""tests/test_v87_w7b_papago_azure.py — v87-W7 회수: Papago(NCP)·Azure 체인 배선.

오너 확정 env명으로 배선됐는지 못박음(공식 엔드포인트만):
- Papago: NCP_PAPAGO_CLIENT_ID + NCP_PAPAGO_CLIENT_SECRET → papago.apigw.ntruss.com
- Azure : AZURE_TRANSLATOR_KEY (+ AZURE_TRANSLATOR_REGION) → api.cognitive.microsofttranslator.com
- 체인 순서 = 무료(mymemory) → papago → deepl → azure → openai(최후).
"""
from __future__ import annotations

import pytest

from src.seller_console.ai.translator import AITranslator

_ENVS = ["OPENAI_API_KEY", "DEEPL_API_KEY", "NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET",
         "AZURE_TRANSLATOR_KEY", "AZURE_TRANSLATOR_REGION", "TRANSLATE_PROVIDER_CHAIN",
         "TRANSLATE_DISABLE_MYMEMORY", "ADAPTER_DRY_RUN"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in _ENVS:
        monkeypatch.delenv(k, raising=False)


def test_chain_order_free_papago_deepl_azure_openai(monkeypatch):
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "id")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "sec")
    monkeypatch.setenv("DEEPL_API_KEY", "d:fx")
    monkeypatch.setenv("AZURE_TRANSLATOR_KEY", "az")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert AITranslator()._provider_chain() == ["mymemory", "papago", "deepl", "azure", "openai"]


def test_papago_needs_both_ncp_keys(monkeypatch):
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "id")   # SECRET 없음 → papago 제외
    assert "papago" not in AITranslator()._provider_chain()
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "sec")
    assert "papago" in AITranslator()._provider_chain()


def test_papago_calls_official_ncp_endpoint(monkeypatch):
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "id")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "sec")
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "papago")   # papago만 격리
    import requests
    seen = {}

    def _post(url, headers=None, data=None, timeout=None, **k):
        seen["url"] = url
        seen["headers"] = headers
        class R:
            def raise_for_status(self): pass
            def json(self): return {"message": {"result": {"translatedText": "쓰무기"}}}
        return R()
    monkeypatch.setattr(requests, "post", _post)
    res = AITranslator().translate_product({"title": "TSUMUGI 紬", "description": "日本語"})
    assert res["provider"] == "papago" and res["title_ko"] == "쓰무기"
    assert seen["url"] == "https://papago.apigw.ntruss.com/nmt/v1/translation"   # 공식 엔드포인트
    assert seen["headers"]["x-ncp-apigw-api-key-id"] == "id"                     # 확정 env명 → 헤더
    assert seen["headers"]["x-ncp-apigw-api-key"] == "sec"


def test_azure_calls_official_endpoint_with_region(monkeypatch):
    monkeypatch.setenv("AZURE_TRANSLATOR_KEY", "az-key")
    monkeypatch.setenv("AZURE_TRANSLATOR_REGION", "koreacentral")
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "azure")
    import requests
    seen = {}

    def _post(url, params=None, headers=None, json=None, timeout=None, **k):
        seen["url"] = url
        seen["params"] = params
        seen["headers"] = headers
        class R:
            def raise_for_status(self): pass
            def json(self): return [{"translations": [{"text": "쓰무기"}]},
                                    {"translations": [{"text": "상세"}]}]
        return R()
    monkeypatch.setattr(requests, "post", _post)
    res = AITranslator().translate_product({"title": "TSUMUGI 紬", "description": "日本語"})
    assert res["provider"] == "azure" and res["title_ko"] == "쓰무기" and res["description_ko"] == "상세"
    assert seen["url"] == "https://api.cognitive.microsofttranslator.com/translate"   # 공식
    assert seen["params"]["to"] == "ko"
    assert seen["headers"]["Ocp-Apim-Subscription-Key"] == "az-key"                   # 확정 env명
    assert seen["headers"]["Ocp-Apim-Subscription-Region"] == "koreacentral"


def test_failure_message_names_provider(monkeypatch):
    # v87-W7 회수: 체인 전부 실패 시 실패 메시지에 **어느 단이 죽었는지** 프로바이더명 명시.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "openai")
    monkeypatch.setenv("OPENAI_RETRY_BACKOFF_SEC", "0")   # v87-W8: 429 재시도 백오프 없이(테스트 지연 방지)
    import requests

    class _R429:
        status_code = 429
    def _boom(*a, **k):
        e = requests.HTTPError("Rate limit reached for gpt-4o-mini")   # 속도 제한(결제 아님)
        e.response = _R429()
        raise e
    monkeypatch.setattr(requests, "post", _boom)
    res = AITranslator().translate_product({"title": "x", "description": "y"})
    assert res["translate_error"].startswith("OpenAI:")            # 프로바이더명 접두(어느 단이 죽었는지)
    assert "속도" in res["translate_error"] and "결제 아님" in res["translate_error"]   # v87-W7a: 결제로 오귀인 금지


def test_provider_label_maps():
    from src.seller_console.ai.translator import provider_label
    assert provider_label("openai-fallback") == "OpenAI"
    assert provider_label("papago") == "Papago"
    assert provider_label("azure-fallback") == "Azure"


def test_papago_failure_falls_over_to_azure(monkeypatch):
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "id")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "sec")
    monkeypatch.setenv("AZURE_TRANSLATOR_KEY", "az")
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "papago,azure")
    import requests
    calls = {"n": 0}

    def _post(url, **k):
        calls["n"] += 1
        class R:
            def raise_for_status(self):
                if "ntruss" in url:
                    raise RuntimeError("429 quota")     # papago 실패
            def json(self): return [{"translations": [{"text": "쓰무기"}]}, {"translations": [{"text": "상세"}]}]
        return R()
    monkeypatch.setattr(requests, "post", _post)
    res = AITranslator().translate_product({"title": "TSUMUGI 紬", "description": "日本語"})
    assert res["provider"] == "azure"                    # papago 실패 → azure 성공
    prov = [a["provider"] for a in res["attempts"]]
    assert prov == ["papago", "azure"]
    assert res["attempts"][0]["ok"] is False and res["attempts"][1]["ok"] is True
