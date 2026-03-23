"""발주 큐 관리 — 큐 생성/조회/승인/거절 + 중복 방지 + 우선순위 계산."""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '')
REORDER_WORKSHEET = os.getenv('REORDER_WORKSHEET', 'reorder_queue')

# 발주 큐 시트 헤더
QUEUE_HEADERS = [
    'sku', 'title', 'vendor', 'current_stock', 'reorder_qty',
    'status', 'created_at', 'updated_at', 'priority',
]

# 발주 상태 상수
STATUS_PENDING = 'pending_approval'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'
STATUS_ORDERED = 'ordered'
STATUS_COMPLETED = 'completed'


class ReorderQueue:
    """발주 큐 관리자.

    Google Sheets 기반 발주 큐 CRUD 제공.
    중복 발주 방지 + 우선순위 계산 포함.
    """

    def __init__(self, sheet_id: str = None, worksheet: str = None):
        self._sheet_id = sheet_id or GOOGLE_SHEET_ID
        self._worksheet = worksheet or REORDER_WORKSHEET

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _get_ws(self):
        """워크시트 객체 반환 (없으면 자동 생성)."""
        from ..utils.sheets import open_sheet
        ws = open_sheet(self._sheet_id, self._worksheet)
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(QUEUE_HEADERS)
        return ws

    def _get_all(self) -> list:
        """전체 발주 큐 반환."""
        try:
            ws = self._get_ws()
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("발주 큐 조회 실패: %s", exc)
            return []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── 공개 API ────────────────────────────────────────────

    def add(self, item: dict) -> bool:
        """발주 큐에 항목 추가.

        Args:
            item: {'sku', 'title', 'vendor', 'current_stock', 'reorder_qty', ...}

        Returns:
            추가 성공 여부
        """
        if self.has_pending(item.get('sku', '')):
            logger.info("이미 대기 중인 SKU — 추가 건너뜀: %s", item.get('sku'))
            return False

        now = self._now_iso()
        priority = self.calc_priority(item)
        try:
            ws = self._get_ws()
            ws.append_row([
                item.get('sku', ''),
                item.get('title', ''),
                item.get('vendor', ''),
                item.get('current_stock', 0),
                item.get('reorder_qty', 1),
                item.get('status', STATUS_PENDING),
                item.get('created_at', now),
                now,
                priority,
            ])
            logger.info("발주 큐 추가: %s", item.get('sku'))
            return True
        except Exception as exc:
            logger.error("발주 큐 추가 실패: %s", exc)
            return False

    def get_by_status(self, status: str) -> list:
        """특정 상태의 발주 항목 반환."""
        rows = self._get_all()
        return [r for r in rows if r.get('status') == status]

    def has_pending(self, sku: str) -> bool:
        """해당 SKU의 승인 대기/승인 완료 항목 존재 여부."""
        rows = self._get_all()
        active_statuses = {STATUS_PENDING, STATUS_APPROVED}
        return any(
            r.get('sku') == sku and r.get('status') in active_statuses
            for r in rows
        )

    def approve(self, sku: str) -> bool:
        """발주 항목 승인."""
        return self._update_status(sku, STATUS_PENDING, STATUS_APPROVED)

    def reject(self, sku: str) -> bool:
        """발주 항목 거절."""
        return self._update_status(sku, STATUS_PENDING, STATUS_REJECTED)

    def mark_ordered(self, sku: str) -> bool:
        """발주 완료 처리."""
        return self._update_status(sku, STATUS_APPROVED, STATUS_ORDERED)

    def get_all(self) -> list:
        """전체 발주 큐 반환 (공개 API)."""
        return self._get_all()

    def get_stats(self) -> dict:
        """발주 큐 통계."""
        rows = self._get_all()
        stats = {
            STATUS_PENDING: 0,
            STATUS_APPROVED: 0,
            STATUS_REJECTED: 0,
            STATUS_ORDERED: 0,
            STATUS_COMPLETED: 0,
            'total': len(rows),
        }
        for r in rows:
            s = r.get('status', '')
            if s in stats:
                stats[s] += 1
        return stats

    @staticmethod
    def calc_priority(item: dict) -> int:
        """발주 우선순위 계산 (높을수록 긴급).

        판매 속도와 현재 재고 기반으로 1~10점 산출.
        """
        stock = int(item.get('current_stock', 0))
        velocity = float(item.get('sales_velocity', 1.0))
        # 재고 0 = 최고 우선순위, 재고 많을수록 낮아짐
        stock_score = max(0, 5 - stock)
        velocity_score = min(5, int(velocity))
        return min(10, stock_score + velocity_score)

    # ── 내부 상태 변경 ───────────────────────────────────────

    def _update_status(self, sku: str, from_status: str, to_status: str) -> bool:
        """특정 SKU의 상태 변경."""
        try:
            ws = self._get_ws()
            rows = ws.get_all_records()
            headers = ws.row_values(1)
            status_col = headers.index('status') + 1
            updated_at_col = (headers.index('updated_at') + 1) if 'updated_at' in headers else None

            now = self._now_iso()
            for idx, row in enumerate(rows, start=2):
                if row.get('sku') == sku and row.get('status') == from_status:
                    ws.update_cell(idx, status_col, to_status)
                    if updated_at_col:
                        ws.update_cell(idx, updated_at_col, now)
                    logger.info("발주 상태 변경: %s %s → %s", sku, from_status, to_status)
                    return True
            logger.warning("발주 항목 미발견: sku=%s, status=%s", sku, from_status)
            return False
        except Exception as exc:
            logger.error("발주 상태 변경 실패: %s", exc)
            return False
