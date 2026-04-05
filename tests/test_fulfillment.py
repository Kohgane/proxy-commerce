"""tests/test_fulfillment.py — Phase 103: 풀필먼트 자동화 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── FulfillmentStatus / FulfillmentOrder ───────────────────────────────────

class TestFulfillmentStatus:
    def test_all_statuses_exist(self):
        from src.fulfillment.engine import FulfillmentStatus
        assert FulfillmentStatus.received == 'received'
        assert FulfillmentStatus.inspecting == 'inspecting'
        assert FulfillmentStatus.packing == 'packing'
        assert FulfillmentStatus.ready_to_ship == 'ready_to_ship'
        assert FulfillmentStatus.shipped == 'shipped'
        assert FulfillmentStatus.in_transit == 'in_transit'
        assert FulfillmentStatus.delivered == 'delivered'

    def test_status_is_str(self):
        from src.fulfillment.engine import FulfillmentStatus
        assert isinstance(FulfillmentStatus.received, str)

    def test_status_values(self):
        from src.fulfillment.engine import FulfillmentStatus
        values = [s.value for s in FulfillmentStatus]
        assert 'received' in values
        assert 'delivered' in values


class TestFulfillmentOrder:
    def test_default_status_is_received(self):
        from src.fulfillment.engine import FulfillmentOrder, FulfillmentStatus
        order = FulfillmentOrder(order_id='test_001')
        assert order.status == FulfillmentStatus.received

    def test_created_at_set_on_init(self):
        from src.fulfillment.engine import FulfillmentOrder
        order = FulfillmentOrder(order_id='test_002')
        assert 'created_at' in order.timestamps

    def test_update_status(self):
        from src.fulfillment.engine import FulfillmentOrder, FulfillmentStatus
        order = FulfillmentOrder(order_id='test_003')
        order.update_status(FulfillmentStatus.inspecting)
        assert order.status == FulfillmentStatus.inspecting
        assert 'inspecting_at' in order.timestamps

    def test_default_items_is_list(self):
        from src.fulfillment.engine import FulfillmentOrder
        order = FulfillmentOrder(order_id='test_004')
        assert isinstance(order.items, list)

    def test_default_recipient_is_dict(self):
        from src.fulfillment.engine import FulfillmentOrder
        order = FulfillmentOrder(order_id='test_005')
        assert isinstance(order.recipient, dict)

    def test_tracking_number_defaults_none(self):
        from src.fulfillment.engine import FulfillmentOrder
        order = FulfillmentOrder(order_id='test_006')
        assert order.tracking_number is None


# ─── FulfillmentEngine ──────────────────────────────────────────────────────

class TestFulfillmentEngine:
    def _make_engine(self):
        from src.fulfillment.engine import FulfillmentEngine
        return FulfillmentEngine()

    def test_create_order_returns_order(self):
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        assert order.order_id.startswith('fulfillment_')

    def test_create_order_stores_items(self):
        engine = self._make_engine()
        items = [{'name': 'item1', 'weight_kg': 1.0}]
        order = engine.create_order(items=items, recipient={})
        assert order.items == items

    def test_get_order_returns_created(self):
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        fetched = engine.get_order(order.order_id)
        assert fetched is order

    def test_get_order_unknown_returns_none(self):
        engine = self._make_engine()
        assert engine.get_order('nonexistent') is None

    def test_list_orders_empty(self):
        engine = self._make_engine()
        assert engine.list_orders() == []

    def test_list_orders_all(self):
        engine = self._make_engine()
        engine.create_order(items=[], recipient={})
        engine.create_order(items=[], recipient={})
        assert len(engine.list_orders()) == 2

    def test_list_orders_by_status(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        engine.create_order(items=[], recipient={})
        o2 = engine.create_order(items=[], recipient={})
        engine.advance_to_inspecting(o2.order_id)
        received = engine.list_orders(status=FulfillmentStatus.received)
        assert len(received) == 1

    def test_advance_to_inspecting(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        engine.advance_to_inspecting(order.order_id)
        assert order.status == FulfillmentStatus.inspecting

    def test_advance_to_packing(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        engine.advance_to_inspecting(order.order_id)
        engine.advance_to_packing(order.order_id, {'grade': 'A'})
        assert order.status == FulfillmentStatus.packing
        assert order.inspection_result == {'grade': 'A'}

    def test_advance_to_ready(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        engine.advance_to_ready(order.order_id, {'packing_id': 'p1'})
        assert order.status == FulfillmentStatus.ready_to_ship
        assert order.packing_result == {'packing_id': 'p1'}

    def test_advance_to_shipped(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        engine.advance_to_shipped(order.order_id, 'CJ123456', 'cj_logistics')
        assert order.status == FulfillmentStatus.shipped
        assert order.tracking_number == 'CJ123456'
        assert order.carrier == 'cj_logistics'

    def test_advance_to_in_transit(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        engine.advance_to_in_transit(order.order_id)
        assert order.status == FulfillmentStatus.in_transit

    def test_advance_to_delivered(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={})
        engine.advance_to_delivered(order.order_id)
        assert order.status == FulfillmentStatus.delivered

    def test_get_stats_empty(self):
        engine = self._make_engine()
        stats = engine.get_stats()
        assert stats['total'] == 0
        assert 'by_status' in stats

    def test_get_stats_counts(self):
        from src.fulfillment.engine import FulfillmentStatus
        engine = self._make_engine()
        engine.create_order(items=[], recipient={})
        o2 = engine.create_order(items=[], recipient={})
        engine.advance_to_shipped(o2.order_id, 'TRK1', 'cj_logistics')
        stats = engine.get_stats()
        assert stats['total'] == 2
        assert stats['by_status']['received'] == 1
        assert stats['by_status']['shipped'] == 1

    def test_advance_unknown_order_raises(self):
        engine = self._make_engine()
        with pytest.raises(KeyError):
            engine.advance_to_inspecting('bogus_id')

    def test_metadata_stored(self):
        engine = self._make_engine()
        order = engine.create_order(items=[], recipient={}, metadata={'source': 'test'})
        assert order.metadata == {'source': 'test'}


# ─── InspectionGrade / InspectionResult ─────────────────────────────────────

class TestInspectionGrade:
    def test_grades_exist(self):
        from src.fulfillment.inspection import InspectionGrade
        assert InspectionGrade.A == 'A'
        assert InspectionGrade.B == 'B'
        assert InspectionGrade.C == 'C'
        assert InspectionGrade.D == 'D'


class TestInspectionService:
    def _make_svc(self):
        from src.fulfillment.inspection import InspectionService
        return InspectionService()

    def test_inspect_returns_result(self):
        svc = self._make_svc()
        result = svc.inspect('order_001', [])
        assert result.order_id == 'order_001'

    def test_inspect_default_grade_a(self):
        from src.fulfillment.inspection import InspectionGrade
        svc = self._make_svc()
        result = svc.inspect('order_002', [])
        assert result.grade == InspectionGrade.A

    def test_inspect_defect_lowers_grade(self):
        from src.fulfillment.inspection import InspectionGrade
        svc = self._make_svc()
        result = svc.inspect('order_003', [{'grade': 'C', 'defect_type': 'scratch'}])
        assert result.grade == InspectionGrade.C

    def test_inspect_grade_d_requires_return(self):
        svc = self._make_svc()
        result = svc.inspect('order_004', [{'grade': 'D', 'defect_type': 'broken'}])
        assert result.requires_return is True

    def test_inspect_grade_a_no_return(self):
        svc = self._make_svc()
        result = svc.inspect('order_005', [])
        assert result.requires_return is False

    def test_inspect_photo_urls_generated(self):
        svc = self._make_svc()
        result = svc.inspect('order_006', [])
        assert len(result.photo_urls) == 2

    def test_inspect_defect_types_collected(self):
        svc = self._make_svc()
        result = svc.inspect('order_007', [{'defect_type': 'dent'}, {'defect_type': 'stain'}])
        assert 'dent' in result.defect_types
        assert 'stain' in result.defect_types

    def test_get_history_all(self):
        svc = self._make_svc()
        svc.inspect('order_a', [])
        svc.inspect('order_b', [])
        assert len(svc.get_history()) == 2

    def test_get_history_by_order_id(self):
        svc = self._make_svc()
        svc.inspect('order_a', [])
        svc.inspect('order_b', [])
        hist = svc.get_history('order_a')
        assert len(hist) == 1
        assert hist[0].order_id == 'order_a'

    def test_get_stats(self):
        svc = self._make_svc()
        svc.inspect('o1', [])
        svc.inspect('o2', [{'grade': 'D', 'defect_type': 'broken'}])
        stats = svc.get_stats()
        assert stats['total'] == 2
        assert stats['by_grade']['A'] == 1
        assert stats['by_grade']['D'] == 1
        assert stats['return_count'] == 1

    def test_inspection_id_unique(self):
        svc = self._make_svc()
        r1 = svc.inspect('o1', [])
        r2 = svc.inspect('o2', [])
        assert r1.inspection_id != r2.inspection_id

    def test_invalid_grade_ignored(self):
        from src.fulfillment.inspection import InspectionGrade
        svc = self._make_svc()
        result = svc.inspect('o1', [{'grade': 'Z'}])
        assert result.grade == InspectionGrade.A


# ─── PackingType / PackingService ───────────────────────────────────────────

class TestPackingType:
    def test_packing_types_exist(self):
        from src.fulfillment.packing import PackingType
        assert PackingType.standard == 'standard'
        assert PackingType.fragile == 'fragile'
        assert PackingType.oversized == 'oversized'
        assert PackingType.multi_item == 'multi_item'


class TestPackingService:
    def _make_svc(self):
        from src.fulfillment.packing import PackingService
        return PackingService()

    def test_pack_returns_result(self):
        svc = self._make_svc()
        result = svc.pack('order_001', [{'weight_kg': 1.0}])
        assert result.order_id == 'order_001'

    def test_pack_standard_single_item(self):
        from src.fulfillment.packing import PackingType
        svc = self._make_svc()
        result = svc.pack('order_002', [{'weight_kg': 1.0}])
        assert result.packing_type == PackingType.standard

    def test_pack_fragile_item(self):
        from src.fulfillment.packing import PackingType
        svc = self._make_svc()
        result = svc.pack('order_003', [{'fragile': True, 'weight_kg': 0.5}])
        assert result.packing_type == PackingType.fragile

    def test_pack_oversized_item(self):
        from src.fulfillment.packing import PackingType
        svc = self._make_svc()
        result = svc.pack('order_004', [{'weight_kg': 15.0}])
        assert result.packing_type == PackingType.oversized

    def test_pack_oversized_flag(self):
        from src.fulfillment.packing import PackingType
        svc = self._make_svc()
        result = svc.pack('order_005', [{'oversized': True, 'weight_kg': 1.0}])
        assert result.packing_type == PackingType.oversized

    def test_pack_multi_item(self):
        from src.fulfillment.packing import PackingType
        svc = self._make_svc()
        result = svc.pack('order_006', [{'weight_kg': 1.0}, {'weight_kg': 0.5}])
        assert result.packing_type == PackingType.multi_item

    def test_pack_empty_items_standard(self):
        from src.fulfillment.packing import PackingType
        svc = self._make_svc()
        result = svc.pack('order_007', [])
        assert result.packing_type == PackingType.standard

    def test_pack_weight_calculation(self):
        svc = self._make_svc()
        result = svc.pack('order_008', [{'weight_kg': 1.0}, {'weight_kg': 2.0}])
        assert result.weight_kg == pytest.approx(3.3, abs=0.01)

    def test_pack_materials_not_empty(self):
        svc = self._make_svc()
        result = svc.pack('order_009', [{'weight_kg': 1.0}])
        assert len(result.materials_used) > 0

    def test_pack_dimensions_returned(self):
        svc = self._make_svc()
        result = svc.pack('order_010', [{'weight_kg': 1.0}])
        assert 'length' in result.dimensions_cm
        assert 'width' in result.dimensions_cm
        assert 'height' in result.dimensions_cm

    def test_get_results_all(self):
        svc = self._make_svc()
        svc.pack('o1', [])
        svc.pack('o2', [])
        assert len(svc.get_results()) == 2

    def test_get_results_by_order(self):
        svc = self._make_svc()
        svc.pack('o1', [])
        svc.pack('o2', [])
        results = svc.get_results('o1')
        assert len(results) == 1

    def test_consolidate_orders(self):
        svc = self._make_svc()
        group_id = svc.consolidate_orders('recipient_key_1', ['o1', 'o2', 'o3'])
        assert group_id.startswith('consolidation_')

    def test_get_stats(self):
        svc = self._make_svc()
        svc.pack('o1', [{'weight_kg': 1.0}])
        svc.pack('o2', [{'fragile': True, 'weight_kg': 0.5}])
        stats = svc.get_stats()
        assert stats['total'] == 2
        assert stats['by_type']['standard'] == 1
        assert stats['by_type']['fragile'] == 1


# ─── CarrierAdapter / CarrierSelector ───────────────────────────────────────

class TestCJLogisticsAdapter:
    def _make(self):
        from src.fulfillment.shipping import CJLogisticsAdapter
        return CJLogisticsAdapter()

    def test_carrier_id(self):
        assert self._make().carrier_id == 'cj_logistics'

    def test_name(self):
        assert self._make().name == 'CJ대한통운'

    def test_base_cost(self):
        assert self._make().base_cost_krw == 3500

    def test_avg_days(self):
        assert self._make().avg_delivery_days == 1.5

    def test_create_waybill(self):
        adapter = self._make()
        waybill = adapter.create_waybill('o1', {'name': '홍길동'}, {'weight_kg': 1.0})
        assert waybill['tracking_number'].startswith('CJ')
        assert 'label_url' in waybill

    def test_request_pickup(self):
        adapter = self._make()
        result = adapter.request_pickup('CJ123456')
        assert result['pickup_status'] == 'requested'

    def test_get_tracking(self):
        adapter = self._make()
        result = adapter.get_tracking('CJ123456')
        assert result['status'] == 'in_transit'
        assert len(result['events']) > 0


class TestHanjinAdapter:
    def _make(self):
        from src.fulfillment.shipping import HanjinAdapter
        return HanjinAdapter()

    def test_carrier_id(self):
        assert self._make().carrier_id == 'hanjin'

    def test_base_cost(self):
        assert self._make().base_cost_krw == 3300

    def test_create_waybill_prefix(self):
        waybill = self._make().create_waybill('o1', {}, {})
        assert waybill['tracking_number'].startswith('HJ')


class TestLotteAdapter:
    def _make(self):
        from src.fulfillment.shipping import LotteAdapter
        return LotteAdapter()

    def test_carrier_id(self):
        assert self._make().carrier_id == 'lotte'

    def test_base_cost(self):
        assert self._make().base_cost_krw == 3200

    def test_create_waybill_prefix(self):
        waybill = self._make().create_waybill('o1', {}, {})
        assert waybill['tracking_number'].startswith('LT')


class TestCarrierSelector:
    def _make(self):
        from src.fulfillment.shipping import CarrierSelector
        return CarrierSelector()

    def test_list_carriers_count(self):
        selector = self._make()
        carriers = selector.list_carriers()
        assert len(carriers) == 3

    def test_list_carriers_has_fields(self):
        selector = self._make()
        for c in selector.list_carriers():
            assert 'carrier_id' in c
            assert 'name' in c
            assert 'base_cost_krw' in c
            assert 'avg_delivery_days' in c

    def test_recommend_balanced(self):
        selector = self._make()
        carrier = selector.recommend(strategy='balanced')
        assert carrier is not None

    def test_recommend_cheapest(self):
        from src.fulfillment.shipping import LotteAdapter
        selector = self._make()
        carrier = selector.recommend(strategy='cheapest')
        assert carrier.base_cost_krw == 3200  # Lotte is cheapest

    def test_recommend_fastest(self):
        from src.fulfillment.shipping import CJLogisticsAdapter
        selector = self._make()
        carrier = selector.recommend(strategy='fastest')
        assert carrier.avg_delivery_days == 1.5  # CJ is fastest

    def test_get_carrier_by_id(self):
        selector = self._make()
        carrier = selector.get_carrier('hanjin')
        assert carrier is not None
        assert carrier.carrier_id == 'hanjin'

    def test_get_carrier_unknown_returns_none(self):
        selector = self._make()
        assert selector.get_carrier('unknown_carrier') is None


class TestDomesticShippingManager:
    def _make(self):
        from src.fulfillment.shipping import DomesticShippingManager
        return DomesticShippingManager()

    def test_ship_returns_shipment(self):
        mgr = self._make()
        shipment = mgr.ship('o1', {'name': '홍길동'}, {'weight_kg': 1.0})
        assert 'tracking_number' in shipment

    def test_ship_stores_shipment(self):
        mgr = self._make()
        shipment = mgr.ship('o1', {}, {'weight_kg': 1.0})
        assert len(mgr.list_shipments()) == 1

    def test_ship_with_carrier_id(self):
        mgr = self._make()
        shipment = mgr.ship('o1', {}, {'weight_kg': 1.0}, carrier_id='hanjin')
        assert shipment['carrier_id'] == 'hanjin'

    def test_ship_with_unknown_carrier_raises(self):
        mgr = self._make()
        with pytest.raises(ValueError):
            mgr.ship('o1', {}, {'weight_kg': 1.0}, carrier_id='bogus_carrier')

    def test_get_tracking_cj(self):
        mgr = self._make()
        result = mgr.get_tracking('CJ123456789012')
        assert result['status'] == 'in_transit'

    def test_get_tracking_hanjin(self):
        mgr = self._make()
        result = mgr.get_tracking('HJ123456789012')
        assert result['carrier_id'] == 'hanjin'

    def test_get_tracking_lotte(self):
        mgr = self._make()
        result = mgr.get_tracking('LT123456789012')
        assert result['carrier_id'] == 'lotte'

    def test_get_tracking_unknown(self):
        mgr = self._make()
        result = mgr.get_tracking('XX999999')
        assert result['status'] == 'unknown'

    def test_get_stats(self):
        mgr = self._make()
        mgr.ship('o1', {}, {'weight_kg': 1.0}, carrier_id='cj_logistics')
        mgr.ship('o2', {}, {'weight_kg': 1.0}, carrier_id='hanjin')
        stats = mgr.get_stats()
        assert stats['total'] == 2
        assert stats['by_carrier']['cj_logistics'] == 1
        assert stats['by_carrier']['hanjin'] == 1


# ─── TrackingNumberManager / DeliveryTracker ────────────────────────────────

class TestTrackingNumberManager:
    def _make(self):
        from src.fulfillment.tracking import TrackingNumberManager
        return TrackingNumberManager()

    def test_register_returns_record(self):
        mgr = self._make()
        record = mgr.register('o1', 'CJ12345', 'cj_logistics')
        assert record.tracking_number == 'CJ12345'
        assert record.order_id == 'o1'

    def test_register_success_true_by_default(self):
        mgr = self._make()
        record = mgr.register('o1', 'CJ12345', 'cj_logistics')
        assert record.registration_success is True

    def test_register_to_different_platforms(self):
        mgr = self._make()
        record1 = mgr.register('o1', 'TRK1', 'cj_logistics', platform='coupang')
        record2 = mgr.register('o2', 'TRK2', 'hanjin', platform='naver')
        assert record1.platform == 'coupang'
        assert record2.platform == 'naver'

    def test_get_history_all(self):
        mgr = self._make()
        mgr.register('o1', 'TRK1', 'cj_logistics')
        mgr.register('o2', 'TRK2', 'hanjin')
        assert len(mgr.get_history()) == 2

    def test_get_history_by_order(self):
        mgr = self._make()
        mgr.register('o1', 'TRK1', 'cj_logistics')
        mgr.register('o2', 'TRK2', 'hanjin')
        hist = mgr.get_history('o1')
        assert len(hist) == 1

    def test_get_record_by_tracking_number(self):
        mgr = self._make()
        mgr.register('o1', 'TRK_UNIQUE', 'cj_logistics')
        record = mgr.get_record('TRK_UNIQUE')
        assert record is not None
        assert record.tracking_number == 'TRK_UNIQUE'

    def test_get_record_unknown_returns_none(self):
        mgr = self._make()
        assert mgr.get_record('DOES_NOT_EXIST') is None

    def test_get_stats(self):
        mgr = self._make()
        mgr.register('o1', 'TRK1', 'cj_logistics')
        mgr.register('o2', 'TRK2', 'hanjin')
        stats = mgr.get_stats()
        assert stats['total'] == 2
        assert stats['success'] == 2
        assert stats['failed'] == 0

    def test_tracking_id_unique(self):
        mgr = self._make()
        r1 = mgr.register('o1', 'TRK1', 'cj_logistics')
        r2 = mgr.register('o2', 'TRK2', 'hanjin')
        assert r1.tracking_id != r2.tracking_id


class TestDeliveryStatus:
    def test_status_values(self):
        from src.fulfillment.tracking import DeliveryStatus
        assert DeliveryStatus.picked_up == 'picked_up'
        assert DeliveryStatus.in_transit == 'in_transit'
        assert DeliveryStatus.out_for_delivery == 'out_for_delivery'
        assert DeliveryStatus.delivered == 'delivered'
        assert DeliveryStatus.failed == 'failed'


class TestDeliveryTracker:
    def _make(self):
        from src.fulfillment.tracking import DeliveryTracker
        return DeliveryTracker()

    def test_start_tracking(self):
        tracker = self._make()
        tracker.start_tracking('CJ123', 'cj_logistics')
        status = tracker.get_status('CJ123')
        assert status['status'] == 'picked_up'
        assert len(status['events']) == 1

    def test_update_status(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.start_tracking('CJ123', 'cj_logistics')
        tracker.update_status('CJ123', DeliveryStatus.in_transit, '물류센터', '이동 중')
        status = tracker.get_status('CJ123')
        assert status['status'] == 'in_transit'

    def test_update_status_delivered(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.start_tracking('CJ123', 'cj_logistics')
        tracker.update_status('CJ123', DeliveryStatus.delivered, '배송지', '배송 완료')
        status = tracker.get_status('CJ123')
        assert status['status'] == 'delivered'

    def test_update_status_failed(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.start_tracking('CJ123', 'cj_logistics')
        tracker.update_status('CJ123', DeliveryStatus.failed, '배송지', '배송 실패')
        status = tracker.get_status('CJ123')
        assert status['status'] == 'failed'

    def test_get_status_unknown_defaults_in_transit(self):
        tracker = self._make()
        status = tracker.get_status('UNKNOWN_TRK')
        assert status['status'] == 'in_transit'

    def test_estimate_eta_delivered_is_zero(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.start_tracking('CJ123', 'cj_logistics')
        tracker.update_status('CJ123', DeliveryStatus.delivered)
        eta = tracker.estimate_eta('CJ123', 'cj_logistics')
        assert eta == 0.0

    def test_estimate_eta_by_carrier(self):
        tracker = self._make()
        tracker.start_tracking('CJ123', 'cj_logistics')
        eta = tracker.estimate_eta('CJ123', 'cj_logistics')
        assert eta == 1.5

    def test_get_all_active(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.start_tracking('TRK1', 'cj_logistics')
        tracker.start_tracking('TRK2', 'hanjin')
        tracker.update_status('TRK2', DeliveryStatus.delivered)
        active = tracker.get_all_active()
        assert len(active) == 1
        assert active[0]['tracking_number'] == 'TRK1'

    def test_get_stats(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.start_tracking('TRK1', 'cj_logistics')
        tracker.start_tracking('TRK2', 'hanjin')
        tracker.update_status('TRK2', DeliveryStatus.delivered)
        stats = tracker.get_stats()
        assert stats['total'] == 2
        assert stats['active'] == 1

    def test_update_without_prior_start(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.update_status('NOSTART', DeliveryStatus.in_transit, 'loc', 'desc')
        status = tracker.get_status('NOSTART')
        assert status['status'] == 'in_transit'

    def test_events_accumulate(self):
        from src.fulfillment.tracking import DeliveryStatus
        tracker = self._make()
        tracker.start_tracking('TRK1', 'cj_logistics')
        tracker.update_status('TRK1', DeliveryStatus.in_transit)
        tracker.update_status('TRK1', DeliveryStatus.out_for_delivery)
        status = tracker.get_status('TRK1')
        assert len(status['events']) == 3


# ─── FulfillmentDashboard ───────────────────────────────────────────────────

class TestFulfillmentDashboard:
    def _make_dashboard(self):
        from src.fulfillment.engine import FulfillmentEngine
        from src.fulfillment.inspection import InspectionService
        from src.fulfillment.packing import PackingService
        from src.fulfillment.shipping import DomesticShippingManager
        from src.fulfillment.tracking import TrackingNumberManager, DeliveryTracker
        from src.fulfillment.dashboard import FulfillmentDashboard
        return FulfillmentDashboard(
            engine=FulfillmentEngine(),
            inspection_service=InspectionService(),
            packing_service=PackingService(),
            shipping_manager=DomesticShippingManager(),
            tracking_manager=TrackingNumberManager(),
            delivery_tracker=DeliveryTracker(),
        )

    def test_get_summary_keys(self):
        dashboard = self._make_dashboard()
        summary = dashboard.get_summary()
        assert 'fulfillment_orders' in summary
        assert 'inspection' in summary
        assert 'packing' in summary
        assert 'shipping' in summary
        assert 'tracking' in summary
        assert 'delivery' in summary
        assert 'generated_at' in summary

    def test_get_summary_no_services(self):
        from src.fulfillment.dashboard import FulfillmentDashboard
        dashboard = FulfillmentDashboard()
        summary = dashboard.get_summary()
        assert summary['fulfillment_orders'] == {}

    def test_get_processing_stats(self):
        dashboard = self._make_dashboard()
        stats = dashboard.get_processing_stats()
        assert 'received' in stats
        assert 'delivered' in stats

    def test_get_carrier_performance_empty(self):
        dashboard = self._make_dashboard()
        perf = dashboard.get_carrier_performance()
        assert perf == []

    def test_get_carrier_performance_with_shipments(self):
        from src.fulfillment.engine import FulfillmentEngine
        from src.fulfillment.shipping import DomesticShippingManager
        from src.fulfillment.dashboard import FulfillmentDashboard
        engine = FulfillmentEngine()
        shipping = DomesticShippingManager()
        shipping.ship('o1', {}, {'weight_kg': 1.0}, carrier_id='cj_logistics')
        dashboard = FulfillmentDashboard(engine=engine, shipping_manager=shipping)
        perf = dashboard.get_carrier_performance()
        assert len(perf) == 1
        assert perf[0]['carrier_id'] == 'cj_logistics'

    def test_generated_at_is_isoformat(self):
        dashboard = self._make_dashboard()
        summary = dashboard.get_summary()
        datetime.fromisoformat(summary['generated_at'])


# ─── Package __init__ exports ────────────────────────────────────────────────

class TestPackageExports:
    def test_fulfillment_engine_exported(self):
        from src.fulfillment import FulfillmentEngine
        assert FulfillmentEngine is not None

    def test_fulfillment_order_exported(self):
        from src.fulfillment import FulfillmentOrder
        assert FulfillmentOrder is not None

    def test_inspection_service_exported(self):
        from src.fulfillment import InspectionService
        assert InspectionService is not None

    def test_packing_service_exported(self):
        from src.fulfillment import PackingService
        assert PackingService is not None

    def test_shipping_manager_exported(self):
        from src.fulfillment import DomesticShippingManager
        assert DomesticShippingManager is not None

    def test_tracking_manager_exported(self):
        from src.fulfillment import TrackingNumberManager
        assert TrackingNumberManager is not None

    def test_delivery_tracker_exported(self):
        from src.fulfillment import DeliveryTracker
        assert DeliveryTracker is not None

    def test_dashboard_exported(self):
        from src.fulfillment import FulfillmentDashboard
        assert FulfillmentDashboard is not None


# ─── API Blueprint ───────────────────────────────────────────────────────────

class TestFulfillmentAPIBlueprint:
    def _make_client(self):
        import importlib
        import src.api.fulfillment_api as api_module
        # Reset module-level singletons
        api_module._engine = None
        api_module._inspection_service = None
        api_module._packing_service = None
        api_module._shipping_manager = None
        api_module._tracking_manager = None
        api_module._delivery_tracker = None
        api_module._dashboard = None

        from flask import Flask
        app = Flask(__name__)
        app.register_blueprint(api_module.fulfillment_bp)
        return app.test_client(), api_module

    def test_create_order(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders', json={
            'items': [{'name': 'item1', 'weight_kg': 1.0}],
            'recipient': {'name': '홍길동', 'address': '서울'}
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'received'

    def test_list_orders_empty(self):
        client, _ = self._make_client()
        resp = client.get('/api/v1/fulfillment/orders')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_get_order_not_found(self):
        client, _ = self._make_client()
        resp = client.get('/api/v1/fulfillment/orders/nonexistent')
        assert resp.status_code == 404

    def test_get_order_found(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders', json={'items': [], 'recipient': {}})
        order_id = resp.get_json()['order_id']
        resp2 = client.get(f'/api/v1/fulfillment/orders/{order_id}')
        assert resp2.status_code == 200

    def test_list_orders_with_status_filter(self):
        client, _ = self._make_client()
        client.post('/api/v1/fulfillment/orders', json={'items': [], 'recipient': {}})
        resp = client.get('/api/v1/fulfillment/orders?status=received')
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_list_orders_invalid_status(self):
        client, _ = self._make_client()
        resp = client.get('/api/v1/fulfillment/orders?status=invalid_status')
        assert resp.status_code == 400

    def test_inspect_order(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders', json={'items': [], 'recipient': {}})
        order_id = resp.get_json()['order_id']
        resp2 = client.post(f'/api/v1/fulfillment/orders/{order_id}/inspect', json={})
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert 'inspection' in data
        assert data['inspection']['grade'] == 'A'

    def test_inspect_order_not_found(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders/bogus/inspect', json={})
        assert resp.status_code == 404

    def test_pack_order(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders', json={
            'items': [{'weight_kg': 1.0}], 'recipient': {}
        })
        order_id = resp.get_json()['order_id']
        resp2 = client.post(f'/api/v1/fulfillment/orders/{order_id}/pack', json={})
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert 'packing' in data

    def test_pack_order_not_found(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders/bogus/pack', json={})
        assert resp.status_code == 404

    def test_ship_order(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders', json={
            'items': [{'weight_kg': 1.0}], 'recipient': {'name': '홍길동'}
        })
        order_id = resp.get_json()['order_id']
        resp2 = client.post(f'/api/v1/fulfillment/orders/{order_id}/ship', json={})
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert 'shipment' in data
        assert data['order']['status'] == 'shipped'

    def test_ship_order_not_found(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders/bogus/ship', json={})
        assert resp.status_code == 404

    def test_get_order_tracking_no_tracking(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders', json={'items': [], 'recipient': {}})
        order_id = resp.get_json()['order_id']
        resp2 = client.get(f'/api/v1/fulfillment/orders/{order_id}/tracking')
        assert resp2.status_code == 404

    def test_get_order_tracking_after_ship(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/orders', json={
            'items': [{'weight_kg': 1.0}], 'recipient': {'name': '홍길동'}
        })
        order_id = resp.get_json()['order_id']
        client.post(f'/api/v1/fulfillment/orders/{order_id}/ship', json={})
        resp2 = client.get(f'/api/v1/fulfillment/orders/{order_id}/tracking')
        assert resp2.status_code == 200

    def test_register_tracking(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/tracking/register', json={
            'order_id': 'o1',
            'tracking_number': 'CJ123456',
            'carrier_id': 'cj_logistics',
        })
        assert resp.status_code == 201

    def test_register_tracking_missing_fields(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/tracking/register', json={
            'order_id': 'o1',
        })
        assert resp.status_code == 400

    def test_get_tracking_by_number(self):
        client, _ = self._make_client()
        resp = client.get('/api/v1/fulfillment/tracking/CJ123456')
        assert resp.status_code == 200

    def test_list_carriers(self):
        client, _ = self._make_client()
        resp = client.get('/api/v1/fulfillment/carriers')
        assert resp.status_code == 200
        carriers = resp.get_json()
        assert len(carriers) == 3

    def test_recommend_carrier(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/carriers/recommend', json={
            'weight_kg': 2.0,
            'strategy': 'cheapest',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'carrier_id' in data

    def test_get_dashboard(self):
        client, _ = self._make_client()
        resp = client.get('/api/v1/fulfillment/dashboard')
        assert resp.status_code == 200

    def test_get_stats(self):
        client, _ = self._make_client()
        resp = client.get('/api/v1/fulfillment/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total' in data

    def test_batch_ship_no_order_ids(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/batch-ship', json={})
        assert resp.status_code == 400

    def test_batch_ship_unknown_orders(self):
        client, _ = self._make_client()
        resp = client.post('/api/v1/fulfillment/batch-ship', json={
            'order_ids': ['nonexistent1', 'nonexistent2']
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] == 0
        assert len(data['errors']) == 2

    def test_batch_ship_success(self):
        client, _ = self._make_client()
        resp1 = client.post('/api/v1/fulfillment/orders', json={
            'items': [{'weight_kg': 1.0}], 'recipient': {'name': '홍길동'}
        })
        resp2 = client.post('/api/v1/fulfillment/orders', json={
            'items': [{'weight_kg': 2.0}], 'recipient': {'name': '김철수'}
        })
        oid1 = resp1.get_json()['order_id']
        oid2 = resp2.get_json()['order_id']
        resp = client.post('/api/v1/fulfillment/batch-ship', json={
            'order_ids': [oid1, oid2]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] == 2
        assert data['total'] == 2
