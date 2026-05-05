"""tests/test_tracking_sweet.py — SweetTracker 운송장 추적 테스트 (Phase 130)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_import():
    """모듈 임포트 성공."""
    from src.seller_console.orders.tracking_sweet import (
        get_tracking_info,
        get_courier_code,
        COURIER_CODE_MAP,
    )
    assert callable(get_tracking_info)
    assert callable(get_courier_code)
    assert isinstance(COURIER_CODE_MAP, dict)


def test_courier_code_map_has_cj():
    """CJ대한통운 코드 포함."""
    from src.seller_console.orders.tracking_sweet import COURIER_CODE_MAP
    assert "CJ대한통운" in COURIER_CODE_MAP
    assert COURIER_CODE_MAP["CJ대한통운"] == "04"


def test_get_courier_code():
    """택배사 이름 → 코드 변환."""
    from src.seller_console.orders.tracking_sweet import get_courier_code
    assert get_courier_code("한진") == "05"
    assert get_courier_code("롯데") == "08"
    assert get_courier_code("알수없는택배") == "00"


def test_stub_when_key_missing(monkeypatch):
    """SWEETTRACKER_API_KEY 미설정 시 stub 반환."""
    monkeypatch.delenv("SWEETTRACKER_API_KEY", raising=False)
    from src.seller_console.orders.tracking_sweet import get_tracking_info
    result = get_tracking_info("123456789012", "04")
    assert result["stub"] is True
    assert result["tracking_no"] == "123456789012"
    assert result["courier_code"] == "04"
    assert result["is_delivered"] is False


def test_stub_when_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 stub 반환."""
    monkeypatch.setenv("SWEETTRACKER_API_KEY", "sweet_test_key")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.orders.tracking_sweet import get_tracking_info
    result = get_tracking_info("123456789012", "05")
    assert result["stub"] is True
    assert result.get("reason") == "dry_run"


def test_stub_response_structure(monkeypatch):
    """stub 응답 구조 확인."""
    monkeypatch.delenv("SWEETTRACKER_API_KEY", raising=False)
    from src.seller_console.orders.tracking_sweet import get_tracking_info
    result = get_tracking_info("987654321", "08")
    required_keys = ["tracking_no", "courier_code", "courier_name", "status", "events", "is_delivered", "stub"]
    for k in required_keys:
        assert k in result, f"키 누락: {k}"
    assert isinstance(result["events"], list)


def test_get_courier_name_from_code():
    """코드 → 택배사 이름 역매핑 (courier_name 필드)."""
    monkp = pytest.MonkeyPatch()
    monkp.delenv("SWEETTRACKER_API_KEY", raising=False)
    from src.seller_console.orders.tracking_sweet import get_tracking_info
    result = get_tracking_info("111222333", "04")
    # "CJ" 또는 "CJ대한통운" — 역매핑에서 먼저 등록된 이름 반환
    assert "CJ" in result["courier_name"]
    monkp.undo()
