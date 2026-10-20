"""Y13-F F4(오너 2026-10-19) — BLACKHOLES 셰고가·고코스모스 「AI 초안 대신 기본 문장 — OpenAI 크레딧 없음」.

그 초안은 10-10(Y8 Anthropic 우선 전)에 OpenAI 단독으로 만들다 실패한 기본 문장(provider stub)이었고, 형식 버전이 최신이라
다시 만들지 않았다. 지금은 Anthropic이 준비돼 있으면 다시 만든다(이미 Anthropic으로 시도했다 실패한 건 6시간 뒤).
"""
from datetime import datetime, timedelta, timezone

from src.seller_console import views as V


def _ready(monkeypatch, anth=True, openai=False):
    from src.ai import llm
    monkeypatch.setattr(llm, "anthropic_ready", lambda: anth)
    if openai:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    else:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _stub(**kw):
    return {"text": "기본 문장", "provider": "stub", "draft_status": "openai_error", "draft_code": "insufficient_quota",
            "at": datetime.now(timezone.utc).isoformat(), **kw}


def test_pre_y8_stub_is_rebuilt_when_anthropic_ready(monkeypatch):
    _ready(monkeypatch)
    assert V._pv_stub_rebuild(_stub()) is True


def test_real_ai_draft_is_kept(monkeypatch):
    _ready(monkeypatch)
    assert V._pv_stub_rebuild({"text": "AI 글", "provider": "anthropic"}) is False


def test_no_ai_ready_keeps_stub(monkeypatch):
    _ready(monkeypatch, anth=False, openai=False)
    assert V._pv_stub_rebuild(_stub()) is False


def test_anthropic_tried_and_failed_waits_6h(monkeypatch):
    _ready(monkeypatch)
    fresh = _stub(draft_code_anthropic="overloaded", draft_status="anthropic_error")
    assert V._pv_stub_rebuild(fresh) is False
    old = dict(fresh, at=(datetime.now(timezone.utc) - timedelta(hours=7)).isoformat())
    assert V._pv_stub_rebuild(old) is True


def test_openai_only_stub_waits_too(monkeypatch):
    _ready(monkeypatch, anth=False, openai=True)
    assert V._pv_stub_rebuild(_stub()) is False                  # 크레딧 없는 OpenAI만 있으면 사전검증마다 부르지 않는다
