"""src/shipping_calculator/dimensional_weight.py — 부피 무게 계산."""
from __future__ import annotations


class DimensionalWeight:
    """부피 무게 계산기."""

    def calculate(self, length: float, width: float, height: float) -> float:
        """부피 무게를 계산한다 (L*W*H/5000)."""
        return length * width * height / 5000

    def effective_weight(self, actual_g: float, length: float, width: float, height: float) -> float:
        """실효 무게를 계산한다."""
        dim_kg = self.calculate(length, width, height)
        dim_g = dim_kg * 1000
        return max(actual_g, dim_g)
