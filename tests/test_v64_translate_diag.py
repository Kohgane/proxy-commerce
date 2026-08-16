"""tests/test_v64_translate_diag.py — v64 STEP6: 번역 경로 진단.

'한국어 번역' 실패 시 원인(키/모델/타임아웃/쿼터/네트워크)을 특정해 표기(무음·오귀인 금지).
키가 설정돼 있는데 실패하면 '키 미설정'으로 오귀인하지 않고 실제 원인을 토스트로.
"""
from __future__ import annotations

import requests

from src.seller_console.ai.translator import classify_translate_error


class _FakeResp:
    def __init__(self, status):
        self.status_code = status


def _exc_with_status(status, msg=""):
    e = requests.HTTPError(msg or f"HTTP {status}")
    e.response = _FakeResp(status)
    return e


def test_classify_auth():
    assert "키" in classify_translate_error(_exc_with_status(401))
    assert "키" in classify_translate_error(_exc_with_status(403))
    assert "키" in classify_translate_error(Exception("invalid_api_key provided"))


def test_classify_quota():
    # v87-W7a 재개정: 429를 요청속도(rate_limit) vs 크레딧소진(insufficient_quota)으로 분리.
    #   순수 429(속도 제한) → 결제 아님(오너가 OpenAI 지갑 뒤지지 않게).
    rl = classify_translate_error(_exc_with_status(429, "rate limit reached"))
    assert "속도" in rl and "결제 아님" in rl
    q = classify_translate_error(Exception("insufficient_quota"))
    assert "크레딧" in q or "결제" in q


def test_classify_model():
    assert "모델" in classify_translate_error(_exc_with_status(404, "model gpt-x does not exist"))
    assert "모델" in classify_translate_error(Exception("The model `gpt-x` does not exist"))


def test_classify_timeout_network():
    assert "지연" in classify_translate_error(Exception("Read timed out"))
    assert "연결" in classify_translate_error(Exception("Connection refused"))


def test_classify_generic():
    # 분류 안 되는 예외도 '실패했어요'로(무음 금지) — 절대 빈 문자열 아님.
    r = classify_translate_error(Exception("weird"))
    assert r and "실패" in r


def test_openai_fallback_carries_error(monkeypatch):
    # 키가 있고 호출이 실패하면 translate_product 결과에 error(원인)가 실린다.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-xxxxx")
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "openai")   # v87-W7: openai만 격리(체인 무료 프로바이더 네트워크 회피)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import src.seller_console.ai.translator as T

    def _boom(*a, **k):
        raise _exc_with_status(401, "unauthorized")

    monkeypatch.setattr(T.requests if hasattr(T, "requests") else requests, "post", _boom, raising=False)
    # requests는 함수 내부 import(_req)라 requests.post를 패치.
    monkeypatch.setattr(requests, "post", _boom)
    tr = T.AITranslator()
    assert tr.provider == "openai"
    out = tr.translate_product({"title": "Wireless Earbuds", "description": "desc"})
    assert out["provider"] == "openai-fallback"
    assert out.get("error") and "키" in out["error"]      # 원인 전달(무음 아님)
