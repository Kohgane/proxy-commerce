"""src/shipping_calculator/shipping_estimator.py — 배송 기간 추정기."""
from __future__ import annotations


class ShippingEstimator:
    """배송 기간 추정기."""

    def __init__(self) -> None:
        self._estimates: dict[str, dict] = {
            'CJ|domestic': {'min_days': 1, 'max_days': 2},
            'CJ|east_asia': {'min_days': 3, 'max_days': 5},
            'CJ|asia': {'min_days': 5, 'max_days': 8},
            'CJ|usa_europe': {'min_days': 7, 'max_days': 14},
            'CJ|international': {'min_days': 10, 'max_days': 20},
            'DHL|domestic': {'min_days': 1, 'max_days': 2},
            'DHL|east_asia': {'min_days': 2, 'max_days': 4},
            'DHL|international': {'min_days': 5, 'max_days': 10},
            'DHL|usa_europe': {'min_days': 4, 'max_days': 7},
        }

    def estimate(self, carrier: str, zone: str) -> dict:
        """배송 기간을 추정한다."""
        key = f'{carrier}|{zone}'
        base = self._estimates.get(key, {'min_days': 7, 'max_days': 14})
        return {'carrier': carrier, 'zone': zone, **base}
