"""src/analytics/sales_analytics.py — Phase 29: Sales Analytics."""

import random


class SalesAnalytics:
    """매출 분석 클래스 (mock 데이터 기반)."""

    # ──────────────────────────────────────────────
    # Internal mock helpers
    # ──────────────────────────────────────────────

    def _mock_orders(self, n: int, base_revenue: float = 300000.0) -> list:
        random.seed(42)
        return [
            {
                'order_id': str(1000 + i),
                'amount': round(base_revenue * (0.8 + random.random() * 0.4), 0),
                'channel': random.choice(['shopify', 'woocommerce', 'naver']),
            }
            for i in range(n)
        ]

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def daily_summary(self, date: str = None) -> dict:
        """일별 매출 요약."""
        if date is None:
            date = str(__import__('datetime').date.today())
        orders = self._mock_orders(n=12)
        revenue = sum(o['amount'] for o in orders)
        order_count = len(orders)
        avg = round(revenue / order_count, 2) if order_count else 0.0
        return {
            'date': date,
            'revenue': revenue,
            'orders': order_count,
            'avg_order_value': avg,
        }

    def weekly_summary(self, year: int = None, week: int = None) -> dict:
        """주별 매출 요약."""
        today = __import__('datetime').date.today()
        if year is None:
            year = today.isocalendar()[0]
        if week is None:
            week = today.isocalendar()[1]
        orders = self._mock_orders(n=84)
        revenue = sum(o['amount'] for o in orders)
        order_count = len(orders)
        avg = round(revenue / order_count, 2) if order_count else 0.0
        return {
            'year': year,
            'week': week,
            'revenue': revenue,
            'orders': order_count,
            'avg_order_value': avg,
        }

    def monthly_summary(self, year: int = None, month: int = None) -> dict:
        """월별 매출 요약."""
        today = __import__('datetime').date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month
        orders = self._mock_orders(n=360)
        revenue = sum(o['amount'] for o in orders)
        order_count = len(orders)
        avg = round(revenue / order_count, 2) if order_count else 0.0
        return {
            'year': year,
            'month': month,
            'revenue': revenue,
            'orders': order_count,
            'avg_order_value': avg,
        }

    def channel_comparison(self, channels: list, start_date: str, end_date: str) -> dict:
        """채널별 매출 비교."""
        random.seed(99)
        result = {}
        for ch in channels:
            n = random.randint(5, 30)
            orders = self._mock_orders(n=n, base_revenue=250000.0)
            revenue = sum(o['amount'] for o in orders)
            result[ch] = {
                'revenue': revenue,
                'orders': n,
                'avg_order_value': round(revenue / n, 2),
                'start_date': start_date,
                'end_date': end_date,
            }
        return result

    def trend_analysis(self, period: str = '30d') -> dict:
        """트렌드 분석 (성장률 및 상위 상품)."""
        days = int(period.rstrip('d')) if period.endswith('d') else 30
        random.seed(7)
        daily_revenues = [
            round(280000.0 * (0.9 + random.random() * 0.2) * (1 + i * 0.003), 2)
            for i in range(days)
        ]
        if len(daily_revenues) >= 2:
            growth_rate = round(
                (daily_revenues[-1] - daily_revenues[0]) / daily_revenues[0] * 100, 2
            )
        else:
            growth_rate = 0.0
        top_products = [
            {'product_id': f'PROD-{100 + i}', 'revenue': round(daily_revenues[i % days] * 3, 2)}
            for i in range(5)
        ]
        top_products.sort(key=lambda x: x['revenue'], reverse=True)
        return {
            'period': period,
            'days': days,
            'growth_rate_pct': growth_rate,
            'daily_revenues': daily_revenues,
            'top_products': top_products,
        }
