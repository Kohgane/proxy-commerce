"""적재율 계산 + 공간 최적화 제안."""
from __future__ import annotations
from .models import Warehouse

class SpaceOptimizer:
    def utilization(self, warehouse: Warehouse) -> dict:
        rate = (warehouse.current_usage / warehouse.capacity) if warehouse.capacity > 0 else 0
        return {
            "warehouse_id": warehouse.warehouse_id,
            "capacity": warehouse.capacity,
            "current_usage": warehouse.current_usage,
            "utilization_rate": round(rate, 4),
        }

    def suggestions(self, warehouse: Warehouse) -> list[str]:
        rate = (warehouse.current_usage / warehouse.capacity) if warehouse.capacity > 0 else 0
        tips = []
        if rate > 0.9:
            tips.append("창고 사용률이 90%를 초과했습니다. 추가 창고 확보를 권장합니다.")
        if rate > 0.75:
            tips.append("고회전 상품을 출구 근처로 이동하세요.")
        if rate < 0.3:
            tips.append("창고 사용률이 낮습니다. 통합 배치를 고려하세요.")
        return tips
