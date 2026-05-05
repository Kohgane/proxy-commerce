"""tests/test_trackingmore.py — TrackingMore 운송장 추적 테스트 (Phase 133)."""
from __future__ import annotations

import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_import():
    """모듈 임포트 성공."""
    from src.seller_console.orders.tracking_trackingmore import (
        TrackingMoreClient,
        KOREA_COURIERS,
        get_courier_code,
    )
    assert callable(get_courier_code)
    assert isinstance(KOREA_COURIERS, dict)


def test_courier_code_map_has_cj():
    """CJ대한통운 코드 포함."""
    from src.seller_console.orders.tracking_trackingmore import KOREA_COURIERS
    assert "CJ대한통운" in KOREA_COURIERS
    assert KOREA_COURIERS["CJ대한통운"] == "cj-korea"


def test_get_courier_code():
    """택배사 이름 → TrackingMore 코드 변환."""
    from src.seller_console.orders.tracking_trackingmore import get_courier_code
    assert get_courier_code("한진") == "hanjin"
    assert get_courier_code("롯데") == "lotte"
    assert get_courier_code("알수없는택배") == ""


def test_stub_when_key_missing(monkeypatch):
    """TRACKINGMORE_API_KEY 미설정 시 stub 반환."""
    monkeypatch.delenv("TRACKINGMORE_API_KEY", raising=False)
    from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
    client = TrackingMoreClient()
    assert not client.active
    result = client.get_status("123456789012", "cj-korea")
    assert result["status"] == "stub"
    assert result["is_delivered"] is False


def test_detect_courier_inactive(monkeypatch):
    """키 미설정 시 detect_courier 빈 목록 반환."""
    monkeypatch.delenv("TRACKINGMORE_API_KEY", raising=False)
    from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
    client = TrackingMoreClient()
    result = client.detect_courier("123456789012")
    assert result == []


def test_register_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 외부 호출 차단."""
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "tm_test_key_12345")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
    client = TrackingMoreClient()
    result = client.register("123456789012", "cj-korea", "order_001")
    assert result.get("_dry_run") is True


def test_get_status_delivered(monkeypatch):
    """배송완료 상태 반환."""
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "tm_test_key_12345")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [{
                    "delivery_status": "delivered",
                    "latest_event_time": "2026-05-01T10:00:00Z",
                    "origin_info": {"trackinfo": [{"Details": "배송완료"}]},
                }]
            }

    with mock.patch("requests.get", return_value=FakeResp()):
        from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
        client = TrackingMoreClient()
        result = client.get_status("123456789012", "cj-korea")

    assert result["status"] == "delivered"
    assert result["is_delivered"] is True
    assert len(result["checkpoints"]) == 1


def test_get_status_not_found(monkeypatch):
    """운송장 미등록 시 not_found 반환."""
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "tm_test_key_12345")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": []}

    with mock.patch("requests.get", return_value=FakeResp()):
        from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
        client = TrackingMoreClient()
        result = client.get_status("000000000000", "cj-korea")

    assert result["status"] == "not_found"


def test_health_check_missing_key(monkeypatch):
    """키 미설정 시 status=missing."""
    monkeypatch.delenv("TRACKINGMORE_API_KEY", raising=False)
    from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
    result = TrackingMoreClient().health_check()
    assert result["status"] == "missing"


def test_health_check_ok(monkeypatch):
    """키 설정 + API 200 시 status=ok."""
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "tm_test_key_12345")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"courier_code": "cj-korea"}, {"courier_code": "hanjin"}]}

    with mock.patch("requests.get", return_value=FakeResp()):
        from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
        result = TrackingMoreClient().health_check()
    assert result["status"] == "ok"
    assert result["couriers"] == 2


def test_detect_courier_returns_codes(monkeypatch):
    """택배사 자동 감지 — 코드 목록 반환."""
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "tm_test_key_12345")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"courier_code": "cj-korea"}, {"courier_code": "hanjin"}]}

    with mock.patch("requests.post", return_value=FakeResp()):
        from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient
        result = TrackingMoreClient().detect_courier("123456789012")
    assert "cj-korea" in result
    assert "hanjin" in result
