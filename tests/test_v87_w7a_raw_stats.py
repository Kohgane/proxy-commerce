"""tests/test_v87_w7a_raw_stats.py — v87-W7a branch②: 원 응답 코드·바디를 translate_stats에 적재.

오너 구성 결백 실증(예산 100/한도 100/키 일치/잔액 $22.37) → '한도 초과' 발화 주체는 코드 내부.
다음 실패부터 **원문 사유가 남게** 원 응답(status·body)을 계측에 보존한다(오귀인 대조).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import src.seller_console.ai.translator as T


class _Resp:
    def __init__(self, code, body):
        self.status_code = code
        self.text = body


def _exc(msg, code=None, body=""):
    e = Exception(msg)
    if code is not None:
        e.response = _Resp(code, body)
    return e


@pytest.fixture(autouse=True)
def _reset():
    T.reset_translate_stats()


def test_raw_error_meta_extracts_status_and_body():
    st, body = T.raw_error_meta(_exc("boom", 429, '{"error":{"type":"rate_limit_exceeded"}}'))
    assert st == 429 and "rate_limit_exceeded" in body


def test_record_failure_preserves_raw_response():
    T.record_translate_failure(_exc("Rate limit reached", 429, '{"type":"rate_limit_exceeded"}'), "openai")
    s = T.get_translate_stats()
    assert s["fail"] == 1
    assert s["by_code"] == {"rate_limit": 1}                    # 사유코드별 집계
    r = s["recent"][-1]
    assert r["provider"] == "openai" and r["status"] == 429     # 원 HTTP 코드 보존
    assert "rate_limit_exceeded" in r["body"]                   # 원 응답 바디 보존(오귀인 대조)
    assert r["code"] == "rate_limit"


def test_recent_is_ring_buffer_bounded():
    for i in range(40):
        T.record_translate_failure(_exc(f"err{i}", 500, "x"), "openai")
    s = T.get_translate_stats()
    assert len(s["recent"]) <= 25                               # 링버퍼 상한
    assert s["fail"] == 40                                      # 집계는 전건


def test_distinct_codes_recorded_separately():
    T.record_translate_failure(_exc("insufficient_quota", 429, "quota"), "openai")
    T.record_translate_failure(_exc("Rate limit reached", 429, "rl"), "openai")
    T.record_translate_failure(_exc("unauthorized", 401, "auth"), "deepl")
    codes = T.get_translate_stats()["by_code"]
    assert codes.get("quota") == 1 and codes.get("rate_limit") == 1 and codes.get("auth") == 1


def test_diagnostics_exposes_translate_stats():
    src = Path("src/dashboard/admin_views.py").read_text(encoding="utf-8")
    assert "_build_translate_stats" in src
    assert "translate_stats=translate_stats" in src
    assert "최근 실패 원 응답" in src                           # 원 응답 표


def test_stats_builder_readonly():
    import src.dashboard.admin_views as av
    out = av._build_translate_stats()
    assert out.get("available") is True
    assert set(["calls", "ok", "fail", "by_code", "recent"]).issubset(out.keys())
