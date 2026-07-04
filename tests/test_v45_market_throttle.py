"""tests/test_v45_market_throttle.py — 마켓 API 스로틀 큐(아웃바운드 레이트리밋).

- 마켓별 초당 한도(안전마진): 네이버 1.5/s, 쿠팡 7/s (env 오버라이드).
- 429/5xx → 지수 백오프(1→2→4) 재시도 최대 3회. 최종 실패는 실패(가짜 성공 0).
- rate-limit-remaining 헤더 로깅.
- 벌크 30건: 매 첫 호출 429여도 재시도로 전건 성공, 429 카운트 관측.
"""
from __future__ import annotations

import logging

import pytest

import src.market_throttle as mt


class FakeResp:
    def __init__(self, code, headers=None):
        self.status_code = code
        self.headers = headers or {}


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    mt.reset_stats()
    monkeypatch.setattr(mt.time, "sleep", lambda *_a, **_k: None)   # 백오프/페이싱 즉시
    # 페이싱 지연 제거(테스트 속도) — RPS 매우 높게
    monkeypatch.setenv("MARKET_RPS_NAVER", "100000")
    monkeypatch.setenv("MARKET_RPS_COUPANG", "100000")
    monkeypatch.setenv("MARKET_RPS_ELEVENST", "100000")
    yield
    mt.reset_stats()


def test_rps_defaults_and_override(monkeypatch):
    monkeypatch.delenv("MARKET_RPS_NAVER", raising=False)
    monkeypatch.delenv("MARKET_RPS_COUPANG", raising=False)
    assert mt.rps_for("naver") == 1.5          # 앱ID당 2/s → 안전 1.5
    assert mt.rps_for("smartstore") == 1.5
    assert mt.rps_for("coupang") == 7.0        # vendorId당 10/s → 안전 7
    monkeypatch.setenv("MARKET_RPS_COUPANG", "9")
    assert mt.rps_for("coupang") == 9.0


def test_retry_429_then_success():
    seq = [FakeResp(429), FakeResp(200)]
    resp = mt.throttled_request(lambda: seq.pop(0), market="coupang", key="v1")
    assert resp.status_code == 200
    st = mt.get_stats()["coupang:v1"]
    assert st["429"] == 1 and st["retries"] >= 1


def test_persistent_429_is_honest_failure():
    resp = mt.throttled_request(lambda: FakeResp(429), market="naver", key="a1")
    assert resp.status_code == 429              # 가짜 성공 아님 — 실패 응답 그대로
    st = mt.get_stats()["naver:a1"]
    assert st["429"] == 4                       # 1 + 재시도 3


def test_5xx_retried_then_returns_last():
    resp = mt.throttled_request(lambda: FakeResp(503), market="coupang", key="v1")
    assert resp.status_code == 503
    assert mt.get_stats()["coupang:v1"]["5xx"] == 4


def test_exception_retried_then_raised():
    calls = {"n": 0}
    def boom():
        calls["n"] += 1
        raise ConnectionError("net")
    with pytest.raises(ConnectionError):
        mt.throttled_request(boom, market="elevenst")
    assert calls["n"] == 4                      # 1 + 재시도 3


def test_rate_limit_remaining_header_logged(caplog):
    with caplog.at_level(logging.INFO):
        mt.throttled_request(
            lambda: FakeResp(200, {"GNCP-GW-RateLimit-Remaining": "58"}),
            market="coupang", key="v1")
    assert any("잔여 호출" in r.message and "58" in str(r.args) + r.message for r in caplog.records) \
        or any("58" in r.getMessage() for r in caplog.records)


def test_bulk_30_first_429_all_succeed():
    """판정: 벌크 30건, 매 첫 호출 429여도 재시도로 전건 성공(429 발생은 재시도로 흡수)."""
    ok = 0
    for i in range(30):
        seq = [FakeResp(429), FakeResp(200)]
        resp = mt.throttled_request(lambda: seq.pop(0), market="coupang", key="v1")
        if resp.status_code == 200:
            ok += 1
    assert ok == 30                             # 성공 30 / 실패 0
    assert mt.get_stats()["coupang:v1"]["429"] == 30


def test_pacing_enforces_min_interval(monkeypatch):
    """페이싱: 같은 (market,key) 연속 호출 사이에 최소 간격(1/RPS)만큼 sleep 요청."""
    monkeypatch.setenv("MARKET_RPS_COUPANG", "10")   # interval 0.1s
    slept = []
    monkeypatch.setattr(mt.time, "sleep", lambda s: slept.append(s))
    # monotonic을 고정(진행 0)해 대기 계산이 간격을 반영하도록
    monkeypatch.setattr(mt.time, "monotonic", lambda: 0.0)
    mt.reset_stats()
    for _ in range(4):
        mt.throttled_request(lambda: FakeResp(200), market="coupang", key="v1")
    # 첫 호출 외 나머지는 최소 간격(0.1s) 이상 대기 요청(시계 고정이라 누적 0.1/0.2/0.3)
    pos = [s for s in slept if s > 0]
    assert len(pos) >= 3
    assert all(s >= 0.1 - 1e-9 for s in pos)         # 각 대기 ≥ 1/RPS
    assert min(pos) == pytest.approx(0.1)            # 최소 간격 = 1/RPS


def test_relay_request_uses_throttle(monkeypatch):
    """relay_request(직접 폴백)가 스로틀을 타 429를 재시도."""
    import src.market_relay as mr
    monkeypatch.setattr(mt.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setenv("MARKET_RPS_COUPANG", "100000")
    mt.reset_stats()
    seq = [FakeResp(429), FakeResp(200)]
    monkeypatch.setattr(mr.requests, "request", lambda *a, **k: seq.pop(0))
    resp = mr.relay_request("POST", "https://api.coupang.com/x", market="coupang", key="v9")
    assert resp.status_code == 200
    assert mt.get_stats()["coupang:v9"]["429"] == 1


def test_bulk_upload_has_chunked_progress():
    """벌크 등록이 청크 단위 진행률 표시(서버 부하·타임아웃 방지 + 진행률)."""
    from pathlib import Path
    tpl = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    assert "bulkUploadProgress" in tpl and "bulkProgressBar" in tpl
    assert "const CHUNK = 5" in tpl                 # 청크 분할
    assert "done / ids.length" in tpl or "done + chunk.length" in tpl  # 진행 누적
    # 성공+실패 합계 = 전체(정직 집계)
    assert "실패 ${ids.length - succeeded}" in tpl
