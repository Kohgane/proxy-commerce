"""src/global_commerce/shipping/international_shipping_manager.py — 국제 배송 관리 (Phase 93)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 국가별 기본 배송 요율 (kg당 KRW)
_RATE_PER_KG: Dict[str, float] = {
    'US': 25000.0,
    'JP': 8000.0,
    'CN': 6000.0,
    'GB': 30000.0,
    'EU': 28000.0,
    'DE': 28000.0,
    'FR': 28000.0,
    'AU': 32000.0,
    'CA': 27000.0,
    'DEFAULT': 30000.0,
}

# 국가별 기본 배송 기간 (일)
_TRANSIT_DAYS: Dict[str, int] = {
    'US': 7,
    'JP': 3,
    'CN': 5,
    'GB': 10,
    'EU': 10,
    'DE': 10,
    'FR': 10,
    'AU': 14,
    'CA': 12,
    'DEFAULT': 14,
}

# 부피 무게 계수 (cm³/kg)
_VOLUMETRIC_DIVISOR = 5000.0

# 배송 루트 매핑 (출발국 → 경유지 → 목적국)
_ROUTE_HUBS: Dict[str, str] = {
    'US': 'LAX',
    'JP': 'NRT',
    'CN': 'PVG',
    'GB': 'LHR',
    'DE': 'FRA',
    'AU': 'SYD',
    'KR': 'ICN',
    'DEFAULT': 'ICN',
}


@dataclass
class ShippingRoute:
    """배송 루트."""
    origin_country: str
    destination_country: str
    origin_hub: str
    destination_hub: str
    transit_days: int
    waypoints: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'origin_country': self.origin_country,
            'destination_country': self.destination_country,
            'origin_hub': self.origin_hub,
            'destination_hub': self.destination_hub,
            'transit_days': self.transit_days,
            'waypoints': self.waypoints,
        }


@dataclass
class ShippingQuote:
    """배송 견적."""
    origin_country: str
    destination_country: str
    actual_weight_kg: float
    volumetric_weight_kg: float
    chargeable_weight_kg: float
    rate_per_kg_krw: float
    base_fee_krw: float
    fuel_surcharge_krw: float
    total_fee_krw: float
    transit_days: int
    route: Optional[ShippingRoute] = None

    def to_dict(self) -> dict:
        return {
            'origin_country': self.origin_country,
            'destination_country': self.destination_country,
            'actual_weight_kg': self.actual_weight_kg,
            'volumetric_weight_kg': self.volumetric_weight_kg,
            'chargeable_weight_kg': self.chargeable_weight_kg,
            'rate_per_kg_krw': self.rate_per_kg_krw,
            'base_fee_krw': self.base_fee_krw,
            'fuel_surcharge_krw': self.fuel_surcharge_krw,
            'total_fee_krw': self.total_fee_krw,
            'transit_days': self.transit_days,
            'route': self.route.to_dict() if self.route else None,
        }


class InternationalShippingManager:
    """국제 배송 관리 — 배송 루트 계산, 배송비 계산."""

    FUEL_SURCHARGE_RATE = 0.12  # 12% 유류할증료

    def calculate_volumetric_weight(self, length_cm: float, width_cm: float,
                                    height_cm: float) -> float:
        """부피 무게 계산.

        Args:
            length_cm: 길이 (cm)
            width_cm: 너비 (cm)
            height_cm: 높이 (cm)

        Returns:
            부피 무게 (kg)
        """
        return round((length_cm * width_cm * height_cm) / _VOLUMETRIC_DIVISOR, 3)

    def get_route(self, origin_country: str, destination_country: str) -> ShippingRoute:
        """배송 루트 계산.

        Args:
            origin_country: 출발 국가 코드
            destination_country: 목적지 국가 코드

        Returns:
            ShippingRoute
        """
        origin = origin_country.upper()
        destination = destination_country.upper()
        origin_hub = _ROUTE_HUBS.get(origin, _ROUTE_HUBS['DEFAULT'])
        dest_hub = _ROUTE_HUBS.get(destination, _ROUTE_HUBS['DEFAULT'])
        transit_days = _TRANSIT_DAYS.get(destination, _TRANSIT_DAYS['DEFAULT'])

        # 국제 경유지: 한국 발송이 아닌 경우 ICN 경유
        waypoints = []
        if origin != 'KR' and destination != 'KR':
            waypoints = ['ICN']

        return ShippingRoute(
            origin_country=origin,
            destination_country=destination,
            origin_hub=origin_hub,
            destination_hub=dest_hub,
            transit_days=transit_days,
            waypoints=waypoints,
        )

    def calculate(self, weight_kg: float, origin_country: str,
                  destination_country: str, length_cm: float = 0.0,
                  width_cm: float = 0.0, height_cm: float = 0.0) -> ShippingQuote:
        """국제 배송비 계산.

        Args:
            weight_kg: 실제 무게 (kg)
            origin_country: 출발 국가
            destination_country: 목적지 국가
            length_cm: 길이 (cm, 부피 무게 계산용)
            width_cm: 너비 (cm)
            height_cm: 높이 (cm)

        Returns:
            ShippingQuote
        """
        destination = destination_country.upper()
        rate = _RATE_PER_KG.get(destination, _RATE_PER_KG['DEFAULT'])

        volumetric = 0.0
        if length_cm and width_cm and height_cm:
            volumetric = self.calculate_volumetric_weight(length_cm, width_cm, height_cm)

        chargeable = max(weight_kg, volumetric, 0.1)  # 최소 0.1kg
        base_fee = round(chargeable * rate, 0)
        fuel_surcharge = round(base_fee * self.FUEL_SURCHARGE_RATE, 0)
        total_fee = base_fee + fuel_surcharge

        route = self.get_route(origin_country, destination_country)

        return ShippingQuote(
            origin_country=origin_country.upper(),
            destination_country=destination,
            actual_weight_kg=weight_kg,
            volumetric_weight_kg=volumetric,
            chargeable_weight_kg=chargeable,
            rate_per_kg_krw=rate,
            base_fee_krw=base_fee,
            fuel_surcharge_krw=fuel_surcharge,
            total_fee_krw=total_fee,
            transit_days=route.transit_days,
            route=route,
        )
