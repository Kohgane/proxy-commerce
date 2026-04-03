"""src/kpi/kpi_calculator.py — KPI 계산기."""
from __future__ import annotations


class KPICalculator:
    """KPI 계산기."""

    def calculate(self, kpi_name: str, data: dict) -> float:
        """KPI 값을 계산한다."""
        return float(data.get(kpi_name, 0.0))

    def sum_metric(self, values: list) -> float:
        """합계를 계산한다."""
        return sum(float(v) for v in values)

    def average_metric(self, values: list) -> float:
        """평균을 계산한다."""
        if not values:
            return 0.0
        return self.sum_metric(values) / len(values)

    def ratio(self, numerator: float, denominator: float) -> float:
        """비율을 계산한다."""
        if denominator == 0:
            return 0.0
        return numerator / denominator

    def growth_rate(self, current: float, previous: float) -> float:
        """성장률을 계산한다."""
        if previous == 0:
            return 0.0
        return (current - previous) / previous

    def yoy(self, current: float, previous_year: float) -> float:
        """전년 대비 성장률을 계산한다."""
        return self.growth_rate(current, previous_year)

    def mom(self, current: float, previous_month: float) -> float:
        """전월 대비 성장률을 계산한다."""
        return self.growth_rate(current, previous_month)
