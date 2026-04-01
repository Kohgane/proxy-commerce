"""주문 상태 추적 + 중복 알림 방지 모듈.

Google Sheets 기반으로 주문 이력을 관리하고,
이미 알림 보낸 주문의 중복 알림을 방지합니다.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# 주문 상태 순서 (낮은 인덱스 → 높은 인덱스로만 진행)
_STATUS_ORDER = [
    'PAY_WAITING',
    'PAYED',
    'ACCEPT',
    'INSTRUCT',
    'DEPARTURE',
    'DELIVERING',
    'DELIVERED',
    'PURCHASE_DECIDED',
    'CANCEL_REQUEST',
    'CANCELED',
    'RETURN_REQUEST',
    'RETURNED',
]

_WORKSHEET_NAME = 'order_alerts'
_HEADERS = ['order_id', 'platform', 'order_number', 'status', 'alerted_at', 'product_names']


class OrderTracker:
    """주문 상태 추적 + 중복 알림 방지.

    Google Sheets에 알림 이력을 저장하여 중복 알림을 방지합니다.

    환경변수:
        GOOGLE_SHEET_ID: Google Sheets ID
        ORDER_ALERTS_WORKSHEET: 워크시트 이름 (기본: order_alerts)
    """

    def __init__(self, sheet_id: str = None, worksheet: str = None):
        """초기화.

        Args:
            sheet_id: Google Sheets ID (None이면 환경변수 사용)
            worksheet: 워크시트 이름 (None이면 환경변수 또는 기본값)
        """
        self._sheet_id = sheet_id or os.getenv('GOOGLE_SHEET_ID', '')
        self._worksheet = worksheet or os.getenv('ORDER_ALERTS_WORKSHEET', _WORKSHEET_NAME)
        # 인메모리 캐시 {(order_id, status): True}
        self._alerted_cache: set = set()
        self._cache_loaded = False

    # ── public API ───────────────────────────────────────────

    def is_already_alerted(self, order_id: str, status: str = None) -> bool:
        """이미 알림 보낸 주문/상태 여부 확인.

        Args:
            order_id: 주문 ID
            status: 주문 상태 (None이면 주문 자체 존재 여부만 확인)

        Returns:
            이미 알림 발송 여부
        """
        self._ensure_cache_loaded()
        if status:
            return (order_id, status) in self._alerted_cache
        # 주문 자체 존재 여부
        return any(oid == order_id for oid, _ in self._alerted_cache)

    def mark_alerted(self, order: dict, status: str = None):
        """주문 알림 발송 완료 표시.

        Args:
            order: 정규화된 주문 딕셔너리
            status: 알림 발송한 주문 상태 (None이면 order['status'] 사용)
        """
        order_id = str(order.get('order_id', ''))
        effective_status = status or order.get('status', '')
        if not order_id:
            return

        # 메모리 캐시 업데이트
        self._alerted_cache.add((order_id, effective_status))

        # Sheets 기록
        self._save_to_sheets(order, effective_status)

    def get_alerted_orders(self, limit: int = 100) -> List[dict]:
        """알림 발송된 주문 이력 조회.

        Args:
            limit: 최대 반환 수

        Returns:
            알림 이력 목록
        """
        if not self._sheet_id:
            return []
        try:
            ws = self._get_worksheet()
            records = ws.get_all_records()
            return records[-limit:] if len(records) > limit else records
        except Exception as exc:
            logger.warning("주문 이력 조회 실패: %s", exc)
            return []

    def filter_new_orders(self, orders: List[dict]) -> List[dict]:
        """신규 주문(아직 알림 미발송) 필터링.

        Args:
            orders: 주문 목록

        Returns:
            알림 미발송 주문 목록
        """
        return [
            order for order in orders
            if not self.is_already_alerted(str(order.get('order_id', '')), order.get('status'))
        ]

    def get_order_history(self, order_id: str) -> List[dict]:
        """특정 주문의 상태 변경 이력 조회.

        Args:
            order_id: 주문 ID

        Returns:
            상태 변경 이력 목록
        """
        all_records = self.get_alerted_orders(limit=1000)
        return [r for r in all_records if str(r.get('order_id', '')) == order_id]

    def should_send_status_alert(self, order_id: str, new_status: str) -> bool:
        """상태 변경 알림 발송 여부 결정.

        이미 같은 상태로 알림 발송한 경우 False 반환.

        Args:
            order_id: 주문 ID
            new_status: 새로운 주문 상태

        Returns:
            알림 발송 여부
        """
        return not self.is_already_alerted(order_id, new_status)

    # ── Sheets 연동 ──────────────────────────────────────────

    def _save_to_sheets(self, order: dict, status: str):
        """알림 이력을 Google Sheets에 저장.

        Args:
            order: 정규화된 주문 딕셔너리
            status: 알림 발송한 주문 상태
        """
        if not self._sheet_id:
            logger.debug("GOOGLE_SHEET_ID 미설정 — Sheets 저장 건너뜀")
            return
        try:
            ws = self._get_worksheet()
            row = [
                str(order.get('order_id', '')),
                str(order.get('platform', '')),
                str(order.get('order_number', '')),
                status,
                datetime.now(tz=timezone.utc).isoformat(),
                ', '.join(order.get('product_names', [])),
            ]
            ws.append_row(row)
            logger.debug("주문 알림 이력 저장: order_id=%s, status=%s", order.get('order_id'), status)
        except Exception as exc:
            logger.warning("주문 이력 Sheets 저장 실패: %s", exc)

    def _load_cache_from_sheets(self):
        """Sheets에서 알림 이력 로드 → 메모리 캐시.

        중복 방지를 위해 시작 시 기존 이력을 메모리에 로드합니다.
        """
        if not self._sheet_id:
            return
        try:
            ws = self._get_worksheet()
            records = ws.get_all_records()
            for row in records:
                order_id = str(row.get('order_id', ''))
                status = str(row.get('status', ''))
                if order_id:
                    self._alerted_cache.add((order_id, status))
            logger.info("주문 이력 캐시 로드: %d건", len(self._alerted_cache))
        except Exception as exc:
            logger.warning("주문 이력 캐시 로드 실패: %s", exc)

    def _ensure_cache_loaded(self):
        """캐시 최초 로드 보장."""
        if not self._cache_loaded:
            self._load_cache_from_sheets()
            self._cache_loaded = True

    def _get_worksheet(self):
        """워크시트 열기 (없으면 헤더 초기화).

        Returns:
            gspread Worksheet 객체
        """
        from ..utils.sheets import open_sheet
        ws = open_sheet(self._sheet_id, self._worksheet)
        existing = ws.get_all_values()
        if not existing or existing[0] != _HEADERS:
            ws.clear()
            ws.append_row(_HEADERS)
        return ws

    # ── 유틸리티 ────────────────────────────────────────────

    def reset_memory_cache(self):
        """메모리 캐시 초기화 (테스트용).

        주의: Sheets 데이터는 유지됩니다.
        """
        self._alerted_cache.clear()
        self._cache_loaded = False

    def get_cache_size(self) -> int:
        """메모리 캐시 크기 반환."""
        return len(self._alerted_cache)

    def get_sheet_id(self) -> Optional[str]:
        """Sheets ID 반환 (설정된 경우)."""
        return self._sheet_id or None
