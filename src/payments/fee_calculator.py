"""src/payments/fee_calculator.py — 플랫폼별 수수료 계산기."""

import logging

logger = logging.getLogger(__name__)

_FEE_RATES: dict[str, float] = {
    "COUPANG": 0.108,
    "NAVER": 0.055,
    "SHOPIFY": 0.02,
    "WOO": 0.0,
}


class FeeCalculator:
    """플랫폼별 판매 수수료 계산기."""

    def get_fee_rate(self, platform: str) -> float:
        """플랫폼 수수료율을 반환한다. 미등록 플랫폼은 0.0."""
        return _FEE_RATES.get(platform.upper(), 0.0)

    def calculate_fee(self, platform: str, sale_price: float) -> float:
        """판매 수수료 금액을 계산한다."""
        return sale_price * self.get_fee_rate(platform)

    def list_platforms(self) -> list:
        """등록된 플랫폼 이름 목록을 반환한다."""
        return list(_FEE_RATES.keys())
