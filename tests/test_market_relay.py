"""tests/test_market_relay.py — 마켓 고정 IP 릴레이 클라이언트 (Phase 265, v8 P0)."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("MARKET_RELAY_URL", "MARKET_RELAY_TOKEN", "MARKET_RELAY_MARKETS"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_direct_when_relay_unconfigured(monkeypatch):
    """릴레이 미설정 → 직접 requests 호출(폴백, 회귀 없음)."""
    from src import market_relay
    assert market_relay.relay_enabled("coupang") is False
    with patch("src.market_relay.requests.request") as mock_req:
        mock_req.return_value = MagicMock(status_code=200)
        market_relay.relay_request("GET", "https://api-gateway.coupang.com/x",
                                   headers={"A": "1"}, market="coupang")
    mock_req.assert_called_once()


def test_relay_used_when_configured(monkeypatch):
    """릴레이 설정 + 대상 마켓 → 릴레이로 POST, 응답 패스스루."""
    monkeypatch.setenv("MARKET_RELAY_URL", "https://relay.example.com")
    monkeypatch.setenv("MARKET_RELAY_TOKEN", "tok-123")
    from src import market_relay
    assert market_relay.relay_enabled("coupang") is True

    relay_resp = MagicMock()
    relay_resp.raise_for_status.return_value = None
    relay_resp.json.return_value = {"status": 201, "body": json.dumps({"ok": True})}
    with patch("src.market_relay.requests.post", return_value=relay_resp) as mock_post, \
         patch("src.market_relay.requests.request") as mock_direct:
        resp = market_relay.relay_request("POST", "https://api-gateway.coupang.com/v2/products",
                                          json={"name": "x"}, headers={"Authorization": "CEA ..."},
                                          market="coupang")
    mock_post.assert_called_once()
    mock_direct.assert_not_called()
    assert resp.status_code == 201
    assert resp.json() == {"ok": True}
    # 릴레이로 보낸 스펙에 서명된 헤더/바디가 담김
    sent = mock_post.call_args
    assert "/relay" in sent.args[0]
    assert sent.kwargs["headers"]["Authorization"] == "Bearer tok-123"
    assert "X-Relay-Signature" in sent.kwargs["headers"]


def test_non_relay_market_goes_direct(monkeypatch):
    """릴레이 설정돼도 대상 아닌 마켓(shopify)은 직접 호출."""
    monkeypatch.setenv("MARKET_RELAY_URL", "https://relay.example.com")
    monkeypatch.setenv("MARKET_RELAY_TOKEN", "tok")
    monkeypatch.setenv("MARKET_RELAY_MARKETS", "coupang,smartstore")
    from src import market_relay
    assert market_relay.relay_enabled("shopify") is False
    with patch("src.market_relay.requests.request") as mock_req, \
         patch("src.market_relay.requests.post") as mock_post:
        mock_req.return_value = MagicMock(status_code=200)
        market_relay.relay_request("GET", "https://shop.myshopify.com/x", market="shopify")
    mock_req.assert_called_once()
    mock_post.assert_not_called()


def test_relay_response_raise_for_status():
    from src.market_relay import RelayResponse
    import requests
    RelayResponse(200, "{}").raise_for_status()  # no raise
    with pytest.raises(requests.exceptions.HTTPError):
        RelayResponse(401, "").raise_for_status()
