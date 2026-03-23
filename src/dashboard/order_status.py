"""Google Sheets 기반 주문 상태 추적 모듈."""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 주문 시트 헤더 (순서 유지)
ORDER_HEADERS = [
    'order_id', 'order_number', 'customer_name', 'customer_email',
    'order_date', 'sku', 'vendor', 'forwarder',
    'buy_price', 'buy_currency', 'sell_price_krw', 'sell_price_usd',
    'margin_pct', 'status', 'status_updated_at',
    'tracking_number', 'carrier', 'notes',
]

_PENDING_EXCLUDE = {'delivered', 'cancelled'}


class OrderStatusTracker:
    """Google Sheets 기반 주문 상태 추적기."""

    # 주문 상태 상수
    STATUS_NEW = 'new'
    STATUS_ROUTED = 'routed'
    STATUS_ORDERED = 'ordered'
    STATUS_SHIPPED_VENDOR = 'shipped_vendor'
    STATUS_AT_FORWARDER = 'at_forwarder'
    STATUS_SHIPPED_DOMESTIC = 'shipped_domestic'
    STATUS_DELIVERED = 'delivered'
    STATUS_CANCELLED = 'cancelled'

    VALID_STATUSES = [
        STATUS_NEW, STATUS_ROUTED, STATUS_ORDERED,
        STATUS_SHIPPED_VENDOR, STATUS_AT_FORWARDER,
        STATUS_SHIPPED_DOMESTIC, STATUS_DELIVERED, STATUS_CANCELLED,
    ]

    def __init__(self, sheet_id: str = None, worksheet: str = None):
        """
        sheet_id: Google Sheets ID (None이면 GOOGLE_SHEET_ID 환경변수)
        worksheet: 주문 상태 시트 이름 (기본 'orders' 또는 ORDERS_WORKSHEET 환경변수)
        """
        self._sheet_id = sheet_id or os.getenv('GOOGLE_SHEET_ID', '')
        self._worksheet = worksheet or os.getenv('ORDERS_WORKSHEET', 'orders')

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _get_worksheet(self):
        """Google Sheets 워크시트 객체 반환 (없으면 자동 생성)."""
        from ..utils.sheets import open_sheet
        ws = open_sheet(self._sheet_id, self._worksheet)
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(ORDER_HEADERS)
        return ws

    def _get_all_rows(self) -> list[dict]:
        """시트 전체 행 반환. 워크시트가 없거나 비어있으면 빈 리스트 반환."""
        try:
            ws = self._get_worksheet()
            rows = ws.get_all_records()
            return rows
        except Exception as exc:
            logger.warning("_get_all_rows() failed, returning empty list: %s", exc)
            return []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    @staticmethod
    def _calc_margin_pct(buy_price_krw: float, sell_price_krw: float) -> float:
        """마진율 계산 (%)."""
        if not sell_price_krw or sell_price_krw == 0:
            return 0.0
        return round((sell_price_krw - buy_price_krw) / sell_price_krw * 100, 2)

    # ── 공개 API ────────────────────────────────────────────

    def record_order(self, order_data: dict, routed_data: dict) -> dict:
        """신규 주문 + 라우팅 결과를 시트에 기록.

        order_data: Shopify webhook payload
        routed_data: OrderRouter.route_order() 반환값

        Returns: 기록된 행 딕셔너리 목록 (task별 1행)
        """
        ws = self._get_worksheet()

        # 헤더가 없으면 첫 행에 삽입
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(ORDER_HEADERS)

        order_id = str(order_data.get('id', ''))
        order_number = str(routed_data.get('order_number', ''))
        customer = routed_data.get('customer', {})
        customer_name = customer.get('name', '')
        customer_email = customer.get('email', '')
        order_date = order_data.get('created_at', self._now_iso())
        now = self._now_iso()

        recorded = []
        for task in routed_data.get('tasks', []):
            sku = task.get('sku', '')
            vendor = task.get('vendor', '')
            forwarder = task.get('forwarder', '')
            buy_price = task.get('buy_price', 0.0)
            buy_currency = task.get('buy_currency', '')

            # sell price: line_items에서 추출 시도
            sell_price_krw = 0.0
            sell_price_usd = 0.0
            for item in order_data.get('line_items', []):
                if item.get('sku') == sku:
                    try:
                        sell_price_krw = float(
                            item.get('price_set', {})
                            .get('shop_money', {})
                            .get('amount', 0) or item.get('price', 0)
                        )
                    except (TypeError, ValueError):
                        sell_price_krw = 0.0
                    try:
                        sell_price_usd = float(
                            item.get('price_set', {})
                            .get('presentment_money', {})
                            .get('amount', 0) or 0
                        )
                    except (TypeError, ValueError):
                        sell_price_usd = 0.0
                    break

            margin_pct = self._calc_margin_pct(float(buy_price), sell_price_krw)

            row = {
                'order_id': order_id,
                'order_number': order_number,
                'customer_name': customer_name,
                'customer_email': customer_email,
                'order_date': order_date,
                'sku': sku,
                'vendor': vendor,
                'forwarder': forwarder,
                'buy_price': buy_price,
                'buy_currency': buy_currency,
                'sell_price_krw': sell_price_krw,
                'sell_price_usd': sell_price_usd,
                'margin_pct': margin_pct,
                'status': self.STATUS_ROUTED,
                'status_updated_at': now,
                'tracking_number': '',
                'carrier': '',
                'notes': '',
            }
            ws.append_row([row[h] for h in ORDER_HEADERS])
            recorded.append(row)

        return recorded[0] if len(recorded) == 1 else recorded

    def update_status(
        self,
        order_id,
        sku: str,
        new_status: str,
        tracking_number: str = '',
        carrier: str = '',
        notes: str = '',
    ) -> dict:
        """주문 상태 업데이트.

        - new_status 유효성 검증 (VALID_STATUSES)
        - status_updated_at 자동 갱신
        - tracking_number, carrier 업데이트 (값이 있는 경우)

        Returns: 업데이트된 행 딕셔너리
        """
        if new_status not in self.VALID_STATUSES:
            raise ValueError(
                f"유효하지 않은 status: '{new_status}'. "
                f"허용값: {self.VALID_STATUSES}"
            )

        ws = self._get_worksheet()
        rows = ws.get_all_values()
        if not rows:
            raise KeyError(f"order_id={order_id}, sku={sku} 행을 찾을 수 없습니다.")

        headers = rows[0]
        try:
            col_order_id = headers.index('order_id') + 1
            col_sku = headers.index('sku') + 1
            col_status = headers.index('status') + 1
            col_updated = headers.index('status_updated_at') + 1
            col_tracking = headers.index('tracking_number') + 1
            col_carrier = headers.index('carrier') + 1
            col_notes = headers.index('notes') + 1
        except ValueError as e:
            raise KeyError(f"시트 헤더 오류: {e}") from e

        now = self._now_iso()
        for row_idx, row in enumerate(rows[1:], start=2):
            if str(row[col_order_id - 1]) == str(order_id) and str(row[col_sku - 1]) == str(sku):
                ws.update_cell(row_idx, col_status, new_status)
                ws.update_cell(row_idx, col_updated, now)
                if tracking_number:
                    ws.update_cell(row_idx, col_tracking, tracking_number)
                if carrier:
                    ws.update_cell(row_idx, col_carrier, carrier)
                if notes:
                    ws.update_cell(row_idx, col_notes, notes)

                # 갱신된 행 반환
                updated_row = dict(zip(headers, row))
                updated_row['status'] = new_status
                updated_row['status_updated_at'] = now
                if tracking_number:
                    updated_row['tracking_number'] = tracking_number
                if carrier:
                    updated_row['carrier'] = carrier
                if notes:
                    updated_row['notes'] = notes
                return updated_row

        raise KeyError(f"order_id={order_id}, sku={sku} 행을 찾을 수 없습니다.")

    def get_orders_by_status(self, status: str) -> list[dict]:
        """특정 상태의 주문 목록 반환."""
        rows = self._get_all_rows()
        return [r for r in rows if str(r.get('status', '')) == status]

    def get_order_history(self, order_id) -> list[dict]:
        """특정 주문의 전체 히스토리 (모든 SKU) 반환."""
        rows = self._get_all_rows()
        return [r for r in rows if str(r.get('order_id', '')) == str(order_id)]

    def get_pending_orders(self) -> list[dict]:
        """아직 배송 완료되지 않은 모든 주문 반환.

        (status가 delivered, cancelled가 아닌 것들)
        """
        rows = self._get_all_rows()
        return [r for r in rows if str(r.get('status', '')) not in _PENDING_EXCLUDE]

    def get_stats(self) -> dict:
        """전체 주문 상태별 통계.

        Returns:
        {
            'total': 150,
            'by_status': {'new': 5, 'routed': 10, ...},
            'by_vendor': {'porter': 80, 'memo_paris': 70},
            'avg_processing_days': 3.5,
        }
        """
        rows = self._get_all_rows()
        total = len(rows)
        by_status: dict[str, int] = {}
        by_vendor: dict[str, int] = {}
        processing_days: list[float] = []

        for r in rows:
            status = str(r.get('status', ''))
            vendor = str(r.get('vendor', '')).lower()
            by_status[status] = by_status.get(status, 0) + 1
            if vendor:
                by_vendor[vendor] = by_vendor.get(vendor, 0) + 1

            # 평균 처리 일수: order_date → status_updated_at (완료 주문만)
            if status in (self.STATUS_DELIVERED, self.STATUS_SHIPPED_DOMESTIC):
                try:
                    order_date = datetime.fromisoformat(
                        str(r.get('order_date', '')).replace('Z', '+00:00')
                    )
                    updated_at = datetime.fromisoformat(
                        str(r.get('status_updated_at', '')).replace('Z', '+00:00')
                    )
                    delta = (updated_at - order_date).total_seconds() / 86400
                    if delta >= 0:
                        processing_days.append(delta)
                except (ValueError, TypeError):
                    pass

        avg_days = round(sum(processing_days) / len(processing_days), 1) if processing_days else 0.0

        return {
            'total': total,
            'by_status': by_status,
            'by_vendor': by_vendor,
            'avg_processing_days': avg_days,
        }
