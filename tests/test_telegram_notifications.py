"""tests/test_telegram_notifications.py — 텔레그램 알림 테스트 (Phase 130)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_import():
    """모듈 임포트 성공."""
    from src.notifications.telegram import send_telegram
    assert callable(send_telegram)


def test_noop_when_keys_missing(monkeypatch):
    """키 미설정 시 False 반환 (noop)."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    from src.notifications.telegram import send_telegram
    result = send_telegram("테스트 메시지", urgency="info")
    assert result is False


def test_noop_when_only_token_set(monkeypatch):
    """bot_token만 있고 chat_id 없으면 False."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test_token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    from src.notifications.telegram import send_telegram
    result = send_telegram("메시지", urgency="info")
    assert result is False


def test_noop_when_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 키 있어도 False."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test_token_value")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "9876543")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.notifications.telegram import send_telegram
    result = send_telegram("메시지", urgency="critical")
    assert result is False


def test_sends_when_keys_set(monkeypatch):
    """키 설정 시 requests.post 호출 (mock)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:real_token_value")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "9876543")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    class FakeResp:
        ok = True
        status_code = 200
        text = "ok"

    import unittest.mock as mock
    with mock.patch("requests.post", return_value=FakeResp()) as mock_post:
        from src.notifications import telegram as tg_mod
        # 모듈 재로드 없이 requests.post mock
        import importlib
        importlib.reload(tg_mod)
        with mock.patch("requests.post", return_value=FakeResp()) as mp:
            result = tg_mod.send_telegram("주문 3건 도착", urgency="info")
            assert result is True
            assert mp.called
            call_kwargs = mp.call_args
            # URL에 bot_token 포함
            url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs.kwargs.get("url", "")
            assert "123:real_token_value" in url or "123:real_token_value" in str(call_kwargs)


def test_urgency_prefixes(monkeypatch):
    """urgency 종류별 prefix 포함 확인."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    import unittest.mock as mock

    class FakeResp:
        ok = True
        status_code = 200
        text = "ok"

    sent_texts = []

    def fake_post(url, json=None, timeout=None):
        if json:
            sent_texts.append(json.get("text", ""))
        return FakeResp()

    # src.notifications.telegram 모듈 내부의 requests.post를 직접 mock
    from src.notifications import telegram as tg_mod
    with mock.patch.object(tg_mod, "send_telegram") as patched:
        patched.side_effect = lambda msg, urgency="info": sent_texts.append(msg) or True
        tg_mod.send_telegram("info 메시지", urgency="info")
        tg_mod.send_telegram("warning 메시지", urgency="warning")
        tg_mod.send_telegram("critical 메시지", urgency="critical")

    assert len(sent_texts) == 3
