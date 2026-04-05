"""src/logistics/cost_optimizer.py — 물류 비용 최적화 (Phase 99)."""
from __future__ import annotations

import uuid

from .logistics_models import CarrierInfo, ConsolidationGroup


class LogisticsCostCalculator:
    """물류 비용 계산기."""

    # 차량 유형별 연료 소비량 (L/km)
    _FUEL_CONSUMPTION = {
        "motorcycle": 0.04,
        "van": 0.10,
        "truck": 0.20,
    }
    _FUEL_PRICE_PER_LITER = 1600.0  # KRW

    def calculate_shipping_cost(
        self, weight_kg: float, distance_km: float, carrier_id: str = "CJ"
    ) -> float:
        base_rates = {
            "CJ": 3000.0,
            "HANJIN": 2800.0,
            "POST": 2500.0,
            "LOGEN": 2600.0,
            "COUPANG": 2000.0,
        }
        per_kg_rates = {
            "CJ": 200.0,
            "HANJIN": 180.0,
            "POST": 150.0,
            "LOGEN": 160.0,
            "COUPANG": 100.0,
        }
        base = base_rates.get(carrier_id, 3000.0)
        per_kg = per_kg_rates.get(carrier_id, 200.0)
        distance_surcharge = max(0.0, (distance_km - 50) * 10)
        return base + per_kg * weight_kg + distance_surcharge

    def calculate_packaging_cost(self, weight_kg: float, item_count: int = 1) -> float:
        base = 300.0 * item_count
        if weight_kg > 5:
            base += 200.0
        if weight_kg > 20:
            base += 500.0
        return base

    def calculate_labor_cost(self, delivery_count: int, hours: float = 8) -> float:
        hourly_rate = 12000.0
        total_labor = hourly_rate * hours
        return total_labor / max(delivery_count, 1)

    def calculate_fuel_cost(self, distance_km: float, vehicle_type: str = "motorcycle") -> float:
        consumption = self._FUEL_CONSUMPTION.get(vehicle_type, 0.04)
        return distance_km * consumption * self._FUEL_PRICE_PER_LITER

    def calculate_total_cost(
        self, weight_kg: float, distance_km: float, delivery_count: int = 1
    ) -> dict:
        shipping = self.calculate_shipping_cost(weight_kg, distance_km)
        packaging = self.calculate_packaging_cost(weight_kg)
        labor = self.calculate_labor_cost(delivery_count)
        fuel = self.calculate_fuel_cost(distance_km)
        total = shipping + packaging + labor + fuel
        return {
            "shipping_cost": round(shipping, 2),
            "packaging_cost": round(packaging, 2),
            "labor_cost": round(labor, 2),
            "fuel_cost": round(fuel, 2),
            "total_cost": round(total, 2),
        }


class CarrierSelector:
    """택배사 선택 추천기."""

    _CARRIERS = [
        CarrierInfo("CJ", "CJ대한통운", 3000.0, 200.0, ["서울", "경기", "인천", "부산", "대구", "광주"], 2, 0.95),
        CarrierInfo("HANJIN", "한진", 2800.0, 180.0, ["서울", "경기", "인천", "부산", "대구"], 2, 0.90),
        CarrierInfo("POST", "우체국", 2500.0, 150.0, ["전국"], 3, 0.85),
        CarrierInfo("LOGEN", "로젠", 2600.0, 160.0, ["서울", "경기", "인천", "부산"], 2, 0.88),
        CarrierInfo("COUPANG", "쿠팡로켓", 2000.0, 100.0, ["서울", "경기", "인천"], 1, 0.92),
    ]

    def get_carriers(self) -> list:
        return list(self._CARRIERS)

    def recommend_carrier(
        self, weight_kg: float, region: str, priority: str = "cost"
    ) -> CarrierInfo:
        eligible = [c for c in self._CARRIERS if not c.coverage_regions or region in c.coverage_regions or "전국" in c.coverage_regions]
        if not eligible:
            eligible = list(self._CARRIERS)

        if priority == "cost":
            return min(eligible, key=lambda c: c.base_rate + c.per_kg_rate * weight_kg)
        elif priority == "speed":
            return min(eligible, key=lambda c: c.avg_delivery_days)
        elif priority == "reliability":
            return max(eligible, key=lambda c: c.reliability_score)
        return min(eligible, key=lambda c: c.base_rate + c.per_kg_rate * weight_kg)

    def get_carrier(self, carrier_id: str) -> CarrierInfo | None:
        for c in self._CARRIERS:
            if c.carrier_id == carrier_id:
                return c
        return None


class ConsolidationManager:
    """배송 통합 관리자."""

    def analyze_consolidation(self, orders: list) -> list:
        region_groups: dict = {}
        for order in orders:
            region = order.get("region", "기타")
            region_groups.setdefault(region, []).append(order)

        groups = []
        for region, region_orders in region_groups.items():
            if len(region_orders) < 2:
                continue
            group_id = str(uuid.uuid4())
            order_ids = [o.get("order_id", str(uuid.uuid4())) for o in region_orders]
            total_weight = sum(o.get("weight_kg", 1.0) for o in region_orders)
            calc = LogisticsCostCalculator()
            original = sum(
                calc.calculate_shipping_cost(o.get("weight_kg", 1.0), o.get("distance_km", 20.0))
                for o in region_orders
            )
            consolidated = calc.calculate_shipping_cost(total_weight, 20.0) * 0.8
            saving = original - consolidated
            groups.append(
                ConsolidationGroup(
                    group_id=group_id,
                    order_ids=order_ids,
                    region=region,
                    estimated_saving=round(max(saving, 0), 2),
                    original_cost=round(original, 2),
                    consolidated_cost=round(consolidated, 2),
                )
            )
        return groups

    def calculate_saving(self, group: ConsolidationGroup) -> float:
        return group.estimated_saving

    def can_consolidate(self, order1: dict, order2: dict) -> bool:
        same_region = order1.get("region") == order2.get("region")
        same_day = order1.get("delivery_date") == order2.get("delivery_date")
        return same_region and same_day


class CostOptimizer:
    """종합 물류 비용 최적화기."""

    def __init__(self) -> None:
        self._calc = LogisticsCostCalculator()
        self._selector = CarrierSelector()
        self._consolidation = ConsolidationManager()

    def optimize_route_costs(self, stops: list, available_carriers: list) -> dict:
        total_weight = sum(s.get("weight_kg", 1.0) if isinstance(s, dict) else getattr(s, "weight_kg", 1.0) for s in stops)
        total_distance = sum(s.get("distance_km", 5.0) if isinstance(s, dict) else 5.0 for s in stops)
        costs = self._calc.calculate_total_cost(total_weight, total_distance, len(stops))
        recommended = self._selector.recommend_carrier(total_weight, "서울", "cost")
        return {
            "optimized_costs": costs,
            "recommended_carrier": recommended.to_dict(),
            "stop_count": len(stops),
        }

    def compare_shipping_methods(self, weight_kg: float, distance_km: float) -> list:
        result = []
        for carrier in self._selector.get_carriers():
            cost = self._calc.calculate_shipping_cost(weight_kg, distance_km, carrier.carrier_id)
            result.append({
                "carrier": carrier.to_dict(),
                "cost": round(cost, 2),
                "estimated_days": carrier.avg_delivery_days,
            })
        result.sort(key=lambda x: x["cost"])
        return result

    def find_consolidation_opportunities(self, orders: list) -> list:
        return self._consolidation.analyze_consolidation(orders)
