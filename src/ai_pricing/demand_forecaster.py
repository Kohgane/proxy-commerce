"""src/ai_pricing/demand_forecaster.py — 수요 예측 모듈 (Phase 97)."""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .pricing_models import DemandForecast

logger = logging.getLogger(__name__)

# 이동평균 기본 윈도우 크기
_DEFAULT_MA_WINDOW = 4

# 지수 평활 기본 알파
_DEFAULT_EWM_ALPHA = 0.3

# 계절성 — 월별 가중치 (1월~12월)
_MONTHLY_SEASONALITY = [
    0.85,  # 1월 (비수기)
    0.80,  # 2월
    0.90,  # 3월
    0.95,  # 4월
    1.00,  # 5월
    0.95,  # 6월
    1.05,  # 7월
    1.10,  # 8월 (여름 성수기)
    1.00,  # 9월
    1.05,  # 10월
    1.20,  # 11월 (블랙프라이데이)
    1.30,  # 12월 (크리스마스 성수기)
]

# 요일별 가중치 (0=월 ~ 6=일)
_WEEKDAY_SEASONALITY = [1.0, 1.05, 1.10, 1.15, 1.20, 1.30, 1.25]


class DemandForecaster:
    """시계열 기반 수요 예측기.

    이동 평균, 지수 평활법, 가중 평균으로 수요를 예측하고
    계절성/외부 요인을 반영한다.
    """

    def __init__(
        self,
        ma_window: int = _DEFAULT_MA_WINDOW,
        ewm_alpha: float = _DEFAULT_EWM_ALPHA,
    ) -> None:
        self._ma_window = ma_window
        self._ewm_alpha = ewm_alpha
        # sku → list[float] (과거 판매량)
        self._sales_history: Dict[str, List[float]] = defaultdict(list)
        # sku → list[(price, qty)] (가격-수량 쌍 — 탄력성 계산용)
        self._price_qty_pairs: Dict[str, List[Tuple[float, float]]] = defaultdict(list)

    # ── 데이터 입력 ───────────────────────────────────────────────────────

    def record_sales(self, sku: str, qty: float, price: float = 0.0) -> None:
        """판매 데이터를 기록한다."""
        self._sales_history[sku].append(qty)
        if price > 0:
            self._price_qty_pairs[sku].append((price, qty))

    def record_sales_batch(self, sku: str, quantities: List[float]) -> None:
        """판매 데이터 배치 기록."""
        self._sales_history[sku].extend(quantities)

    # ── 예측 방법 ─────────────────────────────────────────────────────────

    def moving_average(self, sku: str, window: int = None) -> float:
        """이동 평균 예측값을 반환한다."""
        w = window or self._ma_window
        history = self._sales_history.get(sku, [])
        if not history:
            return 0.0
        recent = history[-w:]
        return round(sum(recent) / len(recent), 4)

    def exponential_smoothing(self, sku: str, alpha: float = None) -> float:
        """지수 평활법(EWM) 예측값을 반환한다.

        S_t = α * x_t + (1 - α) * S_{t-1}
        """
        a = alpha or self._ewm_alpha
        history = self._sales_history.get(sku, [])
        if not history:
            return 0.0
        smoothed = history[0]
        for val in history[1:]:
            smoothed = a * val + (1 - a) * smoothed
        return round(smoothed, 4)

    def weighted_average(self, sku: str, window: int = None) -> float:
        """가중 평균 예측 (최근 데이터에 높은 가중치)."""
        w = window or self._ma_window
        history = self._sales_history.get(sku, [])
        if not history:
            return 0.0
        recent = history[-w:]
        n = len(recent)
        weights = list(range(1, n + 1))  # 1, 2, ..., n
        total_w = sum(weights)
        weighted = sum(v * wt for v, wt in zip(recent, weights))
        return round(weighted / total_w, 4)

    def ensemble_forecast(self, sku: str) -> float:
        """3가지 방법의 앙상블 예측값 (단순 평균)."""
        ma = self.moving_average(sku)
        ewm = self.exponential_smoothing(sku)
        wa = self.weighted_average(sku)
        values = [v for v in (ma, ewm, wa) if v > 0]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    # ── 계절성 ────────────────────────────────────────────────────────────

    def get_seasonality_factor(self, month: int = None, weekday: int = None) -> float:
        """현재 시점의 계절성 가중치를 반환한다.

        Args:
            month: 1~12 (None이면 현재 월)
            weekday: 0~6 (None이면 현재 요일)

        Returns:
            계절성 가중치 (1.0 = 기준)
        """
        now = datetime.now(timezone.utc)
        m = (month or now.month) - 1  # 0-indexed
        d = weekday if weekday is not None else now.weekday()
        m_factor = _MONTHLY_SEASONALITY[max(0, min(11, m))]
        d_factor = _WEEKDAY_SEASONALITY[max(0, min(6, d))]
        return round(m_factor * d_factor, 4)

    def get_monthly_seasonality(self) -> Dict[int, float]:
        """월별 계절성 가중치 딕셔너리를 반환한다."""
        return {i + 1: v for i, v in enumerate(_MONTHLY_SEASONALITY)}

    # ── 외부 요인 ─────────────────────────────────────────────────────────

    def apply_external_factors(
        self,
        base_forecast: float,
        fx_change_pct: float = 0.0,
        is_holiday: bool = False,
        promotion_boost: float = 0.0,
    ) -> float:
        """외부 요인을 반영한 예측값을 반환한다.

        Args:
            base_forecast: 기본 예측값
            fx_change_pct: 환율 변동율 (%) — 양수=원화 약세(수입품 수요 감소)
            is_holiday: 명절/시즌 여부
            promotion_boost: 프로모션 효과 가중치 (0.2 = +20%)

        Returns:
            조정된 예측값
        """
        factor = 1.0
        # 환율 10% 상승 → 수입품 수요 5% 감소 (탄력성 -0.5 가정)
        if fx_change_pct != 0:
            factor *= 1 + (-0.5 * fx_change_pct / 100)
        if is_holiday:
            factor *= 1.3
        if promotion_boost:
            factor *= 1 + promotion_boost
        return round(base_forecast * max(0, factor), 4)

    # ── 탄력성 ────────────────────────────────────────────────────────────

    def calculate_elasticity(self, sku: str) -> float:
        """가격 탄력성을 계산한다.

        E = (ΔQ/Q) / (ΔP/P)
        음수 → 정상재 (가격↑ → 수요↓)
        """
        pairs = self._price_qty_pairs.get(sku, [])
        if len(pairs) < 2:
            return -1.0  # 기본 탄력성

        elasticities = []
        for i in range(1, len(pairs)):
            p0, q0 = pairs[i - 1]
            p1, q1 = pairs[i]
            if p0 == 0 or q0 == 0:
                continue
            dp = (p1 - p0) / p0
            dq = (q1 - q0) / q0
            if dp != 0:
                elasticities.append(dq / dp)

        if not elasticities:
            return -1.0
        return round(sum(elasticities) / len(elasticities), 4)

    # ── 예측 정확도 메트릭 ────────────────────────────────────────────────

    def calculate_mape(self, actuals: List[float], predictions: List[float]) -> float:
        """MAPE (Mean Absolute Percentage Error) 계산."""
        if len(actuals) != len(predictions) or not actuals:
            return 0.0
        errors = []
        for a, p in zip(actuals, predictions):
            if a != 0:
                errors.append(abs((a - p) / a))
        return round(sum(errors) / len(errors) * 100, 4) if errors else 0.0

    def calculate_rmse(self, actuals: List[float], predictions: List[float]) -> float:
        """RMSE (Root Mean Square Error) 계산."""
        if len(actuals) != len(predictions) or not actuals:
            return 0.0
        mse = sum((a - p) ** 2 for a, p in zip(actuals, predictions)) / len(actuals)
        return round(math.sqrt(mse), 4)

    # ── 완전한 예측 결과 ──────────────────────────────────────────────────

    def forecast(
        self,
        sku: str,
        period: str = '',
        month: int = None,
        external_factors: Dict = None,
    ) -> DemandForecast:
        """SKU에 대한 완전한 수요 예측 결과를 반환한다."""
        base = self.ensemble_forecast(sku)
        seasonality = self.get_seasonality_factor(month=month)
        factors = external_factors or {}
        adjusted = self.apply_external_factors(
            base * seasonality,
            fx_change_pct=factors.get('fx_change_pct', 0.0),
            is_holiday=factors.get('is_holiday', False),
            promotion_boost=factors.get('promotion_boost', 0.0),
        )

        # 95% 신뢰구간: ±15%
        ci_width = adjusted * 0.15
        return DemandForecast(
            sku=sku,
            period=period or datetime.now(timezone.utc).strftime('%Y-%m'),
            predicted_qty=adjusted,
            confidence_interval_lower=round(adjusted - ci_width, 4),
            confidence_interval_upper=round(adjusted + ci_width, 4),
            seasonality_factor=seasonality,
            forecast_method='ensemble',
        )

    def get_history(self, sku: str) -> List[float]:
        """SKU 판매 이력을 반환한다."""
        return list(self._sales_history.get(sku, []))
