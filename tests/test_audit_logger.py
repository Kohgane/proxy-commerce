"""tests/test_audit_logger.py — 감사 로그 시스템 테스트.

AuditLogger의 이벤트 기록, Google Sheets 연동(mock), 편의 메서드를 검증한다.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.audit.audit_logger import AuditLogger
from src.audit.event_types import EventType


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def audit_logger():
    """Google Sheets 연동 없이 테스트용 AuditLogger."""
    return AuditLogger(sheet_id="")  # sheet_id 비워 Sheets 기록 비활성화


# ──────────────────────────────────────────────────────────
# EventType 테스트
# ──────────────────────────────────────────────────────────

class TestEventTypes:
    def test_event_type_is_string(self):
        """EventType 값이 문자열이다."""
        assert isinstance(EventType.ORDER_CREATED.value, str)
        assert EventType.ORDER_CREATED.value == "order.created"

    def test_event_type_str_repr(self):
        """EventType.value가 문자열이다."""
        assert EventType.ORDER_ROUTED.value == "order.routed"

    def test_all_event_types_unique(self):
        """모든 EventType 값이 고유하다."""
        values = [e.value for e in EventType]
        assert len(values) == len(set(values))


# ──────────────────────────────────────────────────────────
# AuditLogger.log 테스트
# ──────────────────────────────────────────────────────────

class TestAuditLoggerLog:
    def test_log_returns_entry_dict(self, audit_logger):
        """log()가 감사 엔트리 딕셔너리를 반환한다."""
        entry = audit_logger.log(
            event_type=EventType.ORDER_CREATED,
            actor="shopify_webhook",
            resource="order:12345",
            details={"total": "59000"},
            ip_address="1.2.3.4",
        )
        assert entry["event_type"] == "order.created"
        assert entry["actor"] == "shopify_webhook"
        assert entry["resource"] == "order:12345"
        assert entry["details"]["total"] == "59000"
        assert entry["ip_address"] == "1.2.3.4"
        assert "timestamp" in entry

    def test_log_timestamp_is_iso8601(self, audit_logger):
        """timestamp가 ISO 8601 형식이다."""
        entry = audit_logger.log(EventType.SYSTEM_STARTUP)
        ts = entry["timestamp"]
        assert "T" in ts
        assert "+" in ts or "Z" in ts

    def test_log_default_values(self, audit_logger):
        """기본값으로 log()를 호출할 수 있다."""
        entry = audit_logger.log(EventType.HEALTH_CHECK)
        assert entry["actor"] == "system"
        assert entry["resource"] == ""
        assert entry["ip_address"] == ""

    def test_log_order_convenience(self, audit_logger):
        """log_order() 편의 메서드가 올바른 resource를 설정한다."""
        entry = audit_logger.log_order(
            event_type=EventType.ORDER_ROUTED,
            order_id=99999,
            details={"tasks": 3},
        )
        assert entry["resource"] == "order:99999"
        assert entry["actor"] == "order_system"
        assert entry["details"]["tasks"] == 3

    def test_log_api_convenience(self, audit_logger):
        """log_api() 편의 메서드가 올바른 actor를 설정한다."""
        entry = audit_logger.log_api(
            event_type=EventType.API_CALL_SUCCESS,
            service="shopify",
            endpoint="/admin/api/products.json",
            details={"count": 50},
        )
        assert entry["actor"] == "api:shopify"
        assert entry["resource"] == "/admin/api/products.json"


# ──────────────────────────────────────────────────────────
# Google Sheets 연동 테스트 (mock)
# ──────────────────────────────────────────────────────────

class TestAuditLoggerSheets:
    def test_sheets_write_called_when_enabled(self):
        """AUDIT_LOG_ENABLED=1이고 sheet_id가 있으면 Sheets에 기록한다."""
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = []

        with patch("src.audit.audit_logger._AUDIT_ENABLED", True), \
             patch("src.audit.audit_logger.AuditLogger._write_to_sheets") as mock_write:
            logger = AuditLogger(sheet_id="test_sheet_id")
            logger.log(EventType.ORDER_CREATED, resource="order:1")
            mock_write.assert_called_once()

    def test_sheets_not_called_when_no_sheet_id(self):
        """sheet_id가 없으면 Sheets에 기록하지 않는다."""
        with patch("src.audit.audit_logger.AuditLogger._write_to_sheets") as mock_write:
            logger = AuditLogger(sheet_id="")
            logger.log(EventType.ORDER_CREATED)
            mock_write.assert_not_called()

    def test_sheets_failure_does_not_raise(self):
        """Sheets 기록 실패 시 예외를 전파하지 않는다."""
        with patch("src.audit.audit_logger._AUDIT_ENABLED", True), \
             patch("src.utils.sheets.open_sheet", side_effect=Exception("Sheets 오류")):
            logger = AuditLogger(sheet_id="test_sheet")
            # 예외 없이 실행되어야 함
            entry = logger.log(EventType.ORDER_CREATED)
            assert entry is not None
