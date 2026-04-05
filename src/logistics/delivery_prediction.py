"""src/logistics/delivery_prediction.py — 배송 예측 (Phase 99)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from .logistics_models import Coordinate, DeliveryRecord
from .route_optimizer import DistanceCalculator

# 지역 간 평균 배송 시간 (시간)
_REGIONAL_AVG: dict = {
    ("서울", "서울"): 2.0,
    ("서울", "경기"): 4.0,
    ("서울", "인천"): 3.0,
    ("서울", "부산"): 24.0,
    ("서울", "대구"): 18.0,
    ("서울", "광주"): 20.0,
    ("서울", "전국"): 30.0,
    ("경기", "서울"): 4.0,
    ("경기", "경기"): 3.0,
    ("경기", "부산"): 24.0,
    ("부산", "서울"): 24.0,
    ("부산", "부산"): 2.0,
}

_CARRIER_PERFORMANCE: dict = {
    "CJ": {"on_time_rate": 0.95, "avg_days": 2, "reliability": 0.95},
    "HANJIN": {"on_time_rate": 0.90, "avg_days": 2, "reliability": 0.90},
    "POST": {"on_time_rate": 0.85, "avg_days": 3, "reliability": 0.85},
    "LOGEN": {"on_time_rate": 0.88, "avg_days": 2, "reliability": 0.88},
    "COUPANG": {"on_time_rate": 0.92, "avg_days": 1, "reliability": 0.92},
}

# 명절 (월-일)
_HOLIDAYS = {(9, 29), (9, 30), (10, 1), (1, 21), (1, 22), (1, 23)}


class HistoricalDeliveryData:
    """과거 배송 데이터 (mock)."""

    def get_regional_avg(self, from_region: str, to_region: str) -> float:
        key = (from_region, to_region)
        if key in _REGIONAL_AVG:
            return _REGIONAL_AVG[key]
        # 다른 지역간 기본값
        if from_region == to_region:
            return 3.0
        return 24.0

    def get_carrier_performance(self, carrier_id: str) -> dict:
        return dict(_CARRIER_PERFORMANCE.get(carrier_id, {"on_time_rate": 0.85, "avg_days": 3, "reliability": 0.85}))


class DeliveryDelayPredictor:
    """배송 지연 예측기."""

    def __init__(self) -> None:
        self._historical = HistoricalDeliveryData()

    def predict_delay(
        self,
        carrier_id: str,
        from_region: str,
        to_region: str,
        order_date: datetime | None = None,
    ) -> dict:
        if order_date is None:
            order_date = datetime.now()

        reasons = []
        delay_prob = 0.05
        extra_hours = 0.0

        # 명절 확인
        if (order_date.month, order_date.day) in _HOLIDAYS:
            delay_prob += 0.40
            extra_hours += 24.0
            reasons.append("명절 특수기간 (추석/설날)")

        # 요일 부하 (월요일/금요일)
        if order_date.weekday() == 0:
            delay_prob += 0.10
            extra_hours += 4.0
            reasons.append("월요일 물량 집중")
        elif order_date.weekday() == 4:
            delay_prob += 0.08
            extra_hours += 3.0
            reasons.append("금요일 물량 집중")

        # 택배사 성능
        perf = self._historical.get_carrier_performance(carrier_id)
        base_delay = 1.0 - perf["on_time_rate"]
        delay_prob += base_delay
        if base_delay > 0.1:
            reasons.append(f"택배사 {carrier_id} 평균 지연율 {base_delay:.0%}")

        # 장거리 배송
        if from_region != to_region and {from_region, to_region} & {"부산", "광주", "제주"}:
            delay_prob += 0.05
            extra_hours += 4.0
            reasons.append("장거리 배송 구간")

        delay_prob = min(delay_prob, 1.0)

        return {
            "delay_probability": round(delay_prob, 3),
            "expected_extra_hours": round(extra_hours, 1),
            "reasons": reasons,
        }


class ETACalculator:
    """ETA 계산기."""

    def __init__(self) -> None:
        self._historical = HistoricalDeliveryData()

    def calculate_eta(
        self,
        from_coord: Coordinate,
        to_coord: Coordinate,
        carrier_id: str,
        current_status: str | None = None,
    ) -> dict:
        distance_km = DistanceCalculator.haversine(from_coord, to_coord)
        avg_speed_kmh = 30.0
        travel_hours = distance_km / avg_speed_kmh

        perf = self._historical.get_carrier_performance(carrier_id)
        base_days = perf["avg_days"]
        reliability = perf["reliability"]

        now = datetime.now()
        estimated = now + timedelta(days=base_days, hours=travel_hours)
        min_date = now + timedelta(days=max(1, base_days - 1))
        max_date = now + timedelta(days=base_days + 2)

        return {
            "estimated_arrival": estimated.isoformat(),
            "confidence": round(reliability, 2),
            "min_date": min_date.date().isoformat(),
            "max_date": max_date.date().isoformat(),
        }

    def recalculate_eta(self, delivery: DeliveryRecord, current_position: Coordinate) -> float:
        remaining_km = DistanceCalculator.haversine(current_position, delivery.delivery_coordinate)
        avg_speed_kmh = 30.0
        return round((remaining_km / avg_speed_kmh) * 60, 1)


class DeliveryTimeEstimator:
    """배송 시간 예측기."""

    def __init__(self) -> None:
        self._historical = HistoricalDeliveryData()
        self._predictor = DeliveryDelayPredictor()

    def estimate(
        self,
        from_region: str,
        to_region: str,
        carrier_id: str,
        weight_kg: float = 1.0,
    ) -> dict:
        avg_hours = self._historical.get_regional_avg(from_region, to_region)
        perf = self._historical.get_carrier_performance(carrier_id)
        delay_info = self._predictor.predict_delay(carrier_id, from_region, to_region)

        avg_days = perf["avg_days"]
        min_days = max(1, avg_days - 1)
        max_days = avg_days + int(delay_info["expected_extra_hours"] / 24) + 1

        return {
            "estimated_days": avg_days,
            "min_days": min_days,
            "max_days": max_days,
            "estimated_hours": round(avg_hours, 1),
            "carrier_info": perf,
            "delay_risk": delay_info,
        }
