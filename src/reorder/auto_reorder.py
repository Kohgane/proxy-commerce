"""자동 재발주 엔진 — 재고 부족 감지 + 벤더별 발주 큐 생성."""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

REORDER_ENABLED = os.getenv('REORDER_ENABLED', '0') == '1'
REORDER_THRESHOLD = int(os.getenv('REORDER_THRESHOLD', '2'))
REORDER_WORKSHEET = os.getenv('REORDER_WORKSHEET', 'reorder_queue')
REORDER_APPROVAL_REQUIRED = os.getenv('REORDER_APPROVAL_REQUIRED', '1') == '1'

GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '')


class AutoReorder:
    """자동 재발주 엔진.

    REORDER_ENABLED=1 환경변수로 활성화.
    재고 임계값 이하 상품 감지 → 벤더별 발주 큐 생성 → 텔레그램 승인 요청.
    """

    def __init__(
        self,
        sheet_id: str = None,
        worksheet: str = None,
        enabled: bool = None,
        threshold: int = None,
    ):
        self._sheet_id = sheet_id or GOOGLE_SHEET_ID
        self._worksheet = worksheet or REORDER_WORKSHEET
        self._enabled = enabled if enabled is not None else REORDER_ENABLED
        self._threshold = threshold if threshold is not None else REORDER_THRESHOLD

    # ── 공개 API ────────────────────────────────────────────

    def run(self, dry_run: bool = False) -> dict:
        """자동 재발주 실행.

        1) 재고 부족 상품 감지
        2) 발주 큐 생성
        3) Google Sheets에 이력 기록
        4) 승인 필요 시 텔레그램 알림

        Args:
            dry_run: True면 큐 생성/알림 없이 감지만 수행

        Returns:
            {
                'enabled': bool,
                'items_checked': int,
                'items_below_threshold': int,
                'queued': int,
                'dry_run': bool,
                'queue_items': list,
            }
        """
        if not self._enabled:
            logger.debug("AutoReorder 비활성화")
            return {'enabled': False, 'items_checked': 0, 'items_below_threshold': 0,
                    'queued': 0, 'dry_run': dry_run, 'queue_items': []}

        # 1) 재고 부족 상품 목록
        low_stock_items = self._detect_low_stock()

        if not low_stock_items:
            logger.info("재고 부족 상품 없음")
            return {
                'enabled': True,
                'items_checked': self._last_total_checked,
                'items_below_threshold': 0,
                'queued': 0,
                'dry_run': dry_run,
                'queue_items': [],
            }

        # 2) 발주 큐 생성
        queue_items = self._build_queue(low_stock_items)

        if not dry_run:
            # 3) Google Sheets 기록
            self._record_to_sheet(queue_items)
            # 4) 텔레그램 알림
            if REORDER_APPROVAL_REQUIRED:
                self._send_approval_request(queue_items)

        logger.info(
            "AutoReorder 완료 — 감지: %d개, 큐 생성: %d개 (dry_run=%s)",
            len(low_stock_items), len(queue_items), dry_run,
        )

        return {
            'enabled': True,
            'items_checked': self._last_total_checked,
            'items_below_threshold': len(low_stock_items),
            'queued': len(queue_items),
            'dry_run': dry_run,
            'queue_items': queue_items,
        }

    def get_pending_approvals(self) -> list:
        """승인 대기 중인 발주 큐 항목 반환."""
        from .reorder_queue import ReorderQueue
        q = ReorderQueue(sheet_id=self._sheet_id, worksheet=self._worksheet)
        return q.get_by_status('pending_approval')

    # ── 내부 헬퍼 ───────────────────────────────────────────

    _last_total_checked = 0

    def _detect_low_stock(self) -> list:
        """재고 임계값 이하 상품 감지."""
        try:
            from ..inventory.inventory_sync import InventorySync
            sync = InventorySync(sheet_id=self._sheet_id)
            rows = sync._get_active_rows()
            self._last_total_checked = len(rows)
            return [
                r for r in rows
                if int(r.get('stock', 0)) <= self._threshold
            ]
        except Exception as exc:
            logger.error("재고 조회 실패: %s", exc)
            self._last_total_checked = 0
            return []

    def _build_queue(self, items: list) -> list:
        """발주 큐 항목 생성."""
        from .reorder_queue import ReorderQueue
        q = ReorderQueue(sheet_id=self._sheet_id, worksheet=self._worksheet)
        queue_items = []
        for item in items:
            sku = item.get('sku', '')
            if not sku:
                continue
            # 중복 발주 방지
            if q.has_pending(sku):
                logger.debug("이미 발주 대기 중인 SKU 건너뜀: %s", sku)
                continue
            entry = {
                'sku': sku,
                'title': item.get('title', '-'),
                'vendor': item.get('vendor', '-'),
                'current_stock': int(item.get('stock', 0)),
                'threshold': self._threshold,
                'reorder_qty': self._calc_reorder_qty(item),
                'status': 'pending_approval' if REORDER_APPROVAL_REQUIRED else 'approved',
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
            queue_items.append(entry)
        return queue_items

    @staticmethod
    def _calc_reorder_qty(item: dict) -> int:
        """재발주 수량 계산 — 안전 재고 기반."""
        safety_stock = int(os.getenv('SAFETY_STOCK_DAYS', '3'))
        velocity = float(item.get('sales_velocity', 1.0))
        return max(1, int(velocity * safety_stock))

    def _record_to_sheet(self, queue_items: list) -> None:
        """발주 큐를 Google Sheets에 기록."""
        if not queue_items:
            return
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._worksheet)
            for item in queue_items:
                ws.append_row([
                    item['sku'], item['title'], item['vendor'],
                    item['current_stock'], item['reorder_qty'],
                    item['status'], item['created_at'],
                ])
            logger.info("발주 큐 %d건 Google Sheets 기록 완료", len(queue_items))
        except Exception as exc:
            logger.error("Google Sheets 기록 실패: %s", exc)

    def _send_approval_request(self, queue_items: list) -> None:
        """텔레그램으로 발주 승인 요청 발송."""
        import requests as req_lib

        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        if not bot_token or not chat_id:
            logger.warning("텔레그램 설정 없음 — 승인 요청 건너뜀")
            return

        lines = ["*📋 자동 재발주 승인 요청*\n"]
        for item in queue_items[:10]:  # 최대 10개
            lines.append(
                f"• `{item['sku']}` {item['title'][:20]}\n"
                f"  재고: {item['current_stock']} | 발주량: {item['reorder_qty']} | 벤더: {item['vendor']}"
            )
        if len(queue_items) > 10:
            lines.append(f"\n_... 외 {len(queue_items) - 10}개_")
        lines.append("\n승인하려면 관리자 패널을 확인하세요.")

        text = '\n'.join(lines)
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        try:
            req_lib.post(
                url,
                json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'},
                timeout=10,
            )
        except Exception as exc:
            logger.error("텔레그램 승인 요청 발송 실패: %s", exc)
