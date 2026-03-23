"""Phase 7: 자동 재주문 알림 엔진.

재고 부족 + 판매 속도(일일 판매량) + 벤더 리드타임을 기반으로
재주문 시점을 예측하고 알림을 발송한다.
"""

import logging
import os
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# 벤더별 기본 리드타임 (일)
_VENDOR_LEAD_DAYS = {
    'porter': int(os.getenv('PORTER_LEAD_DAYS', '7')),
    'memo_paris': int(os.getenv('MEMO_LEAD_DAYS', '10')),
}
_DEFAULT_LEAD_DAYS = 7


class ReorderAlertEngine:
    """재고 부족 + 판매 속도 기반 자동 재주문 알림 엔진.

    환경변수:
      REORDER_CHECK_ENABLED       — 활성화 여부 (기본 1)
      SALES_VELOCITY_DAYS         — 판매 속도 계산 기간 일수 (기본 30)
      SAFETY_STOCK_DAYS           — 안전재고 일수 (기본 3)
      PORTER_LEAD_DAYS            — 포터 리드타임 일수 (기본 7)
      MEMO_LEAD_DAYS              — 메모파리 리드타임 일수 (기본 10)
      REORDER_SUGGESTIONS_WORKSHEET — Sheets 워크시트명 (기본 reorder_suggestions)
    """

    def __init__(self, sheet_id: str = None, catalog_worksheet: str = None,
                 orders_worksheet: str = None):
        """초기화.

        Args:
            sheet_id: Google Sheet ID.
            catalog_worksheet: 카탈로그 워크시트명.
            orders_worksheet: 주문 워크시트명.
        """
        self._sheet_id = sheet_id or os.getenv('GOOGLE_SHEET_ID', '')
        self._catalog_ws = catalog_worksheet or os.getenv('WORKSHEET', 'catalog')
        self._orders_ws = orders_worksheet or os.getenv('ORDERS_WORKSHEET', 'orders')
        self._velocity_days = int(os.getenv('SALES_VELOCITY_DAYS', '30'))
        self._safety_days = int(os.getenv('SAFETY_STOCK_DAYS', '3'))

    # ── 공개 API ─────────────────────────────────────────────

    def sales_velocity(self, days: int = None) -> dict:
        """SKU별 일일 평균 판매량 계산.

        최근 N일의 주문 데이터를 집계하여 SKU별 일일 평균 판매량을 반환한다.

        Args:
            days: 분석 기간 일수 (기본 SALES_VELOCITY_DAYS 환경변수).

        Returns:
            {'PTR-TNK-001': 0.5, 'MMP-EDP-001': 0.3, ...}
        """
        if days is None:
            days = self._velocity_days

        today = date.today()
        start = today - timedelta(days=days)
        rows = self._get_order_rows()

        sku_daily: dict[str, dict] = {}
        for r in rows:
            order_date_str = str(r.get('order_date', '') or '')[:10]
            try:
                order_date = date.fromisoformat(order_date_str)
            except (ValueError, TypeError):
                continue
            if not (start <= order_date <= today):
                continue
            sku = str(r.get('sku', '') or '')
            if not sku:
                continue
            sku_daily.setdefault(sku, {})
            ds = str(order_date)
            sku_daily[sku][ds] = sku_daily[sku].get(ds, 0) + 1

        result = {}
        for sku, daily_counts in sku_daily.items():
            total = sum(daily_counts.values())
            result[sku] = round(total / days, 3) if days > 0 else 0.0

        return result

    def reorder_point(self, sku: str, daily_sales: float, vendor: str = None) -> dict:
        """재주문 시점(재주문 필요 재고량) 계산.

        재주문 포인트 = (리드타임 + 안전재고) × 일일 판매량

        Args:
            sku: 상품 SKU.
            daily_sales: 일일 평균 판매량.
            vendor: 벤더명 (리드타임 결정용).

        Returns:
            {'sku': ..., 'vendor': ..., 'daily_sales': ...,
             'lead_days': ..., 'safety_stock_days': ..., 'reorder_point_qty': ...}
        """
        vendor_lower = str(vendor or '').lower()
        lead_days = _VENDOR_LEAD_DAYS.get(vendor_lower, _DEFAULT_LEAD_DAYS)
        reorder_qty = (lead_days + self._safety_days) * daily_sales

        return {
            'sku': sku,
            'vendor': vendor_lower,
            'daily_sales': daily_sales,
            'lead_days': lead_days,
            'safety_stock_days': self._safety_days,
            'reorder_point_qty': round(reorder_qty, 1),
        }

    def generate_suggestions(self) -> list:
        """재주문이 필요한 SKU 목록 + 추천 발주 수량 생성.

        재고 소진 예상일이 (리드타임 + 안전재고일) 미만인 SKU를
        긴급 순(재고소진예상일 오름차순)으로 정렬하여 반환한다.

        Returns:
            list of dicts sorted by urgency (days_until_stockout ascending)
        """
        catalog = self._get_catalog_rows()
        velocity = self.sales_velocity()
        suggestions = []

        for row in catalog:
            sku = str(row.get('sku', '') or '')
            if not sku:
                continue
            try:
                stock = int(row.get('stock', 0) or 0)
            except (TypeError, ValueError):
                stock = 0

            daily_sales = velocity.get(sku, 0.0)
            if daily_sales <= 0:
                continue  # 판매 실적 없는 상품 제외

            vendor = str(row.get('vendor', '') or '').lower()
            lead_days = _VENDOR_LEAD_DAYS.get(vendor, _DEFAULT_LEAD_DAYS)
            days_until_stockout = round(stock / daily_sales) if daily_sales > 0 else 9999
            reorder_needed = days_until_stockout < (lead_days + self._safety_days)

            if reorder_needed:
                recommended_qty = max(
                    round((lead_days + self._safety_days) * daily_sales), 1
                )
                suggestions.append({
                    'sku': sku,
                    'vendor': vendor,
                    'current_stock': stock,
                    'daily_sales': daily_sales,
                    'days_until_stockout': days_until_stockout,
                    'lead_days': lead_days,
                    'recommended_qty': recommended_qty,
                    'urgent': days_until_stockout < lead_days,
                })

        return sorted(suggestions, key=lambda x: x['days_until_stockout'])

    def send_alerts(self, suggestions: list):
        """재주문 알림 텔레그램 발송.

        Args:
            suggestions: generate_suggestions() 반환값.
        """
        if not suggestions:
            return

        urgent = [s for s in suggestions if s['urgent']]
        lines = [
            f"📦 [재주문 알림] {len(suggestions)}개 SKU 재주문 필요",
            f"긴급: {len(urgent)}개",
            "",
        ]
        for s in suggestions[:10]:
            flag = "🚨" if s['urgent'] else "⚠️"
            lines.append(
                f"{flag} {s['sku']} ({s['vendor']}): "
                f"재고 {s['current_stock']}개, {s['days_until_stockout']}일 후 소진 "
                f"→ 추천 발주: {s['recommended_qty']}개"
            )
        msg = "\n".join(lines)

        if os.getenv('TELEGRAM_ENABLED', '1') == '1':
            try:
                from ..utils.telegram import send_tele
                send_tele(msg)
                logger.info("Reorder alert sent via Telegram")
            except Exception as exc:
                logger.warning("Telegram send failed: %s", exc)

    def run(self) -> dict:
        """메인 진입점: 재주문 알림 체크 + Sheets 기록 + 텔레그램 발송.

        Returns:
            {'total_suggestions': int, 'urgent': int, 'suggestions': list}
            or {'skipped': True} if disabled.
        """
        enabled = os.getenv('REORDER_CHECK_ENABLED', '1') == '1'
        if not enabled:
            logger.info("REORDER_CHECK_ENABLED=0, skipping")
            return {'skipped': True}

        suggestions = self.generate_suggestions()
        self._write_suggestions_to_sheets(suggestions)
        self.send_alerts(suggestions)

        return {
            'total_suggestions': len(suggestions),
            'urgent': len([s for s in suggestions if s['urgent']]),
            'suggestions': suggestions,
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    def _get_order_rows(self) -> list:
        """주문 데이터 로드."""
        if not self._sheet_id:
            return []
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._orders_ws)
            return ws.get_all_records()
        except Exception as exc:
            logger.error("Failed to load orders: %s", exc)
            return []

    def _get_catalog_rows(self) -> list:
        """카탈로그 데이터 로드."""
        if not self._sheet_id:
            return []
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._catalog_ws)
            return ws.get_all_records()
        except Exception as exc:
            logger.error("Failed to load catalog: %s", exc)
            return []

    def _write_suggestions_to_sheets(self, suggestions: list):
        """재주문 제안을 Google Sheets reorder_suggestions 워크시트에 기록."""
        if not self._sheet_id or not suggestions:
            return
        worksheet = os.getenv('REORDER_SUGGESTIONS_WORKSHEET', 'reorder_suggestions')
        try:
            from ..utils.sheets import open_sheet
            from datetime import datetime, timezone
            ws = open_sheet(self._sheet_id, worksheet)
            headers = [
                'recorded_at', 'sku', 'vendor', 'current_stock',
                'daily_sales', 'days_until_stockout', 'recommended_qty', 'urgent',
            ]
            existing = ws.get_all_values()
            if not existing or existing[0] != headers:
                ws.clear()
                ws.append_row(headers)
            now_str = datetime.now(timezone.utc).isoformat()
            for s in suggestions:
                ws.append_row([
                    now_str, s['sku'], s['vendor'], s['current_stock'],
                    s['daily_sales'], s['days_until_stockout'], s['recommended_qty'],
                    'Y' if s.get('urgent') else 'N',
                ])
            logger.info("Reorder suggestions written to Sheets (%d rows)", len(suggestions))
        except Exception as exc:
            logger.warning("Failed to write reorder suggestions to Sheets: %s", exc)
