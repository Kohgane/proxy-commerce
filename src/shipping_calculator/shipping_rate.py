"""src/shipping_calculator/shipping_rate.py — 배송 요금."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ShippingRate:
    """배송 요금 정보."""

    zone: str
    weight_min: float
    weight_max: float
    price: float
    carrier: str
    method: str
