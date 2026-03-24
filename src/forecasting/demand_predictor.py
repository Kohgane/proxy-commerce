"""src/forecasting/demand_predictor.py — 수요 예측 엔진.

이동 평균(SMA) 및 지수 이동 평균(EMA) 기반 수요 예측.
stdlib math, statistics만 사용 (외부 통계 라이브러리 불필요).

환경변수:
  FORECASTING_ENABLED         — 활성화 여부 (기본 "0")
  FORECASTING_MIN_DATA_DAYS   — 예측에 필요한 최소 데이터 일수 (기본 30)
  GOOGLE_SHEET_ID             — Google Sheets ID
"""

import logging
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_ENABLED = os.getenv('FORECASTING_ENABLED', '0') == '1'
_MIN_DATA_DAYS = int(os.getenv('FORECASTING_MIN_DATA_DAYS', '30'))


def _sma(values: list, window: int) -> list:
    """단순 이동 평균(SMA) 계산.

    Args:
        values: 숫자 리스트
        window: 이동 평균 윈도우 크기

    Returns:
        이동 평균 리스트 (길이 = len(values) - window + 1)
    """
    if len(values) < window:
        return []
    result = []
    for i in range(len(values) - window + 1):
        avg = sum(values[i:i + window]) / window
        result.append(avg)
    return result


def _ema(values: list, alpha: float = None) -> list:
    """지수 이동 평균(EMA) 계산.

    Args:
        values: 숫자 리스트
        alpha: 평활 계수 (None이면 2/(n+1) 사용)

    Returns:
        EMA 리스트 (첫 값은 첫 values 값으로 초기화)
    """
    if not values:
        return []
    n = len(values)
    if alpha is None:
        alpha = 2.0 / (n + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


class DemandPredictor:
    """수요 예측 엔진."""

    def __init__(self):
        self._sales_cache: dict = {}

    def _get_sales_history(self, sku: str) -> dict:
        """Google Sheets에서 SKU별 과거 판매 데이터를 읽는다.

        Returns:
            {날짜(str): 판매수량(int)} dict
        """
        if sku in self._sales_cache:
            return self._sales_cache[sku]

        result = defaultdict(int)
        try:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            ws = open_sheet(sheet_id, os.getenv('ORDERS_SHEET_NAME', 'orders'))
            records = ws.get_all_records()
            for row in records:
                row_sku = str(row.get('sku', ''))
                if row_sku != str(sku):
                    continue
                order_date = str(row.get('order_date', '') or row.get('created_at', ''))[:10]
                qty = int(row.get('quantity', 1) or 1)
                if order_date:
                    result[order_date] += qty
        except Exception as exc:
            logger.warning("판매 이력 조회 실패 (%s): %s", sku, exc)

        self._sales_cache[sku] = dict(result)
        return self._sales_cache[sku]

    def _build_daily_series(self, sku: str, days: int = 90) -> list:
        """최근 days일간의 일별 판매량 리스트를 반환한다.

        결측일은 0으로 채운다.
        """
        history = self._get_sales_history(sku)
        today = datetime.utcnow().date()
        series = []
        for i in range(days - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            series.append(history.get(d, 0))
        return series

    def predict_demand(self, sku: str, days_ahead: int = 30) -> dict:
        """수요 예측.

        SMA-7, SMA-14, SMA-30 및 EMA를 조합하여 예측한다.

        Args:
            sku: 상품 SKU
            days_ahead: 예측 기간 (일)

        Returns:
            dict with predicted_qty, confidence, trend, method
        """
        series = self._build_daily_series(sku, days=90)
        non_zero = [v for v in series if v > 0]

        if len(non_zero) < _MIN_DATA_DAYS // 3:
            return {
                'sku': sku,
                'predicted_qty': 0,
                'confidence': 'low',
                'trend': 'insufficient_data',
                'avg_daily_demand': 0.0,
                'days_ahead': days_ahead,
            }

        avg_daily = sum(series) / len(series) if series else 0.0

        # SMA 계산
        sma7 = _sma(series, 7)
        sma14 = _sma(series, 14)
        sma30 = _sma(series, 30)

        # 가장 최근 SMA 값 사용
        sma7_last = sma7[-1] if sma7 else avg_daily
        sma14_last = sma14[-1] if sma14 else avg_daily
        sma30_last = sma30[-1] if sma30 else avg_daily

        # EMA (최근 30일)
        ema_values = _ema(series[-30:]) if len(series) >= 30 else _ema(series)
        ema_last = ema_values[-1] if ema_values else avg_daily

        # 가중 평균: EMA 40%, SMA-7 30%, SMA-14 20%, SMA-30 10%
        predicted_daily = (
            ema_last * 0.4
            + sma7_last * 0.3
            + sma14_last * 0.2
            + sma30_last * 0.1
        )
        predicted_qty = math.ceil(predicted_daily * days_ahead)

        # 트렌드 판단
        trend = 'stable'
        if sma7_last > sma30_last * 1.1:
            trend = 'rising'
        elif sma7_last < sma30_last * 0.9:
            trend = 'falling'

        # 신뢰도: 데이터 양 기반
        data_days = len([v for v in series[-30:] if v > 0])
        if data_days >= 20:
            confidence = 'high'
        elif data_days >= 10:
            confidence = 'medium'
        else:
            confidence = 'low'

        return {
            'sku': sku,
            'predicted_qty': predicted_qty,
            'avg_daily_demand': round(predicted_daily, 4),
            'confidence': confidence,
            'trend': trend,
            'sma_7d': round(sma7_last, 4),
            'sma_14d': round(sma14_last, 4),
            'sma_30d': round(sma30_last, 4),
            'ema': round(ema_last, 4),
            'days_ahead': days_ahead,
        }

    def get_seasonal_pattern(self, sku: str) -> dict:
        """월별 판매 지수를 반환한다.

        반환값: {1: 1.2, 2: 0.8, ..., 12: 1.5} (1.0 = 평균)
        """
        history = self._get_sales_history(sku)
        monthly = defaultdict(list)

        for date_str, qty in history.items():
            try:
                month = int(date_str[5:7])
                monthly[month].append(qty)
            except (ValueError, IndexError):
                continue

        if not monthly:
            return {m: 1.0 for m in range(1, 13)}

        monthly_avg = {m: (sum(vals) / len(vals)) for m, vals in monthly.items()}
        overall_avg = sum(monthly_avg.values()) / len(monthly_avg)

        pattern = {}
        for m in range(1, 13):
            if overall_avg > 0 and m in monthly_avg:
                pattern[m] = round(monthly_avg[m] / overall_avg, 4)
            else:
                pattern[m] = 1.0

        return pattern

    def get_active_skus(self) -> list:
        """판매 이력이 있는 SKU 목록을 반환한다."""
        try:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            ws = open_sheet(sheet_id, os.getenv('ORDERS_SHEET_NAME', 'orders'))
            records = ws.get_all_records()
            skus = list({str(r.get('sku', '')) for r in records if r.get('sku')})
            return skus
        except Exception as exc:
            logger.warning("SKU 목록 조회 실패: %s", exc)
            return []

    def _stddev(self, values: list) -> float:
        """표준편차 계산 (stdlib statistics 사용)."""
        if len(values) < 2:
            return 0.0
        try:
            return statistics.stdev(values)
        except Exception:
            return 0.0
