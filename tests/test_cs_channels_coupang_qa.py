from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_coupang_qa_inactive_without_keys(monkeypatch):
    monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
    monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)
    from src.cs_bot.channels.coupang_qa import CoupangQAAdapter
    adapter = CoupangQAAdapter()
    assert not adapter.is_active()
    assert adapter.poll() == []
    assert not adapter.send_reply("buyer", "hi", ref="123")


def test_coupang_qa_active_with_keys(monkeypatch):
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "test_access")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "test_secret")
    from src.cs_bot.channels.coupang_qa import CoupangQAAdapter
    adapter = CoupangQAAdapter()
    assert adapter.is_active()


def test_coupang_qa_poll_no_vendor_id(monkeypatch):
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "test_access")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "test_secret")
    monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
    from src.cs_bot.channels.coupang_qa import CoupangQAAdapter
    adapter = CoupangQAAdapter()
    result = adapter.poll()
    assert result == []


def test_coupang_qa_poll_api_error(monkeypatch):
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "test_access")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "test_secret")
    monkeypatch.setenv("COUPANG_VENDOR_ID", "A00123456")
    with patch("requests.get", side_effect=Exception("network error")):
        from src.cs_bot.channels.coupang_qa import CoupangQAAdapter
        adapter = CoupangQAAdapter()
        result = adapter.poll()
        assert result == []


def test_coupang_qa_poll_parses_response(monkeypatch):
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "test_access")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "test_secret")
    monkeypatch.setenv("COUPANG_VENDOR_ID", "A00123456")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "data": {
            "content": [
                {"questionId": "Q001", "writerMemberId": "buyer1", "questionContent": "배송 언제오나요?", "createdAt": "2024-01-01T00:00:00", "productId": "P001"}
            ]
        }
    }
    with patch("requests.get", return_value=mock_resp):
        from src.cs_bot.channels.coupang_qa import CoupangQAAdapter
        adapter = CoupangQAAdapter()
        msgs = adapter.poll()
        assert len(msgs) == 1
        assert msgs[0].raw_id == "Q001"
        assert "배송" in msgs[0].body
