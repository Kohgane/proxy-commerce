"""창고 CRUD + 위치 관리."""
from __future__ import annotations
import uuid
from .models import Warehouse, StorageZone, StorageLocation

class WarehouseManager:
    def __init__(self) -> None:
        self._warehouses: dict[str, Warehouse] = {}

    def create(self, name: str, address: str, capacity: int) -> Warehouse:
        wh = Warehouse(
            warehouse_id=str(uuid.uuid4()),
            name=name,
            address=address,
            capacity=capacity,
        )
        self._warehouses[wh.warehouse_id] = wh
        return wh

    def get(self, warehouse_id: str) -> Warehouse | None:
        return self._warehouses.get(warehouse_id)

    def list(self, active_only: bool = False) -> list[Warehouse]:
        whs = list(self._warehouses.values())
        if active_only:
            whs = [w for w in whs if w.is_active]
        return whs

    def add_zone(self, warehouse_id: str, name: str, zone_type: str = "general") -> StorageZone | None:
        wh = self._warehouses.get(warehouse_id)
        if not wh:
            return None
        zone = StorageZone(zone_id=str(uuid.uuid4()), name=name, zone_type=zone_type)
        wh.zones.append(zone)
        return zone

    def add_location(self, warehouse_id: str, zone_id: str, aisle: str, row: int, level: int) -> StorageLocation | None:
        wh = self._warehouses.get(warehouse_id)
        if not wh:
            return None
        for zone in wh.zones:
            if zone.zone_id == zone_id:
                loc = StorageLocation(location_id=str(uuid.uuid4()), aisle=aisle, row=row, level=level)
                zone.locations.append(loc)
                return loc
        return None

    def update(self, warehouse_id: str, **kwargs) -> Warehouse | None:
        wh = self._warehouses.get(warehouse_id)
        if not wh:
            return None
        for k, v in kwargs.items():
            setattr(wh, k, v)
        return wh
