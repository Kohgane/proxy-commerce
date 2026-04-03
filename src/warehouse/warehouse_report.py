"""창고 리포트."""
from __future__ import annotations
from .models import Warehouse

class WarehouseReport:
    def status(self, warehouse: Warehouse) -> dict:
        zone_count = len(warehouse.zones)
        loc_count = sum(len(z.locations) for z in warehouse.zones)
        return {
            "warehouse_id": warehouse.warehouse_id,
            "name": warehouse.name,
            "capacity": warehouse.capacity,
            "current_usage": warehouse.current_usage,
            "zone_count": zone_count,
            "location_count": loc_count,
            "is_active": warehouse.is_active,
        }

    def all_status(self, warehouses: list[Warehouse]) -> list[dict]:
        return [self.status(wh) for wh in warehouses]
