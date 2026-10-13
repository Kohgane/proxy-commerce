"""#886 후속 — 반려 자동 수정(Claude) 답이 파이프라인이 일부러 지우는 상표 이름을 **새로** 들이면 버린다.

상표(가구 레플리카·영화/캐릭터 IP — `ko_polish.mark_hits`, T3·Y6·Y7-J)는 제목·옵션 값에서 지우고 등록은 보류한다.
Claude 답은 원문 맥락(브랜드)을 보고 그 이름을 되살릴 수 있다 — 「무선 충전기」 → 「디즈니 무선 충전기」.
원래 있던 이름은 이 판정의 일이 아니다(상표 보류가 맡는다) — 「새로」 들어간 것만 막는다.
"""
from __future__ import annotations

import pytest

from src.services import reject_autofix as RAF


class _R:
    def __init__(self, m, ok=False, **kw):
        self.market, self.ok = m, ok
        self.error_code = kw.get("error_code", "")
        self.message = kw.get("message", "")
        self.hint = ""
        self.reach_ok = self.reach_ms = None
        self.reach_detail = ""
        self.details = list(kw.get("details", []))
        self.action_url = ""
        self.hold = kw.get("hold", False)
        self.fixes = kw.get("fixes", [])


PD = {"title_ko": "라운지 체어 오일 가죽 판매 1위", "coupang_name": "라운지 체어 최저가",
      "options": [{"name": "색상", "values": ["黑", "白"], "values_ko": ["블랙 50% 할인", "화이트"]}]}
GOOD = {"fixable": True, "title": "라운지 체어 오일 가죽", "coupang_name": "라운지 체어",
        "options": [{"name": "색상", "values_ko": ["블랙", "화이트"]}], "why": "표시광고 문구 삭제"}


def _row():
    return _R("coupang:woojoo", error_code="ad_claim_risk", message="표시광고 위험 문구",
              details=["상품명에 표시광고 위험 문구 「최저가」 — 빼고 등록해 주세요",
                       "옵션 값에 표시광고 위험 문구 「50% 할인」 — 빼고 등록해 주세요"])


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("REJECT_AUTOFIX_ENABLED", raising=False)


def _run(monkeypatch, pd, answer):
    monkeypatch.setattr(RAF, "_call", lambda fields, reasons, timeout: (dict(answer), {"provider": "anthropic", "model": "m", "error": ""}))
    return RAF.run(pd, RAF.collect(pd, [_row()], {}))


def test_clean_answer_still_applies(monkeypatch):
    rec = _run(monkeypatch, PD, GOOD)
    assert rec["status"] == "done" and len(rec["changes"]) == 3


@pytest.mark.parametrize("bad,label,mark", [
    ({"title": "임스 라운지 체어 오일 가죽"}, "상품명", "임스"),                       # 가구 레플리카
    ({"coupang_name": "Eames 라운지 체어"}, "쿠팡 상품명", "임스"),                  # 영문 표기도 같은 상표
    ({"title": "디즈니 라운지 체어 오일 가죽"}, "상품명", "디즈니"),                   # 캐릭터 IP
    ({"options": [{"name": "색상", "values_ko": ["허먼밀러 블랙", "화이트"]}]}, "옵션 값", "허먼밀러"),
])
def test_new_trademark_name_is_refused(monkeypatch, bad, label, mark):
    rec = _run(monkeypatch, PD, {**GOOD, **bad})
    assert rec["status"] == "failed" and rec["changes"] == []
    assert f"{label}에 상표 이름이 새로 들어갔어요" in rec["error"] and mark in rec["error"]


def test_name_already_there_is_not_this_guards_job(monkeypatch):
    """원래 있던 상표는 막지 않는다(상표 보류가 따로 잡는다) — 이 판정은 「새로」만."""
    pd = dict(PD, title_ko="임스 라운지 체어 오일 가죽 판매 1위")
    rec = _run(monkeypatch, pd, {**GOOD, "title": "임스 라운지 체어 오일 가죽"})
    assert rec["status"] == "done"
    assert any(c["field"] == "title_ko" and c["after"] == "임스 라운지 체어 오일 가죽" for c in rec["changes"])


def test_prompt_says_not_to_add_brand_names():
    assert "새로 넣지 않는다" in RAF._SYSTEM
