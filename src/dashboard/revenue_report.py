"""매출/마진 분석 리포터 모듈."""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class RevenueReporter:
    """매출/마진 분석 리포터."""

    LOW_MARGIN_THRESHOLD = 15.0
    HIGH_MARGIN_THRESHOLD = 35.0

    def __init__(self, order_tracker=None):
        """OrderStatusTracker 인스턴스 주입 또는 새로 생성."""
        if order_tracker is None:
            from .order_status import OrderStatusTracker
            self._tracker = OrderStatusTracker()
        else:
            self._tracker = order_tracker

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _parse_date(self, row_date_str: str) -> date | None:
        """order_date 문자열을 date 객체로 변환."""
        if not row_date_str:
            return None
        try:
            return date.fromisoformat(str(row_date_str)[:10])
        except (ValueError, TypeError):
            return None

    def _rows_for_date(self, target: date) -> list[dict]:
        """특정 날짜에 생성된 주문 행 반환."""
        try:
            rows = self._tracker._get_all_rows()
        except Exception as exc:
            logger.warning("_rows_for_date() failed to fetch rows: %s", exc)
            return []
        return [r for r in rows if self._parse_date(r.get('order_date', '')) == target]

    def _rows_for_range(self, start: date, end: date) -> list[dict]:
        """날짜 범위 내 주문 행 반환 (start ≤ date < end)."""
        try:
            rows = self._tracker._get_all_rows()
        except Exception as exc:
            logger.warning("_rows_for_range() failed to fetch rows: %s", exc)
            return []
        result = []
        for r in rows:
            d = self._parse_date(r.get('order_date', ''))
            if d and start <= d < end:
                result.append(r)
        return result

    @staticmethod
    def _aggregate(rows: list[dict]) -> dict:
        """주문 행 목록에서 매출/비용/마진 집계."""
        total_orders = len(rows)
        total_revenue = 0.0
        total_cost = 0.0

        for r in rows:
            try:
                revenue = float(r.get('sell_price_krw', 0) or 0)
                cost = float(r.get('buy_price', 0) or 0)
            except (TypeError, ValueError):
                revenue = 0.0
                cost = 0.0
            total_revenue += revenue
            total_cost += cost

        gross_profit = total_revenue - total_cost
        margin_pct = (
            round(gross_profit / total_revenue * 100, 1)
            if total_revenue > 0 else 0.0
        )
        return {
            'orders': total_orders,
            'revenue_krw': round(total_revenue),
            'cost_krw': round(total_cost),
            'gross_profit_krw': round(gross_profit),
            'margin_pct': margin_pct,
        }

    @staticmethod
    def _by_vendor(rows: list[dict]) -> dict:
        vendor_rows: dict[str, list] = {}
        for r in rows:
            v = str(r.get('vendor', 'unknown')).lower()
            vendor_rows.setdefault(v, []).append(r)
        result = {}
        for v, vrows in vendor_rows.items():
            agg = RevenueReporter._aggregate(vrows)
            result[v] = {
                'orders': agg['orders'],
                'revenue_krw': agg['revenue_krw'],
                'cost_krw': agg['cost_krw'],
                'margin_pct': agg['margin_pct'],
            }
        return result

    @staticmethod
    def _by_channel(rows: list[dict]) -> dict:
        """채널별 집계 (order_number 접두어로 추정)."""
        channel_rows: dict[str, list] = {}
        for r in rows:
            # 간단한 추정: sell_price_usd > 0 이면 shopify, 아니면 woocommerce
            try:
                usd = float(r.get('sell_price_usd', 0) or 0)
            except (TypeError, ValueError):
                usd = 0.0
            ch = 'shopify' if usd > 0 else 'woocommerce'
            channel_rows.setdefault(ch, []).append(r)
        result = {}
        for ch, crows in channel_rows.items():
            agg = RevenueReporter._aggregate(crows)
            result[ch] = {'orders': agg['orders'], 'revenue_krw': agg['revenue_krw']}
        return result

    @staticmethod
    def _top_products(rows: list[dict], n: int = 5) -> list[dict]:
        """SKU별 매출 상위 N개 상품."""
        sku_map: dict[str, dict] = {}
        for r in rows:
            sku = str(r.get('sku', ''))
            if not sku:
                continue
            if sku not in sku_map:
                sku_map[sku] = {'sku': sku, 'title': str(r.get('title', '')), 'sold': 0, 'revenue_krw': 0.0}
            sku_map[sku]['sold'] += 1
            try:
                sku_map[sku]['revenue_krw'] += float(r.get('sell_price_krw', 0) or 0)
            except (TypeError, ValueError):
                pass
        sorted_skus = sorted(sku_map.values(), key=lambda x: x['revenue_krw'], reverse=True)
        for item in sorted_skus:
            item['revenue_krw'] = round(item['revenue_krw'])
        return sorted_skus[:n]

    # ── 공개 API ────────────────────────────────────────────

    def daily_revenue(self, date_str: str = None) -> dict:
        """특정 일자의 매출 요약.

        date_str: 'YYYY-MM-DD' 형식. None이면 오늘.
        """
        target = (
            date.fromisoformat(date_str) if date_str else date.today()
        )
        rows = self._rows_for_date(target)
        agg = self._aggregate(rows)

        return {
            'date': str(target),
            'total_orders': agg['orders'],
            'total_revenue_krw': agg['revenue_krw'],
            'total_cost_krw': agg['cost_krw'],
            'gross_profit_krw': agg['gross_profit_krw'],
            'gross_margin_pct': agg['margin_pct'],
            'by_vendor': self._by_vendor(rows),
            'by_channel': self._by_channel(rows),
            'top_products': self._top_products(rows),
        }

    def weekly_revenue(self, week_start: str = None) -> dict:
        """주간 매출 요약.

        week_start: 'YYYY-MM-DD' (월요일). None이면 이번 주 월요일.
        """
        if week_start:
            start = date.fromisoformat(week_start)
        else:
            today = date.today()
            start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)

        rows = self._rows_for_range(start, end)
        agg = self._aggregate(rows)

        # 일별 분해
        daily: list[dict] = []
        for i in range(7):
            day = start + timedelta(days=i)
            day_rows = [r for r in rows if self._parse_date(r.get('order_date', '')) == day]
            day_agg = self._aggregate(day_rows)
            daily.append({'date': str(day), 'orders': day_agg['orders'], 'revenue_krw': day_agg['revenue_krw']})

        return {
            'week_start': str(start),
            'week_end': str(end - timedelta(days=1)),
            'total_orders': agg['orders'],
            'total_revenue_krw': agg['revenue_krw'],
            'total_cost_krw': agg['cost_krw'],
            'gross_profit_krw': agg['gross_profit_krw'],
            'gross_margin_pct': agg['margin_pct'],
            'by_vendor': self._by_vendor(rows),
            'daily': daily,
        }

    def monthly_revenue(self, year_month: str = None) -> dict:
        """월간 매출 요약.

        year_month: 'YYYY-MM'. None이면 이번 달.
        """
        if year_month:
            year, month = map(int, year_month.split('-'))
        else:
            today = date.today()
            year, month = today.year, today.month

        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)

        rows = self._rows_for_range(start, end)
        agg = self._aggregate(rows)

        return {
            'year_month': f"{year:04d}-{month:02d}",
            'total_orders': agg['orders'],
            'total_revenue_krw': agg['revenue_krw'],
            'total_cost_krw': agg['cost_krw'],
            'gross_profit_krw': agg['gross_profit_krw'],
            'gross_margin_pct': agg['margin_pct'],
            'by_vendor': self._by_vendor(rows),
            'by_channel': self._by_channel(rows),
            'top_products': self._top_products(rows),
        }

    @staticmethod
    def _sku_to_category(sku: str) -> str:
        """SKU 접두어에서 카테고리 추출.

        Expected SKU format: {VENDOR}-{CATEGORY}-{NUM} (e.g. PTR-TNK-100000)
        Returns 'other' if the SKU does not match the expected format.
        """
        parts = sku.split('-')
        if len(parts) >= 2 and parts[1]:
            return parts[1].lower()
        return 'other'

    def margin_analysis(self) -> dict:
        """전체 마진 분석.

        Returns:
        {
            'overall_margin_pct': 25.5,
            'by_vendor': {'porter': 22.0, 'memo_paris': 30.0},
            'by_category': {'bag': 20.0, 'perfume': 32.0},
            'low_margin_products': [...],
            'high_margin_products': [...],
        }
        """
        rows = self._tracker._get_all_rows()
        agg = self._aggregate(rows)

        # 벤더별 마진
        vendor_map: dict[str, list] = {}
        category_map: dict[str, list] = {}

        low_margin: list[dict] = []
        high_margin: list[dict] = []

        for r in rows:
            vendor = str(r.get('vendor', 'unknown')).lower()
            vendor_map.setdefault(vendor, []).append(r)

            sku = str(r.get('sku', ''))
            # Use dedicated method to safely extract category from SKU
            cat = self._sku_to_category(sku)
            category_map.setdefault(cat, []).append(r)

            try:
                mp = float(r.get('margin_pct', 0) or 0)
            except (TypeError, ValueError):
                mp = 0.0

            product_entry = {'sku': sku, 'vendor': vendor, 'margin_pct': mp}
            if mp < self.LOW_MARGIN_THRESHOLD and mp != 0:
                low_margin.append(product_entry)
            elif mp >= self.HIGH_MARGIN_THRESHOLD:
                high_margin.append(product_entry)

        by_vendor = {}
        for v, vrows in vendor_map.items():
            vagg = self._aggregate(vrows)
            by_vendor[v] = vagg['margin_pct']

        by_category = {}
        for cat, crows in category_map.items():
            cagg = self._aggregate(crows)
            by_category[cat] = cagg['margin_pct']

        return {
            'overall_margin_pct': agg['margin_pct'],
            'by_vendor': by_vendor,
            'by_category': by_category,
            'low_margin_products': sorted(low_margin, key=lambda x: x['margin_pct']),
            'high_margin_products': sorted(high_margin, key=lambda x: x['margin_pct'], reverse=True),
        }

    def currency_impact(self) -> dict:
        """환율 변동이 마진에 미치는 영향 분석.

        현재 환율 vs 주문 시점 환율 비교.
        현재 구현: 환경변수 기반 현재 환율과 buy_currency를 사용해 추정.
        """
        import os

        rows = self._tracker._get_all_rows()

        fx_current = {
            'JPYKRW': float(os.getenv('FX_JPYKRW', '9.0')),
            'EURKRW': float(os.getenv('FX_EURKRW', '1470')),
            'USDKRW': float(os.getenv('FX_USDKRW', '1350')),
        }

        impacts: list[dict] = []
        for r in rows:
            currency = str(r.get('buy_currency', '')).upper()
            fx_key = f"{currency}KRW"
            if fx_key not in fx_current:
                continue
            try:
                buy_price = float(r.get('buy_price', 0) or 0)
                sell_krw = float(r.get('sell_price_krw', 0) or 0)
                margin_recorded = float(r.get('margin_pct', 0) or 0)
            except (TypeError, ValueError):
                continue

            current_cost_krw = buy_price * fx_current[fx_key]
            current_margin_pct = (
                round((sell_krw - current_cost_krw) / sell_krw * 100, 2)
                if sell_krw > 0 else 0.0
            )
            margin_delta = round(current_margin_pct - margin_recorded, 2)
            impacts.append({
                'sku': r.get('sku', ''),
                'currency': currency,
                'fx_current': fx_current[fx_key],
                'margin_at_order': margin_recorded,
                'margin_current': current_margin_pct,
                'margin_delta': margin_delta,
            })

        return {
            'fx_current': fx_current,
            'impacts': impacts,
            'avg_margin_delta': (
                round(sum(i['margin_delta'] for i in impacts) / len(impacts), 2)
                if impacts else 0.0
            ),
        }
