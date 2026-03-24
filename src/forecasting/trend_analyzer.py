"""src/forecasting/trend_analyzer.py — 트렌드 분석.

판매 추세, 이상치 감지, 상품 성과 등급 분류.
stdlib statistics 모듈만 사용.
"""

import logging
import statistics

logger = logging.getLogger(__name__)

# 상품 성과 등급
GRADES = {
    'Star': '성장률 높고 판매량도 높은 스타 상품',
    'Cash Cow': '성장률 낮지만 판매량 높은 캐시카우 상품',
    'Rising': '성장률 높지만 판매량 낮은 성장 상품',
    'Declining': '성장률도 낮고 판매량도 낮은 쇠퇴 상품',
}


class TrendAnalyzer:
    """판매 트렌드 분석기."""

    def __init__(self):
        self._predictor = None

    def _get_predictor(self):
        if self._predictor is None:
            from .demand_predictor import DemandPredictor
            self._predictor = DemandPredictor()
        return self._predictor

    def _get_active_skus(self) -> list:
        return self._get_predictor().get_active_skus()

    def _get_daily_series(self, sku: str, days: int = 90) -> list:
        return self._get_predictor()._build_daily_series(sku, days=days)

    def _calc_growth_rate(self, series: list) -> float:
        """판매 성장률 계산 (전반부 vs 후반부 비교).

        Returns:
            성장률 (%) — 양수면 성장, 음수면 감소
        """
        if len(series) < 2:
            return 0.0
        mid = len(series) // 2
        first_half = series[:mid]
        second_half = series[mid:]
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        if avg_first <= 0:
            return 100.0 if avg_second > 0 else 0.0
        return round((avg_second - avg_first) / avg_first * 100, 2)

    def analyze_trends(self, period_days: int = 30) -> list:
        """SKU별 트렌드 분석 및 등급 분류.

        Args:
            period_days: 분석 기간 (일)

        Returns:
            SKU별 트렌드 + 등급 리스트
        """
        skus = self._get_active_skus()
        results = []

        for sku in skus:
            series = self._get_daily_series(sku, days=period_days * 2)
            if not series:
                continue

            recent = series[-period_days:] if len(series) >= period_days else series
            total_sales = sum(recent)
            avg_daily = total_sales / len(recent) if recent else 0
            growth_rate = self._calc_growth_rate(series)

            trend = 'stable'
            if growth_rate > 10:
                trend = 'rising'
            elif growth_rate < -10:
                trend = 'falling'

            grade = self._classify_grade(avg_daily, growth_rate, skus)

            results.append({
                'sku': sku,
                'total_sales': total_sales,
                'avg_daily_demand': round(avg_daily, 4),
                'growth_rate_pct': growth_rate,
                'trend': trend,
                'grade': grade,
                'period_days': period_days,
            })

        return sorted(results, key=lambda x: x['total_sales'], reverse=True)

    def _classify_grade(self, avg_daily: float, growth_rate: float,
                        all_skus: list) -> str:
        """상품 성과 등급 분류.

        Star:       성장률 높고 판매량 높음
        Cash Cow:   성장률 낮지만 판매량 높음
        Rising:     성장률 높지만 판매량 낮음
        Declining:  성장률 낮고 판매량 낮음
        """
        high_growth = growth_rate > 10
        # 판매량 높음 기준: 하루 평균 1개 이상
        high_volume = avg_daily >= 1.0

        if high_growth and high_volume:
            return 'Star'
        elif not high_growth and high_volume:
            return 'Cash Cow'
        elif high_growth and not high_volume:
            return 'Rising'
        else:
            return 'Declining'

    def detect_anomalies(self, sku: str, period_days: int = 30) -> list:
        """이상치 판매 이벤트 감지 (평균 ± 2σ 기준).

        Args:
            sku: 상품 SKU
            period_days: 분석 기간 (일)

        Returns:
            비정상 판매 이벤트 목록 [{date, qty, type, deviation}]
        """
        from datetime import datetime, timedelta

        series = self._get_daily_series(sku, days=period_days)
        if len(series) < 7:
            return []

        try:
            mean = statistics.mean(series)
            stddev = statistics.stdev(series) if len(series) >= 2 else 0.0
        except statistics.StatisticsError:
            return []

        if stddev == 0:
            return []

        anomalies = []
        today = datetime.utcnow().date()
        start = today - timedelta(days=period_days - 1)

        for i, qty in enumerate(series):
            date = (start + timedelta(days=i)).isoformat()
            z_score = (qty - mean) / stddev
            if abs(z_score) >= 2.0:
                anomaly_type = 'spike' if z_score > 0 else 'drop'
                anomalies.append({
                    'date': date,
                    'qty': qty,
                    'type': anomaly_type,
                    'mean': round(mean, 4),
                    'stddev': round(stddev, 4),
                    'z_score': round(z_score, 4),
                })

        return anomalies
