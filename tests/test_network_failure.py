import socket
import ssl
from unittest.mock import patch

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProxyError

from src.utils.network_failure import failure_kind


@pytest.mark.parametrize("inner, expected", [
    (socket.gaierror(-2, "secret hostname"), "dns"),
    (ssl.SSLError("secret certificate"), "tls"),
    (ConnectionRefusedError(111, "secret endpoint"), "connection_refused"),
    (ConnectionResetError(104, "secret endpoint"), "connection_reset"),
    (requests.exceptions.ReadTimeout("secret url"), "timeout"),
])
def test_nested_requests_chain(inner, expected):
    connection = NewConnectionError(None, "secret")
    connection.__cause__ = inner
    error = requests.exceptions.ConnectionError(MaxRetryError(None, "secret", connection))
    assert failure_kind(error) == expected


def test_proxy_dns_is_not_misreported_as_destination_dns():
    error = requests.exceptions.ProxyError(
        MaxRetryError(None, "secret", ProxyError("secret", socket.gaierror(-2, "secret"))))
    assert failure_kind(error) == "proxy"


def test_cycles_and_unknown_messages_are_safe():
    class SensitiveError(Exception):
        def __str__(self):
            raise AssertionError("exception text must not be read")
    error = SensitiveError("DNS lookup failed password=SECRET")
    error.__cause__ = error
    assert failure_kind(error) == "unknown"


def test_reach_failure_logs_only_category_and_keeps_single_attempt(caplog):
    from src.seller_console.upload_dispatcher import market_reach
    error = requests.exceptions.ConnectionError("https://user:SECRET@host/?token=SECRET")
    error.__cause__ = socket.gaierror(-2, "SECRET")
    with patch("requests.get", side_effect=error) as get, patch("src.market_throttle.pace"):
        result = market_reach("elevenst")
    assert get.call_count == 1
    assert result["ok"] is False and result["detail"] == "ConnectionError"
    assert "market=elevenst reason=dns" in caplog.text
    assert "SECRET" not in caplog.text


def test_http_rejection_still_counts_as_reachable(caplog):
    from src.seller_console.upload_dispatcher import market_reach
    with patch("requests.get") as get, patch("src.market_throttle.pace"):
        get.return_value.status_code = 403
        assert market_reach("elevenst")["ok"] is True
    assert "[market-reach]" not in caplog.text
