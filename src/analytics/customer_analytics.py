"""src/analytics/customer_analytics.py — Phase 29: Customer Analytics."""

from datetime import date


class CustomerAnalytics:
    """고객 분석 클래스 (RFM, 코호트, LTV)."""

    # ──────────────────────────────────────────────
    # RFM Analysis
    # ──────────────────────────────────────────────

    def rfm_analysis(self, orders: list) -> list:
        """RFM 분석.

        Args:
            orders: [{'customer_id', 'order_date', 'amount'}, ...]

        Returns:
            [{'customer_id', 'recency_days', 'frequency', 'monetary',
              'rfm_score', 'segment'}, ...]
        """
        from collections import defaultdict
        today = date.today()

        customer_data: dict = defaultdict(lambda: {'dates': [], 'amounts': []})
        for order in orders:
            cid = order['customer_id']
            odate = order['order_date']
            if isinstance(odate, str):
                odate = date.fromisoformat(odate[:10])
            customer_data[cid]['dates'].append(odate)
            customer_data[cid]['amounts'].append(float(order['amount']))

        results = []
        for cid, info in customer_data.items():
            last_date = max(info['dates'])
            recency = (today - last_date).days
            frequency = len(info['dates'])
            monetary = sum(info['amounts'])

            r_score = self._score_recency(recency)
            f_score = self._score_frequency(frequency)
            m_score = self._score_monetary(monetary)
            rfm_score = r_score * 100 + f_score * 10 + m_score

            segment = self._assign_segment(r_score, f_score, m_score)
            results.append({
                'customer_id': cid,
                'recency_days': recency,
                'frequency': frequency,
                'monetary': round(monetary, 2),
                'rfm_score': rfm_score,
                'segment': segment,
            })
        return results

    def _score_recency(self, days: int) -> int:
        if days <= 30:
            return 5
        if days <= 60:
            return 4
        if days <= 90:
            return 3
        if days <= 180:
            return 2
        return 1

    def _score_frequency(self, count: int) -> int:
        if count >= 10:
            return 5
        if count >= 6:
            return 4
        if count >= 3:
            return 3
        if count >= 2:
            return 2
        return 1

    def _score_monetary(self, total: float) -> int:
        if total >= 1_000_000:
            return 5
        if total >= 500_000:
            return 4
        if total >= 200_000:
            return 3
        if total >= 100_000:
            return 2
        return 1

    def _assign_segment(self, r: int, f: int, m: int) -> str:
        if r >= 4 and f >= 4:
            return 'Champions'
        if f >= 3 and m >= 3:
            return 'Loyal'
        if r <= 2 and f >= 2:
            return 'At Risk'
        if r <= 2 and f <= 1:
            return 'Lost'
        return 'Promising'

    # ──────────────────────────────────────────────
    # Cohort Analysis
    # ──────────────────────────────────────────────

    def cohort_analysis(self, orders: list) -> dict:
        """코호트 분석 (첫 구매 월 기준).

        Returns:
            {cohort_month: {'customers': int, 'retention': {period: count}}}
        """
        from collections import defaultdict

        first_purchase: dict = {}
        cohort_map: dict = defaultdict(lambda: defaultdict(set))

        for order in orders:
            cid = order['customer_id']
            odate = order['order_date']
            if isinstance(odate, str):
                odate = date.fromisoformat(odate[:10])
            month_key = odate.strftime('%Y-%m')
            if cid not in first_purchase:
                first_purchase[cid] = month_key
            cohort_month = first_purchase[cid]
            cohort_map[cohort_month][month_key].add(cid)

        result = {}
        for cohort_month, periods in cohort_map.items():
            base_count = len(periods.get(cohort_month, set()))
            retention = {}
            for period, cids in sorted(periods.items()):
                retention[period] = len(cids)
            result[cohort_month] = {'customers': base_count, 'retention': retention}
        return result

    # ──────────────────────────────────────────────
    # LTV Estimate
    # ──────────────────────────────────────────────

    def ltv_estimate(self, customer_id: str, orders: list) -> float:
        """고객 생애 가치(LTV) 추정.

        단순 공식: avg_order_value × purchase_frequency_per_year × avg_lifespan_years
        """
        customer_orders = [
            o for o in orders if o['customer_id'] == customer_id
        ]
        if not customer_orders:
            return 0.0

        amounts = [float(o['amount']) for o in customer_orders]
        avg_order_value = sum(amounts) / len(amounts)

        dates = []
        for o in customer_orders:
            odate = o['order_date']
            if isinstance(odate, str):
                odate = date.fromisoformat(odate[:10])
            dates.append(odate)

        if len(dates) >= 2:
            span_days = (max(dates) - min(dates)).days or 1
            frequency_per_year = len(dates) / (span_days / 365.0)
        else:
            frequency_per_year = 1.0

        avg_lifespan_years = 3.0
        return round(avg_order_value * frequency_per_year * avg_lifespan_years, 2)
