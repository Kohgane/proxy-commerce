"""tests/test_warehouse.py — Phase 89: 창고 관리 시스템 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.warehouse import (
    Warehouse,
    StorageZone,
    StorageLocation,
    WarehouseManager,
    PickingOrder,
    WarehouseTransfer,
    SpaceOptimizer,
    WarehouseReport,
)


class TestWarehouseModels:
    def test_warehouse_dataclass(self):
        wh = Warehouse(
            warehouse_id='wh1',
            name='메인창고',
            address='서울시 강남구',
            capacity=10000,
        )
        assert wh.warehouse_id == 'wh1'
        assert wh.is_active
        assert wh.current_usage == 0

    def test_storage_zone(self):
        zone = StorageZone(zone_id='z1', name='일반구역', zone_type='general')
        assert zone.zone_id == 'z1'
        assert zone.locations == []

    def test_storage_location(self):
        loc = StorageLocation(location_id='l1', aisle='A', row=1, level=2)
        assert loc.location_id == 'l1'
        assert loc.aisle == 'A'
        assert loc.quantity == 0


class TestWarehouseManager:
    def test_create(self):
        mgr = WarehouseManager()
        wh = mgr.create(name='메인창고', address='서울', capacity=10000)
        assert wh.warehouse_id
        assert wh.name == '메인창고'
        assert wh.capacity == 10000

    def test_get(self):
        mgr = WarehouseManager()
        wh = mgr.create('메인창고', '서울', 10000)
        found = mgr.get(wh.warehouse_id)
        assert found is not None
        assert found.name == '메인창고'

    def test_get_not_found(self):
        mgr = WarehouseManager()
        assert mgr.get('nonexistent') is None

    def test_list(self):
        mgr = WarehouseManager()
        mgr.create('창고1', '서울', 5000)
        mgr.create('창고2', '부산', 3000)
        whs = mgr.list()
        assert len(whs) == 2

    def test_list_active_only(self):
        mgr = WarehouseManager()
        wh1 = mgr.create('창고1', '서울', 5000)
        wh2 = mgr.create('창고2', '부산', 3000)
        mgr.update(wh2.warehouse_id, is_active=False)
        active = mgr.list(active_only=True)
        assert len(active) == 1

    def test_add_zone(self):
        mgr = WarehouseManager()
        wh = mgr.create('창고', '서울', 1000)
        zone = mgr.add_zone(wh.warehouse_id, name='냉장구역', zone_type='refrigerated')
        assert zone is not None
        assert zone.zone_type == 'refrigerated'
        assert len(mgr.get(wh.warehouse_id).zones) == 1

    def test_add_zone_not_found(self):
        mgr = WarehouseManager()
        zone = mgr.add_zone('nonexistent', 'zone')
        assert zone is None

    def test_add_location(self):
        mgr = WarehouseManager()
        wh = mgr.create('창고', '서울', 1000)
        zone = mgr.add_zone(wh.warehouse_id, '일반구역')
        loc = mgr.add_location(wh.warehouse_id, zone.zone_id, aisle='A', row=1, level=1)
        assert loc is not None
        assert loc.aisle == 'A'

    def test_update(self):
        mgr = WarehouseManager()
        wh = mgr.create('창고', '서울', 1000)
        updated = mgr.update(wh.warehouse_id, current_usage=500)
        assert updated.current_usage == 500


class TestPickingOrder:
    def test_create(self):
        picking = PickingOrder()
        items = [
            {'sku': 'S1', 'aisle': 'B', 'row': 2, 'level': 1},
            {'sku': 'S2', 'aisle': 'A', 'row': 1, 'level': 1},
        ]
        order = picking.create(order_id='ORD-001', items=items)
        assert order['pick_id']
        assert order['order_id'] == 'ORD-001'
        assert order['status'] == 'pending'
        # Items should be sorted: A before B
        assert order['items'][0]['aisle'] == 'A'

    def test_create_empty_items(self):
        picking = PickingOrder()
        order = picking.create(order_id='ORD-001', items=[])
        assert order['items'] == []

    def test_complete(self):
        picking = PickingOrder()
        order = picking.create(order_id='ORD-001', items=[])
        completed = picking.complete(order['pick_id'])
        assert completed['status'] == 'completed'

    def test_list(self):
        picking = PickingOrder()
        picking.create('ORD-001', [])
        picking.create('ORD-002', [])
        orders = picking.list()
        assert len(orders) == 2


class TestWarehouseTransfer:
    def test_create(self):
        transfer = WarehouseTransfer()
        result = transfer.create(
            from_warehouse_id='wh1',
            to_warehouse_id='wh2',
            items=[{'sku': 'SKU-001', 'qty': 50}],
        )
        assert result['transfer_id']
        assert result['status'] == 'pending'
        assert result['from_warehouse_id'] == 'wh1'

    def test_advance(self):
        transfer = WarehouseTransfer()
        t = transfer.create('wh1', 'wh2', [])
        t1 = transfer.advance(t['transfer_id'])
        assert t1['status'] == 'in_transit'
        t2 = transfer.advance(t['transfer_id'])
        assert t2['status'] == 'received'

    def test_advance_not_found(self):
        transfer = WarehouseTransfer()
        result = transfer.advance('nonexistent')
        assert result == {}

    def test_list(self):
        transfer = WarehouseTransfer()
        transfer.create('wh1', 'wh2', [])
        transfer.create('wh2', 'wh3', [])
        transfers = transfer.list()
        assert len(transfers) == 2


class TestSpaceOptimizer:
    def test_utilization(self):
        optimizer = SpaceOptimizer()
        wh = Warehouse(warehouse_id='wh1', name='창고', address='서울', capacity=1000, current_usage=750)
        result = optimizer.utilization(wh)
        assert result['utilization_rate'] == 0.75

    def test_utilization_zero_capacity(self):
        optimizer = SpaceOptimizer()
        wh = Warehouse(warehouse_id='wh1', name='창고', address='서울', capacity=0)
        result = optimizer.utilization(wh)
        assert result['utilization_rate'] == 0

    def test_suggestions_high(self):
        optimizer = SpaceOptimizer()
        wh = Warehouse(warehouse_id='wh1', name='창고', address='서울', capacity=1000, current_usage=950)
        tips = optimizer.suggestions(wh)
        assert len(tips) > 0
        assert any('90%' in t for t in tips)

    def test_suggestions_low(self):
        optimizer = SpaceOptimizer()
        wh = Warehouse(warehouse_id='wh1', name='창고', address='서울', capacity=1000, current_usage=100)
        tips = optimizer.suggestions(wh)
        assert len(tips) > 0

    def test_suggestions_normal(self):
        optimizer = SpaceOptimizer()
        wh = Warehouse(warehouse_id='wh1', name='창고', address='서울', capacity=1000, current_usage=500)
        tips = optimizer.suggestions(wh)
        assert tips == []


class TestWarehouseReport:
    def test_status(self):
        report = WarehouseReport()
        wh = Warehouse(warehouse_id='wh1', name='메인창고', address='서울', capacity=5000, current_usage=2000)
        result = report.status(wh)
        assert result['warehouse_id'] == 'wh1'
        assert result['name'] == '메인창고'
        assert result['capacity'] == 5000
        assert result['zone_count'] == 0

    def test_status_with_zones(self):
        report = WarehouseReport()
        mgr = WarehouseManager()
        wh = mgr.create('창고', '서울', 5000)
        zone = mgr.add_zone(wh.warehouse_id, '구역1')
        mgr.add_location(wh.warehouse_id, zone.zone_id, 'A', 1, 1)
        result = report.status(mgr.get(wh.warehouse_id))
        assert result['zone_count'] == 1
        assert result['location_count'] == 1

    def test_all_status(self):
        report = WarehouseReport()
        wh1 = Warehouse(warehouse_id='wh1', name='창고1', address='서울', capacity=1000)
        wh2 = Warehouse(warehouse_id='wh2', name='창고2', address='부산', capacity=2000)
        results = report.all_status([wh1, wh2])
        assert len(results) == 2
