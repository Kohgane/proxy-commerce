"""src/audit/audit_logger.py — 감사 로그 시스템.

모든 주요 비즈니스 이벤트(주문 처리, 가격 변경, 재고 변동, API 호출)를
구조화된 형식으로 기록한다.

기록 방법:
  1. Python logging (기본 — 항상 활성화)
  2. Google Sheets 'audit_log' 워크시트 (AUDIT_LOG_ENABLED=1 시)

로그 구조:
  timestamp, event_type, actor, resource, details, ip_address

환경변수:
  AUDIT_LOG_ENABLED  — Google Sheets 기록 활성화 (기본 "1")
  AUDIT_WORKSHEET    — Google Sheets 워크시트명 (기본 "audit_log")
"""

import datetime
import logging
import os
from typing import Any, Dict, List, Optional

from .event_types import EventType

logger = logging.getLogger(__name__)

_AUDIT_ENABLED = os.getenv("AUDIT_LOG_ENABLED", "1") == "1"
_AUDIT_WORKSHEET = os.getenv("AUDIT_WORKSHEET", "audit_log")

# Sheets 헤더
_HEADERS = ["timestamp", "event_type", "actor", "resource", "details", "ip_address"]


class AuditLogger:
    """감사 로그 기록기.

    사용 예:
        audit = AuditLogger()
        audit.log(
            event_type=EventType.ORDER_CREATED,
            actor="shopify_webhook",
            resource=f"order:{order_id}",
            details={"total": "59000", "currency": "KRW"},
            ip_address="1.2.3.4",
        )
    """

    def __init__(self, sheet_id: Optional[str] = None):
        self._sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")
        self._sheets_available: Optional[bool] = None  # Lazy check
        self._audit_logger = logging.getLogger("proxy_commerce.audit")

    # ── 공개 API ──────────────────────────────────────────

    def log(
        self,
        event_type: EventType,
        actor: str = "system",
        resource: str = "",
        details: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
    ) -> Dict[str, Any]:
        """감사 이벤트를 기록한다.

        Args:
            event_type: 이벤트 타입 (EventType 열거형)
            actor: 이벤트를 발생시킨 주체 (예: "shopify_webhook", "admin")
            resource: 대상 리소스 (예: "order:12345", "product:PORTER-BAG-001")
            details: 추가 상세 정보 딕셔너리
            ip_address: 요청 IP 주소

        Returns:
            기록된 감사 이벤트 딕셔너리
        """
        entry = self._build_entry(event_type, actor, resource, details or {}, ip_address)

        # 1) Python 로깅
        self._audit_logger.info(
            "AUDIT | %s | actor=%s | resource=%s | ip=%s | details=%s",
            entry["event_type"], entry["actor"], entry["resource"],
            entry["ip_address"], entry["details"],
        )

        # 2) Google Sheets 기록 (활성화 시)
        if _AUDIT_ENABLED and self._sheet_id:
            self._write_to_sheets(entry)

        return entry

    def log_order(
        self,
        event_type: EventType,
        order_id: Any,
        details: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
    ) -> Dict[str, Any]:
        """주문 관련 감사 이벤트를 기록하는 편의 메서드."""
        return self.log(
            event_type=event_type,
            actor="order_system",
            resource=f"order:{order_id}",
            details=details,
            ip_address=ip_address,
        )

    def log_api(
        self,
        event_type: EventType,
        service: str,
        endpoint: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """API 호출 감사 이벤트를 기록하는 편의 메서드."""
        return self.log(
            event_type=event_type,
            actor=f"api:{service}",
            resource=endpoint,
            details=details,
        )

    # ── 내부 메서드 ───────────────────────────────────────

    def _build_entry(
        self,
        event_type: EventType,
        actor: str,
        resource: str,
        details: Dict[str, Any],
        ip_address: str,
    ) -> Dict[str, Any]:
        """감사 로그 엔트리 딕셔너리를 구성한다."""
        return {
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "event_type": str(event_type.value) if isinstance(event_type, EventType) else str(event_type),
            "actor": actor,
            "resource": resource,
            "details": details,
            "ip_address": ip_address,
        }

    def _write_to_sheets(self, entry: Dict[str, Any]) -> None:
        """Google Sheets audit_log 워크시트에 이벤트를 기록한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, _AUDIT_WORKSHEET)
            # 헤더가 없으면 첫 행에 삽입
            existing = ws.get_all_values()
            if not existing or existing[0] != _HEADERS:
                ws.insert_row(_HEADERS, 1)
            # 새 행 추가
            import json
            row: List[Any] = [
                entry["timestamp"],
                entry["event_type"],
                entry["actor"],
                entry["resource"],
                json.dumps(entry["details"], ensure_ascii=False)[:500],
                entry["ip_address"],
            ]
            ws.append_row(row)
        except Exception as exc:
            logger.warning("감사 로그 Sheets 기록 실패: %s", exc)
