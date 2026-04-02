"""Tests for scripts/smoke_test.py."""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from smoke_test import check_endpoint, main


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestCheckEndpoint:
    def test_check_endpoint_success(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(200)):
            result = check_endpoint("http://localhost:8000", "/health")
        assert result is True

    def test_check_endpoint_failure(self):
        http_error = urllib.error.HTTPError(
            url="http://localhost:8000/health",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            result = check_endpoint("http://localhost:8000", "/health")
        assert result is False

    def test_check_endpoint_timeout(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = check_endpoint("http://localhost:8000", "/health")
        assert result is False

    def test_check_endpoint_optional_failure_returns_true(self):
        http_error = urllib.error.HTTPError(
            url="http://localhost:8000/optional",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            result = check_endpoint("http://localhost:8000", "/optional", optional=True)
        assert result is True


class TestMainExitCodes:
    def test_main_all_pass_returns_zero(self):
        with patch("smoke_test.check_endpoint", return_value=True):
            code = main("http://localhost:8000")
        assert code == 0

    def test_main_required_fail_returns_one(self):
        # Simulate /health failing (first call returns False, rest True)
        side_effects = [False, True, True]
        with patch("smoke_test.check_endpoint", side_effect=side_effects):
            code = main("http://localhost:8000")
        assert code == 1
