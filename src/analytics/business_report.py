"""Phase 7: 고급 비즈니스 분석 모듈.

RevenueReporter를 확장하여 국가별/브랜드별/채널별 분석,
트렌드 분석(이동평균), 성장률 계산 기능을 제공한다.
"""

import logging
from datetime import date, timedelta

from ..dashboard.revenue_report import RevenueReporter

logger = logging.getLogger(__name__)


class BusinessAnalytics(RevenueReporter):
    """고급 비즈니스 분석 — RevenueReporter 확장.

    추가 분석 메서드:
      - by_country: 국가별 매출/마진/AOV 분석
      - by_brand: 브랜드별 매출/마진/회전율 분석
      - trend_analysis: 매출 추이 + 이동평균 + 성장률
      - channel_efficiency: 채널별 ROI 추정
    """

    # ── 국가별 분석 ─────────────────────────────────────────

    def by_country(self, start: str = None, end: str = None) -> dict:
        """국가별 매출/마진/AOV 분석.

        Args:
            start: 시작 날짜 'YYYY-MM-DD'. end와 함께 사용.
            end: 종료 날짜 'YYYY-MM-DD' (포함하지 않음).

        Returns:
            {'KR': {'orders': 10, 'revenue_krw': 3000000, 'margin_pct': 22.0, 'aov_krw': 300000}, ...}
        """
        if start and end:
            rows = self._rows_for_range(
                date.fromisoformat(start), date.fromisoformat(end)
            )
        else:
            rows = self._tracker._get_all_rows()

        country_rows: dict[str, list] = {}
        for r in rows:
            country = (
                str(r.get('shipping_country', '') or r.get('destination_country', '') or '').upper()
            )
            if not country:
                country = 'UNKNOWN'
            country_rows.setdefault(country, []).append(r)

        result = {}
        for country, crows in country_rows.items():
            agg = self._aggregate(crows)
            aov = (
                round(agg['revenue_krw'] / agg['orders'])
                if agg['orders'] > 0 else 0
            )
            result[country] = {
                'orders': agg['orders'],
                'revenue_krw': agg['revenue_krw'],
                'margin_pct': agg['margin_pct'],
                'aov_krw': aov,
            }
        return result

    # ── 브랜드별 분석 ────────────────────────────────────────

    def by_brand(self, start: str = None, end: str = None) -> dict:
        """브랜드별 매출/마진/회전율 분석.

        SKU 접두어(PTR → PORTER, MMP → MEMO_PARIS) 또는 vendor 필드 기반.

        Args:
            start: 시작 날짜 'YYYY-MM-DD'.
            end: 종료 날짜 'YYYY-MM-DD' (포함하지 않음).

        Returns:
            {'PORTER': {'orders': 5, 'revenue_krw': ..., 'margin_pct': ...,
                        'unique_skus': 3, 'turnover_rate': 1.67}, ...}
        """
        if start and end:
            rows = self._rows_for_range(
                date.fromisoformat(start), date.fromisoformat(end)
            )
        else:
            rows = self._tracker._get_all_rows()

        brand_rows: dict[str, list] = {}
        for r in rows:
            vendor = str(r.get('vendor', '') or '').upper()
            sku = str(r.get('sku', '') or '')
            prefix = sku.split('-')[0].upper() if '-' in sku else ''
            brand = vendor or prefix or 'UNKNOWN'
            brand_rows.setdefault(brand, []).append(r)

        result = {}
        for brand, brows in brand_rows.items():
            agg = self._aggregate(brows)
            unique_skus = len({r.get('sku', '') for r in brows if r.get('sku')})
            result[brand] = {
                'orders': agg['orders'],
                'revenue_krw': agg['revenue_krw'],
                'margin_pct': agg['margin_pct'],
                'unique_skus': unique_skus,
                'turnover_rate': round(agg['orders'] / unique_skus, 2) if unique_skus > 0 else 0.0,
            }
        return result

    # ── 트렌드 분석 ──────────────────────────────────────────

    def trend_analysis(self, days: int = 30) -> dict:
        """최근 N일 매출 추이 + 7일 이동평균 + 성장률 + 계절성.

        Args:
            days: 분석 기간 (기본 30일).

        Returns:
            {
              'period_days': 30,
              'current_period': {...},
              'prev_period': {...},
              'growth_pct': 5.2,
              'daily_series': [{'date': ..., 'revenue_krw': ..., 'orders': ...}, ...],
              'moving_avg_7d': [None, None, ..., 1234567],
              'monthly_seasonality': {'1': 2000000, '2': 1800000, ...},
            }
        """
        today = date.today()
        current_start = today - timedelta(days=days)
        prev_start = current_start - timedelta(days=days)

        current_rows = self._rows_for_range(current_start, today + timedelta(days=1))
        prev_rows = self._rows_for_range(prev_start, current_start)

        # 일별 매출 시리즈
        daily_series = []
        for i in range(days):
            day = current_start + timedelta(days=i)
            day_rows = [
                r for r in current_rows
                if self._parse_date(r.get('order_date', '')) == day
            ]
            day_agg = self._aggregate(day_rows)
            daily_series.append({
                'date': str(day),
                'revenue_krw': day_agg['revenue_krw'],
                'orders': day_agg['orders'],
            })

        # 7일 이동평균
        window = 7
        moving_avg = []
        for i, _ in enumerate(daily_series):
            if i < window - 1:
                moving_avg.append(None)
            else:
                avg = sum(d['revenue_krw'] for d in daily_series[i - window + 1:i + 1]) / window
                moving_avg.append(round(avg))

        current_agg = self._aggregate(current_rows)
        prev_agg = self._aggregate(prev_rows)

        growth_pct = 0.0
        if prev_agg['revenue_krw'] > 0:
            growth_pct = round(
                (current_agg['revenue_krw'] - prev_agg['revenue_krw'])
                / prev_agg['revenue_krw'] * 100, 1
            )

        # 월별 계절성 (전체 데이터 기반)
        monthly_map: dict[int, float] = {}
        all_rows = self._tracker._get_all_rows()
        for r in all_rows:
            d = self._parse_date(r.get('order_date', ''))
            if d:
                monthly_map.setdefault(d.month, 0.0)
                try:
                    monthly_map[d.month] += float(r.get('sell_price_krw', 0) or 0)
                except (TypeError, ValueError):
                    pass

        return {
            'period_days': days,
            'current_period': {
                'start': str(current_start),
                'end': str(today),
                'revenue_krw': current_agg['revenue_krw'],
                'orders': current_agg['orders'],
                'margin_pct': current_agg['margin_pct'],
            },
            'prev_period': {
                'start': str(prev_start),
                'end': str(current_start - timedelta(days=1)),
                'revenue_krw': prev_agg['revenue_krw'],
                'orders': prev_agg['orders'],
            },
            'growth_pct': growth_pct,
            'daily_series': daily_series,
            'moving_avg_7d': moving_avg,
            'monthly_seasonality': {
                str(k): round(v) for k, v in sorted(monthly_map.items())
            },
        }

    # ── 채널 효율 분석 ────────────────────────────────────────

    def channel_efficiency(self, start: str = None, end: str = None) -> dict:
        """채널별 ROI 추정 및 효율 분석.

        채널별(Shopify, WooCommerce, Coupang, Naver) 주문 수, 매출, 마진, AOV.

        Args:
            start: 시작 날짜 'YYYY-MM-DD'.
            end: 종료 날짜 'YYYY-MM-DD' (포함하지 않음).

        Returns:
            {'shopify': {'orders': 8, 'revenue_krw': ..., 'margin_pct': ..., 'aov_krw': ...}, ...}
        """
        if start and end:
            rows = self._rows_for_range(
                date.fromisoformat(start), date.fromisoformat(end)
            )
        else:
            rows = self._tracker._get_all_rows()

        channel_rows: dict[str, list] = {}
        for r in rows:
            ch = self._detect_channel(r)
            channel_rows.setdefault(ch, []).append(r)

        result = {}
        for ch, crows in channel_rows.items():
            agg = self._aggregate(crows)
            aov = round(agg['revenue_krw'] / agg['orders']) if agg['orders'] > 0 else 0
            result[ch] = {
                'orders': agg['orders'],
                'revenue_krw': agg['revenue_krw'],
                'margin_pct': agg['margin_pct'],
                'aov_krw': aov,
            }
        return result

    # ── 내부 헬퍼 ────────────────────────────────────────────

    @staticmethod
    def _detect_channel(row: dict) -> str:
        """주문 행에서 판매 채널 감지.

        channel 필드 → order_number 패턴 → sell_price_usd 유무 순서로 판별.
        """
        channel = str(row.get('channel', '') or '').lower()
        if channel:
            return channel
        order_number = str(row.get('order_number', '') or '').lower()
        if 'coup' in order_number or 'coupang' in order_number:
            return 'coupang'
        if 'naver' in order_number or 'smart' in order_number:
            return 'naver'
        try:
            usd = float(row.get('sell_price_usd', 0) or 0)
        except (TypeError, ValueError):
            usd = 0.0
        return 'shopify' if usd > 0 else 'woocommerce'
