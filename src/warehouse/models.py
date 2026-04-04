"""창고 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class StorageLocation:
    location_id: str
    aisle: str
    row: int
    level: int
    sku: str = ""
    quantity: int = 0

@dataclass
class StorageZone:
    zone_id: str
    name: str
    zone_type: str = "general"  # general/refrigerated/frozen/hazardous
    locations: list[StorageLocation] = field(default_factory=list)

@dataclass
class Warehouse:
    warehouse_id: str
    name: str
    address: str
    capacity: int
    current_usage: int = 0
    zones: list[StorageZone] = field(default_factory=list)
    is_active: bool = True
