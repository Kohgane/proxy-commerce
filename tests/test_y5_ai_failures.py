"""Y5(오너 2026-10-04) — AI 호출 실패 원문: 「AI 상세 초안 — 요청 속도 제한」 「AI 다듬기 실패(HTTPError)」만 보였다.

이제 사유 · 공급사 · HTTP 코드 · 재시도 여부 · 응답 앞부분을 한 줄로(화면·로그·계측) · 429는 백오프 1회 재시도 ·
서버 월 예산(AI_MONTHLY_BUDGET_USD)에 초안·다듬기도 묶임 · 제목이 비면 AI를 부르지 않는다(「제목 없음 — 보강 먼저」).
"""
from __future__ import annotations

import pytest
import requests


class _Resp:
    def __init__(self, code, body):
        self.status_code, self.text = code, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)

    def json(self):
        return {"choices": [{"message": {"content": "블랙홀 무드등 미니 우주 인테리어 조명"}}]}


@pytest.fixture
def openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_RETRY_BACKOFF_SEC", "0")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    from src.ai.budget import BudgetGuard
    monkeypatch.setattr(BudgetGuard, "can_spend", lambda self, **k: True)


def test_failure_line_has_status_provider_retry_and_body():
    from src.seller_console.ai.translator import failure_line
    exc = requests.HTTPError("429", response=_Resp(429, '{"error":{"code":"rate_limit_exceeded"}}'))
    line = failure_line(exc, "openai-draft")
    assert "OpenAI HTTP 429" in line and "백오프 재시도 1회 뒤에도 실패" in line and "rate_limit_exceeded" in line


def test_ai_draft_429_is_retried_then_reported_raw(openai_key, monkeypatch):
    from src.seller_console.ai.translator import AITranslator
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: calls.append(1) or _Resp(429, '{"error":"rate_limit"}'))
    res = AITranslator().generate_description({"title": "블랙홀 무드등", "category": "", "keywords": [], "specs": []})
    assert len(calls) == 2                                               # 백오프 1회 재시도
    # Y7-K(오너 2026-10-10): 화면 문구는 한국어 사유 + HTTP 코드만 — 재시도·영문 원문은 관리 기록(ai_call.error)·로그에
    assert res["draft_status"] == "openai_error" and "HTTP 429" in res["draft_error"] and res["draft_code"] == "rate_limit"
    assert "재시도 1회" in res["ai_call"]["error"]


def test_budget_exhausted_says_server_budget(openai_key, monkeypatch):
    from src.ai.budget import BudgetGuard
    from src.seller_console.ai.translator import AITranslator
    monkeypatch.setattr(BudgetGuard, "can_spend", lambda self, **k: False)
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("예산 넘었는데 호출"))
    res = AITranslator().generate_description({"title": "블랙홀 무드등", "category": "", "keywords": [], "specs": []})
    assert "서버 월 예산" in res["draft_error"]


def test_title_polish_reports_http_code_and_skips_empty_title(openai_key, monkeypatch):
    from src.uploaders.coupang_title import build_name, llm_rewrite
    p = {"title_ko": "블랙홀 무드등 미니 우주 조명"}
    rule = build_name(p)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(500, "upstream boom"))
    out = llm_rewrite(p, rule)
    assert "AI 다듬기 실패 — " in out["note"] and "HTTP 500" in out["note"] and "upstream boom" in out["note"]
    assert "HTTPError)" not in out["note"]
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("제목 없는데 호출"))
    assert llm_rewrite({"title": ""}, {"name": "", "parts": {}})["note"] == "제목 없음 — 보강 먼저(AI 다듬기 건너뜀)"


def test_ai_draft_route_skips_empty_title(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "owner-y5"
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=5", seller_id=seller, title="",
                   price="1", currency="CNY", extra={"title": ""})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    d = c.post(f"/seller/collect/preview/{iid}/ai-description", json={}).get_json()
    assert d["ok"] is False and d["skipped"] and d["error"].startswith("제목 없음 — 보강 먼저")
