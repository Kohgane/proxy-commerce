"""tests/test_v87_w10_stability.py — v87-W10 긴급 안정성: 번역 요청-경로 워커 보호.

근원: 요청 경로 내 동기 번역 체인(프로바이더 순차 + 타임아웃)이 워커를 최악 125초 점유 → 8슬롯
고갈 → 저부하에서도 전면 저속. 수리: 체인 로직 불변(순서·프로바이더 무손대) + 시간 예산 캡(워커
보호). 부분 요청 오류는 JSON(전체 페이지 HTML 중첩 렌더 금지).
"""
from __future__ import annotations

import time

import pytest

from src.seller_console.ai.translator import AITranslator


def test_request_budget_caps_worker_hold(monkeypatch):
    # ja 체인 전 프로바이더가 타임아웃까지 걸려도 워커 점유는 예산(3초)+여유 이내.
    monkeypatch.setenv("TRANSLATE_REQUEST_BUDGET_SEC", "3")
    monkeypatch.delenv("TRANSLATE_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    for k in ["NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET", "DEEPL_API_KEY", "AZURE_TRANSLATOR_KEY", "OPENAI_API_KEY"]:
        monkeypatch.setenv(k, "x")
    import requests

    def _slow_post(url, **k):
        time.sleep(min(k.get("timeout", 10), 10)); raise requests.exceptions.Timeout("t")
    def _slow_get(url, params=None, timeout=None):
        time.sleep(min(timeout or 10, 10)); raise requests.exceptions.Timeout("t")
    monkeypatch.setattr(requests, "post", _slow_post)
    monkeypatch.setattr(requests, "get", _slow_get)
    t0 = time.time()
    res = AITranslator().translate_product({"title": "玉渕 紬", "description": "日本語" * 20})
    el = time.time() - t0
    assert el <= 5.0                                  # 예산 3초 + 여유(단일 프로바이더 클램프) ≤ 5s
    assert res["provider"].endswith("-fallback")      # 전부 실패 → 정직 실패(원문 유지)
    assert res["title_ko"] == "玉渕 紬"                # 원문 보존


def test_later_providers_skipped_after_budget(monkeypatch):
    monkeypatch.setenv("TRANSLATE_REQUEST_BUDGET_SEC", "2")
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "mymemory,papago,openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "a")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "b")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import requests
    calls = {"post": 0}

    def _slow_get(url, params=None, timeout=None):
        time.sleep(min(timeout or 2, 2.2)); raise requests.exceptions.Timeout("t")
    def _post(url, **k):
        calls["post"] += 1; raise AssertionError("budget exhausted — must not call papago/openai")
    monkeypatch.setattr(requests, "get", _slow_get)
    monkeypatch.setattr(requests, "post", _post)
    res = AITranslator().translate_product({"title": "紬", "description": "x"})
    assert calls["post"] == 0                          # mymemory가 예산 소진 → 뒤 프로바이더 미호출
    skipped = [a for a in res["attempts"] if a.get("skipped")]
    assert skipped and "예산 초과" in skipped[0]["error"]


def test_clamp_timeout_bounds():
    tr = AITranslator()
    tr._deadline = time.time() + 3
    assert tr._clamp_timeout(30) <= 3.1               # 남은 예산으로 클램프
    assert tr._clamp_timeout(30) >= 1.0               # 최소 1초
    tr._deadline = None
    assert tr._clamp_timeout(10) == 10.0              # deadline 없으면 원 timeout


def test_normal_translation_not_slowed(monkeypatch):
    # 정상(첫 프로바이더 즉시 성공)은 캡의 영향 없음 — p50 불변.
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "papago")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "a")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "b")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import requests

    def _post(url, **k):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"message": {"result": {"translatedText": "쓰무기"}}}
        return R()
    monkeypatch.setattr(requests, "post", _post)
    t0 = time.time()
    res = AITranslator().translate_product({"title": "紬", "description": "x"})
    assert res["provider"] == "papago" and (time.time() - t0) < 1.0


# ── item3: 부분 요청 오류는 JSON(전체 HTML 금지) ─────────────────────
def test_wants_json_error_for_fetch_and_xhr():
    from src.order_webhook import app, _wants_json_error
    with app.test_request_context("/seller/collect/bulk-translate", headers={"Sec-Fetch-Dest": "empty"}):
        assert _wants_json_error() is True             # fetch()/XHR = empty
    with app.test_request_context("/seller/foo", headers={"X-Requested-With": "XMLHttpRequest"}):
        assert _wants_json_error() is True
    with app.test_request_context("/seller/collect/history", headers={"Sec-Fetch-Dest": "document"}):
        assert _wants_json_error() is False            # 문서 내비게이션 = HTML 페이지 유지


def test_bulk_translate_response_has_deferred_field(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    monkeypatch.setattr(V, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    iid = ch.append(source="extension", url="https://x/1", title="T", price="1", currency="KRW", seller_id="u1", extra={})

    class _T:
        def translate_product(self, s):
            return {"title_ko": "티", "description_ko": "", "provider": "papago", "attempts": []}
    import src.seller_console.ai.translator as _tr
    monkeypatch.setattr(_tr, "AITranslator", lambda: _T())
    from src.order_webhook import app
    with app.test_client() as c:
        j = c.post("/seller/collect/bulk-translate", json={"item_ids": [iid]}).get_json()
    assert "deferred" in j and j["deferred"] == 0      # 빠른 처리 → 지연 0
