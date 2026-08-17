"""tests/test_v87_w8_ja_state.py — v87-W8 item2·3·4: 상태 잔존·ja 품질·429 재시도.

- item2: 재번역 성공 시 옛 실패 배너·목록 뱃지 근거(translate_error) 즉시 소거 + translated=True.
- item3: 소스 언어별 체인(ja=papago/deepl 선행, mymemory 최후) + 라쿠텐 상용구 번역 전 제거.
- item4: OpenAI 429는 짧은 백오프 1회 재시도 후 폴백.
"""
from __future__ import annotations

import json

import pytest

from src.seller_console.ai.translator import (
    AITranslator, strip_market_boilerplate, _post_with_429_retry, _is_rate_limit_exc)


# ── item3: ja 체인 순서 + 상용구 제거 ────────────────────────────────
def test_ja_chain_puts_mymemory_last(monkeypatch):
    for k in ["TRANSLATE_PROVIDER_CHAIN", "TRANSLATE_DISABLE_MYMEMORY"]:
        monkeypatch.delenv(k, raising=False)
    for k in ["NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET", "DEEPL_API_KEY", "AZURE_TRANSLATOR_KEY", "OPENAI_API_KEY"]:
        monkeypatch.setenv(k, "x")
    assert AITranslator()._provider_chain(src_lang="ja") == ["papago", "deepl", "azure", "openai", "mymemory"]
    assert AITranslator()._provider_chain(src_lang="en")[0] == "mymemory"   # 비-ja는 무료 우선 유지


def test_rakuten_boilerplate_stripped_from_title():
    assert strip_market_boilerplate("楽ギフ_包装 あす着対応 TSUMUGI 紬 レコード") == "TSUMUGI 紬 レコード"
    assert "送料無料" not in strip_market_boilerplate("送料無料 ポイント10倍 木製ケース")
    assert "楽ギフ" not in strip_market_boilerplate("楽ギフ_包装 木製ケース")
    # 상품 속성어는 보존 · 전부 상용구면 원문 유지(빈 제목 금지)
    assert strip_market_boilerplate("TSUMUGI 木製ケース") == "TSUMUGI 木製ケース"
    assert strip_market_boilerplate("送料無料 あす着") == "送料無料 あす着"


def test_translate_product_uses_ja_order_and_strips(monkeypatch):
    monkeypatch.delenv("TRANSLATE_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    for k in ["NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET"]:
        monkeypatch.setenv(k, "x")
    import requests
    seen = {"urls": [], "texts": []}

    def _post(url, headers=None, data=None, timeout=None, **k):
        seen["urls"].append(url)
        seen["texts"].append((data or {}).get("text"))
        class R:
            def raise_for_status(self): pass
            def json(self): return {"message": {"result": {"translatedText": "쓰무기 레코드 케이스"}}}
        return R()
    monkeypatch.setattr(requests, "post", _post)
    res = AITranslator().translate_product({"title": "楽ギフ_包装 TSUMUGI レコードケース", "description": "日本語の説明"})
    # ja → papago 선착(mymemory 아님) + 상용구 제거된 제목이 전송됨
    assert res["provider"] == "papago"
    assert "papago" in seen["urls"][0]
    assert "楽ギフ" not in seen["texts"][0] and "TSUMUGI" in seen["texts"][0]   # 첫 post = 제목(상용구 제거됨)


# ── item4: 429 재시도 ────────────────────────────────────────────────
def test_is_rate_limit_detection():
    class E(Exception):
        pass
    e = E("boom"); e.response = type("R", (), {"status_code": 429})()
    assert _is_rate_limit_exc(e)
    assert _is_rate_limit_exc(Exception("Rate limit reached"))
    assert not _is_rate_limit_exc(Exception("insufficient_quota only"))


def test_429_retries_once_then_succeeds(monkeypatch):
    monkeypatch.setenv("OPENAI_RETRY_BACKOFF_SEC", "0")
    import requests
    calls = {"n": 0}

    class R:
        def __init__(self, code): self.status_code = code
        def raise_for_status(self):
            if self.status_code >= 400:
                e = requests.HTTPError("429 rate limit"); e.response = self; raise e
    def _post(url, **k):
        calls["n"] += 1
        return R(429) if calls["n"] == 1 else R(200)
    monkeypatch.setattr(requests, "post", _post)
    r = _post_with_429_retry(requests, "http://x")
    assert calls["n"] == 2 and r.status_code == 200      # 1회 재시도로 성공


# ── item2: 재번역 성공 시 실패 상태 소거 ──────────────────────────────
def test_retranslate_success_clears_stale_error(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    monkeypatch.setattr(V, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    # 옛 수집 시 실패 상태가 박힌 항목
    iid = ch.append(source="extension", url="https://item.rakuten.co.jp/x/9/", title="TSUMUGI 紬",
                    price="1706", currency="JPY", seller_id="u1",
                    extra={"translated": False, "translate_error": "요청 속도 제한(옛 실패)", "translate_requested": True})

    class _T:
        def translate_product(self, s):
            return {"title_ko": "쓰무기", "description_ko": "설명", "provider": "papago", "attempts": [{"provider": "papago", "ok": True}]}
    import src.seller_console.ai.translator as _tr
    monkeypatch.setattr(_tr, "AITranslator", lambda: _T())   # 라우트가 함수 내 import 후 AITranslator()

    from src.order_webhook import app
    with app.test_client() as c:
        r = c.post("/seller/collect/bulk-translate", json={"item_ids": [iid]})
        assert r.get_json()["translated"] >= 1
    row = ch.get(iid, seller_id="u1")
    ex = json.loads(row["extra_json"])
    assert ex.get("translated") is True
    assert "translate_error" not in ex                     # 실패 근거 소거(배너·뱃지 잔존 금지)
    assert ex.get("translation_provider") == "papago"
