"""tests/test_v87_w7a_cause_split.py — v87-W7a 재개정: '한도 초과' 발화 주체 4분.

오너 실증(OpenAI 잔액 $22.37 → 크레딧 고갈 기각). 현행 "사용량·결제 한도 초과"가 뭉치던 것을
①서버 내부 예산 가드(AI_MONTHLY_BUDGET_USD) ②프로바이더 insufficient_quota ③프로바이더 rate_limit
④401 무효 키로 분리 — 각각 별 문구 + 사유코드. 내부 가드 차단이면 반드시 "서버 월 예산" 명시.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.seller_console.ai.translator import classify_translate_reason, classify_translate_error


class _Resp:
    def __init__(self, code): self.status_code = code


def _http(msg, code=None):
    e = Exception(msg)
    if code:
        e.response = _Resp(code)
    return e


class BudgetExceededError(Exception):
    """copywriter가 던지는 것과 동일한 이름(가드 차단 식별)."""


def test_four_causes_have_distinct_codes():
    codes = {
        classify_translate_reason(BudgetExceededError("AI 월 예산 초과: 100/100 USD"))[0],
        classify_translate_reason(_http("Error code: 429 insufficient_quota", 429))[0],
        classify_translate_reason(_http("Rate limit reached", 429))[0],
        classify_translate_reason(_http("unauthorized", 401))[0],
    }
    assert codes == {"budget", "quota", "rate_limit", "auth"}   # 4분 전부 유일


def test_budget_guard_names_server_budget_not_openai():
    code, msg = classify_translate_reason(BudgetExceededError("AI 월 예산 초과"))
    assert code == "budget"
    assert "서버 월 예산" in msg                 # 반드시 명시(오너가 OpenAI 지갑 뒤지지 않게)
    assert "OpenAI 잔액 아님" in msg


def test_rate_limit_is_not_billing():
    code, msg = classify_translate_reason(_http("Rate limit reached for gpt-4o-mini", 429))
    assert code == "rate_limit"
    assert "속도" in msg and "결제 아님" in msg   # 결제로 오귀인 금지(잠시 후 재시도)


def test_insufficient_quota_is_billing():
    code, msg = classify_translate_reason(_http("You exceeded your current quota, insufficient_quota", 429))
    assert code == "quota"
    assert "크레딧" in msg or "결제" in msg


def test_auth_invalid_key():
    code, msg = classify_translate_reason(_http("invalid_api_key", 401))
    assert code == "auth" and "키" in msg


def test_error_string_matches_reason_second():
    # classify_translate_error(하위호환)은 (code,msg)의 msg와 일치.
    e = _http("Rate limit reached", 429)
    assert classify_translate_error(e) == classify_translate_reason(e)[1]


# ── /admin/diagnostics 예산 가드 읽기전용 노출 ────────────────────────
def test_diagnostics_exposes_ai_budget_readonly():
    src = Path("src/dashboard/admin_views.py").read_text(encoding="utf-8")
    assert "_build_ai_budget_status" in src
    assert "AI_MONTHLY_BUDGET_USD" in src
    assert "서버 월 예산 초과(OpenAI 잔액 아님)" in src   # 차단 뱃지 문구
    assert "ai_budget=ai_budget" in src                   # 템플릿에 주입


def test_ai_budget_builder_is_readonly_summary(monkeypatch):
    # 빌더는 요약만 읽고(쓰기 0) status/blocked를 반환. 시트 미연결이어도 정직(available False).
    import src.dashboard.admin_views as av
    out = av._build_ai_budget_status()
    assert "available" in out
    if out["available"]:
        assert set(["limit_usd", "used_usd", "pct", "status", "blocked"]).issubset(out.keys())
