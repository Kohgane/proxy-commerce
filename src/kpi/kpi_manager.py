"""src/kpi/kpi_manager.py — KPI 관리자."""
from __future__ import annotations

from .kpi_definition import KPIDefinition
from .kpi_calculator import KPICalculator


_BUILTIN_KPIS = [
    KPIDefinition(name="GMV", formula="sum(order_amounts)", target=100_000_000, unit="원", period="monthly"),
    KPIDefinition(name="order_conversion_rate", formula="orders/visitors", target=0.03, unit="%", period="daily"),
    KPIDefinition(name="average_order_value", formula="GMV/orders", target=50_000, unit="원", period="daily"),
    KPIDefinition(name="customer_repurchase_rate", formula="repurchase/total_customers", target=0.3, unit="%", period="monthly"),
    KPIDefinition(name="inventory_turnover", formula="COGS/avg_inventory", target=6.0, unit="회", period="monthly"),
    KPIDefinition(name="cs_response_time", formula="avg(response_times)", target=2.0, unit="시간", period="daily"),
]


class KPIManager:
    """KPI 관리자."""

    def __init__(self) -> None:
        self._kpis: dict[str, KPIDefinition] = {kpi.name: kpi for kpi in _BUILTIN_KPIS}
        self._calculator = KPICalculator()

    def register(self, definition: KPIDefinition) -> None:
        """KPI 정의를 등록한다."""
        self._kpis[definition.name] = definition

    def get(self, kpi_name: str) -> KPIDefinition | None:
        """KPI 정의를 반환한다."""
        return self._kpis.get(kpi_name)

    def list_kpis(self) -> list:
        """모든 KPI 정의 목록을 반환한다."""
        return [kpi.to_dict() for kpi in self._kpis.values()]

    def calculate_all(self, data: dict) -> dict:
        """모든 KPI 값을 계산한다."""
        return {
            name: self._calculator.calculate(name, data)
            for name in self._kpis
        }
