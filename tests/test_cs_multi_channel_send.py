from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_send_to_channels_partial_failure(monkeypatch):
    monkeypatch.setenv("CS_MULTICHANNEL_ENABLED", "1")
    from src.cs_bot.multi_channel_send import Customer, send_to_channels

    customer = Customer(customer_id="c1", customer_name="Kim", language="ko")
    with patch("src.cs_bot.multi_channel_send._send_one", side_effect=[True, False]):
        result = send_to_channels(customer, "테스트", ["telegram", "email"])
    assert result["telegram"] is True
    assert result["email"] is False


def test_adjust_tone_by_channel():
    from src.cs_bot.multi_channel_send import adjust_tone

    assert "안녕하세요." in adjust_tone("배송 안내드립니다.", "email", "ko")
    assert adjust_tone("길게 작성된 문장입니다.", "telegram", "ko")
    assert adjust_tone("변수 {{name}}", "kakao_alimtalk", "ko").startswith("[Kohgane]")
