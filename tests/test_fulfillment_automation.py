"""tests/test_fulfillment_automation.py — Phase 84: 풀필먼트 자동화 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── FulfillmentStatus ───────────────────────────────────────────────────────

class TestFulfillmentStatusEnum:
    def test_all_statuses_exist(self):
        from src.fulfillment_automation.models import FulfillmentStatus
        assert FulfillmentStatus.pending == 'pending'
        assert FulfillmentStatus.dispatching == 'dispatching'
        assert FulfillmentStatus.dispatched == 'dispatched'
        assert FulfillmentStatus.tracking_registered == 'tracking_registered'
        assert FulfillmentStatus.in_transit == 'in_transit'
        assert FulfillmentStatus.delivered == 'delivered'
        assert FulfillmentStatus.failed == 'failed'

    def test_status_is_str(self):
        from src.fulfillment_automation.models import FulfillmentStatus
        assert isinstance(FulfillmentStatus.pending, str)

    def test_status_values_list(self):
        from src.fulfillment_automation.models import FulfillmentStatus
        values = [s.value for s in FulfillmentStatus]
        assert 'pending' in values
        assert 'failed' in values


# ─── FulfillmentOrder ────────────────────────────────────────────────────────

class TestFulfillmentOrderModel:
    def _make(self, **kw):
        from src.fulfillment_automation.models import FulfillmentOrder
        return FulfillmentOrder(**kw)

    def test_defaults(self):
        order = self._make()
        assert order.order_id.startswith('fa_')
        assert order.status.value == 'pending'
        assert order.package_ids == []
        assert order.items == []
        assert isinstance(order.metadata, dict)

    def test_custom_values(self):
        order = self._make(
            outbound_request_id='OB-001',
            recipient_name='홍길동',
            recipient_address='서울시 강남구',
        )
        assert order.outbound_request_id == 'OB-001'
        assert order.recipient_name == '홍길동'
        assert order.recipient_address == '서울시 강남구'

    def test_update_status(self):
        from src.fulfillment_automation.models import FulfillmentStatus
        order = self._make()
        old_updated = order.updated_at
        order.update_status(FulfillmentStatus.dispatching)
        assert order.status == FulfillmentStatus.dispatching

    def test_to_dict_keys(self):
        order = self._make()
        d = order.to_dict()
        for key in (
            'order_id', 'outbound_request_id', 'package_ids', 'carrier_id',
            'tracking_number', 'status', 'recipient_name', 'recipient_address',
            'items', 'created_at', 'updated_at', 'metadata',
        ):
            assert key in d, f'Missing key: {key}'

    def test_to_dict_status_is_str(self):
        order = self._make()
        d = order.to_dict()
        assert isinstance(d['status'], str)

    def test_unique_order_ids(self):
        from src.fulfillment_automation.models import FulfillmentOrder
        ids = {FulfillmentOrder().order_id for _ in range(10)}
        assert len(ids) == 10


# ─── DispatchRequest ─────────────────────────────────────────────────────────

class TestDispatchRequestModel:
    def _make(self, **kw):
        from src.fulfillment_automation.models import DispatchRequest
        return DispatchRequest(**kw)

    def test_defaults(self):
        req = self._make()
        assert req.dispatch_id.startswith('disp_')
        assert req.weight_kg == 1.0
        assert req.strategy == 'balanced'

    def test_custom_values(self):
        req = self._make(
            outbound_request_id='OB-002',
            package_ids=['P1', 'P2'],
            carrier_id='cj_logistics',
            weight_kg=2.5,
            strategy='fastest',
        )
        assert req.outbound_request_id == 'OB-002'
        assert req.package_ids == ['P1', 'P2']
        assert req.carrier_id == 'cj_logistics'
        assert req.weight_kg == 2.5
        assert req.strategy == 'fastest'

    def test_to_dict_keys(self):
        req = self._make()
        d = req.to_dict()
        for key in (
            'dispatch_id', 'outbound_request_id', 'package_ids', 'carrier_id',
            'recipient_name', 'recipient_address', 'weight_kg', 'strategy',
            'created_at', 'metadata',
        ):
            assert key in d


# ─── TrackingInfo ────────────────────────────────────────────────────────────

class TestTrackingInfoModel:
    def _make(self, **kw):
        from src.fulfillment_automation.models import TrackingInfo
        return TrackingInfo(**kw)

    def test_defaults(self):
        info = self._make()
        assert info.tracking_id.startswith('trk_')
        assert info.status == 'registered'
        assert info.events == []
        assert info.last_synced_at is None

    def test_custom_values(self):
        info = self._make(
            order_id='fa_001',
            tracking_number='CJ123456789',
            carrier_id='cj_logistics',
            carrier_name='CJ대한통운',
        )
        assert info.order_id == 'fa_001'
        assert info.tracking_number == 'CJ123456789'
        assert info.carrier_id == 'cj_logistics'
        assert info.carrier_name == 'CJ대한통운'

    def test_to_dict_keys(self):
        info = self._make()
        d = info.to_dict()
        for key in (
            'tracking_id', 'order_id', 'tracking_number', 'carrier_id',
            'carrier_name', 'status', 'events', 'registered_at',
            'last_synced_at', 'metadata',
        ):
            assert key in d


# ─── CarrierBase ─────────────────────────────────────────────────────────────

class TestCarrierBase:
    def test_is_abstract(self):
        import abc
        from src.fulfillment_automation.carriers.base import CarrierBase
        assert hasattr(CarrierBase, '__abstractmethods__')
        assert len(CarrierBase.__abstractmethods__) > 0

    def test_abstract_methods_exist(self):
        from src.fulfillment_automation.carriers.base import CarrierBase
        for method in ('carrier_id', 'name', 'base_cost_krw', 'avg_delivery_days',
                       'create_waybill', 'request_pickup', 'get_tracking'):
            assert hasattr(CarrierBase, method)


# ─── CJLogisticsCarrier ──────────────────────────────────────────────────────

class TestCJLogisticsCarrier:
    def _make(self):
        from src.fulfillment_automation.carriers.cj_logistics import CJLogisticsCarrier
        return CJLogisticsCarrier()

    def test_carrier_id(self):
        assert self._make().carrier_id == 'cj_logistics'

    def test_name(self):
        assert self._make().name == 'CJ대한통운'

    def test_base_cost_positive(self):
        assert self._make().base_cost_krw > 0

    def test_avg_delivery_days_positive(self):
        assert self._make().avg_delivery_days > 0

    def test_create_waybill_returns_dict(self):
        carrier = self._make()
        waybill = carrier.create_waybill('order_001', {'name': '홍길동'}, {'weight_kg': 1.0})
        assert isinstance(waybill, dict)
        assert 'tracking_number' in waybill
        assert waybill['tracking_number'].startswith('CJ')
        assert 'label_url' in waybill

    def test_create_waybill_unique_tracking(self):
        carrier = self._make()
        nums = {carrier.create_waybill('o', {}, {})['tracking_number'] for _ in range(5)}
        assert len(nums) == 5

    def test_request_pickup_returns_dict(self):
        carrier = self._make()
        result = carrier.request_pickup('CJ1234567890')
        assert result['pickup_status'] == 'requested'
        assert result['tracking_number'] == 'CJ1234567890'

    def test_get_tracking_returns_dict(self):
        carrier = self._make()
        result = carrier.get_tracking('CJ1234567890')
        assert 'status' in result
        assert 'events' in result
        assert isinstance(result['events'], list)


# ─── HanjinCarrier ───────────────────────────────────────────────────────────

class TestHanjinCarrier:
    def _make(self):
        from src.fulfillment_automation.carriers.hanjin import HanjinCarrier
        return HanjinCarrier()

    def test_carrier_id(self):
        assert self._make().carrier_id == 'hanjin'

    def test_name(self):
        assert self._make().name == '한진택배'

    def test_base_cost_positive(self):
        assert self._make().base_cost_krw > 0

    def test_create_waybill_prefix(self):
        carrier = self._make()
        waybill = carrier.create_waybill('o', {}, {})
        assert waybill['tracking_number'].startswith('HJ')

    def test_request_pickup(self):
        carrier = self._make()
        result = carrier.request_pickup('HJ001')
        assert result['pickup_status'] == 'requested'

    def test_get_tracking(self):
        carrier = self._make()
        result = carrier.get_tracking('HJ001')
        assert 'status' in result
        assert 'events' in result


# ─── LotteCarrier ────────────────────────────────────────────────────────────

class TestLotteCarrier:
    def _make(self):
        from src.fulfillment_automation.carriers.lotte import LotteCarrier
        return LotteCarrier()

    def test_carrier_id(self):
        assert self._make().carrier_id == 'lotte'

    def test_name(self):
        assert self._make().name == '롯데택배'

    def test_base_cost_positive(self):
        assert self._make().base_cost_krw > 0

    def test_create_waybill_prefix(self):
        carrier = self._make()
        waybill = carrier.create_waybill('o', {}, {})
        assert waybill['tracking_number'].startswith('LT')

    def test_request_pickup(self):
        carrier = self._make()
        result = carrier.request_pickup('LT001')
        assert result['pickup_status'] == 'requested'

    def test_get_tracking(self):
        carrier = self._make()
        result = carrier.get_tracking('LT001')
        assert 'status' in result
        assert 'events' in result


# ─── CarrierRegistry ─────────────────────────────────────────────────────────

class TestCarrierRegistry:
    def _make(self):
        from src.fulfillment_automation.dispatcher import CarrierRegistry
        return CarrierRegistry()

    def test_default_carriers_available(self):
        registry = self._make()
        for cid in ('cj_logistics', 'hanjin', 'lotte'):
            carrier = registry.get(cid)
            assert carrier.carrier_id == cid

    def test_get_unknown_raises(self):
        registry = self._make()
        with pytest.raises(KeyError):
            registry.get('unknown_carrier')

    def test_list_carriers(self):
        registry = self._make()
        carriers = registry.list_carriers()
        assert len(carriers) == 3
        ids = [c['carrier_id'] for c in carriers]
        assert 'cj_logistics' in ids
        assert 'hanjin' in ids
        assert 'lotte' in ids

    def test_recommend_balanced(self):
        registry = self._make()
        carrier = registry.recommend(strategy='balanced')
        assert carrier.carrier_id in ('cj_logistics', 'hanjin', 'lotte')

    def test_recommend_cheapest(self):
        registry = self._make()
        carrier = registry.recommend(strategy='cheapest')
        assert carrier.carrier_id == 'lotte'  # lowest cost

    def test_recommend_fastest(self):
        registry = self._make()
        carrier = registry.recommend(strategy='fastest')
        assert carrier.carrier_id == 'cj_logistics'  # lowest avg_delivery_days


# ─── AutoDispatcher ──────────────────────────────────────────────────────────

class TestAutoDispatcher:
    def _make(self):
        from src.fulfillment_automation.dispatcher import AutoDispatcher
        return AutoDispatcher()

    def test_dispatch_with_carrier_id(self):
        from src.fulfillment_automation.models import DispatchRequest, FulfillmentStatus
        dispatcher = self._make()
        req = DispatchRequest(
            outbound_request_id='OB-001',
            package_ids=['PKG-001'],
            carrier_id='cj_logistics',
            recipient_name='테스트',
            recipient_address='서울시',
        )
        order = dispatcher.dispatch(req)
        assert order.status == FulfillmentStatus.dispatched
        assert order.carrier_id == 'cj_logistics'
        assert order.tracking_number.startswith('CJ')

    def test_dispatch_without_carrier_uses_strategy(self):
        from src.fulfillment_automation.models import DispatchRequest, FulfillmentStatus
        dispatcher = self._make()
        req = DispatchRequest(
            outbound_request_id='OB-002',
            strategy='cheapest',
            recipient_name='테스트',
            recipient_address='서울시',
        )
        order = dispatcher.dispatch(req)
        assert order.status == FulfillmentStatus.dispatched
        assert order.tracking_number != ''

    def test_dispatch_sets_order_id(self):
        from src.fulfillment_automation.models import DispatchRequest
        dispatcher = self._make()
        req = DispatchRequest()
        order = dispatcher.dispatch(req)
        assert order.order_id.startswith('fa_')

    def test_dispatch_stores_order(self):
        from src.fulfillment_automation.models import DispatchRequest
        dispatcher = self._make()
        req = DispatchRequest(carrier_id='hanjin')
        order = dispatcher.dispatch(req)
        fetched = dispatcher.get_order(order.order_id)
        assert fetched is order

    def test_get_order_unknown_returns_none(self):
        dispatcher = self._make()
        assert dispatcher.get_order('nonexistent') is None

    def test_list_orders_empty(self):
        dispatcher = self._make()
        assert dispatcher.list_orders() == []

    def test_list_orders_with_status_filter(self):
        from src.fulfillment_automation.models import DispatchRequest, FulfillmentStatus
        dispatcher = self._make()
        for cid in ('cj_logistics', 'hanjin', 'lotte'):
            dispatcher.dispatch(DispatchRequest(carrier_id=cid))
        dispatched = dispatcher.list_orders(FulfillmentStatus.dispatched)
        assert len(dispatched) == 3

    def test_get_stats(self):
        from src.fulfillment_automation.models import DispatchRequest
        dispatcher = self._make()
        dispatcher.dispatch(DispatchRequest(carrier_id='cj_logistics'))
        stats = dispatcher.get_stats()
        assert 'total' in stats
        assert stats['total'] == 1
        assert 'by_status' in stats
        assert 'carriers' in stats

    def test_consume_outbound_confirmed_event(self):
        from src.fulfillment_automation.models import FulfillmentStatus
        dispatcher = self._make()
        event = {
            'outbound_request_id': 'OB-CONFIRM-001',
            'package_ids': ['PKG-A', 'PKG-B'],
            'recipient_name': '이순신',
            'recipient_address': '경기도 수원시',
            'weight_kg': 2.0,
            'carrier_id': 'hanjin',
        }
        order = dispatcher.consume_outbound_confirmed(event)
        assert order.status == FulfillmentStatus.dispatched
        assert order.outbound_request_id == 'OB-CONFIRM-001'
        assert order.package_ids == ['PKG-A', 'PKG-B']
        assert order.carrier_id == 'hanjin'
        assert order.tracking_number.startswith('HJ')

    def test_consume_outbound_confirmed_strategy(self):
        from src.fulfillment_automation.models import FulfillmentStatus
        dispatcher = self._make()
        event = {
            'outbound_request_id': 'OB-STRAT-001',
            'strategy': 'fastest',
        }
        order = dispatcher.consume_outbound_confirmed(event)
        assert order.status == FulfillmentStatus.dispatched

    def test_dispatch_failed_on_bad_carrier(self):
        from src.fulfillment_automation.models import DispatchRequest, FulfillmentStatus
        dispatcher = self._make()
        req = DispatchRequest(carrier_id='invalid_carrier')
        order = dispatcher.dispatch(req)
        assert order.status == FulfillmentStatus.failed
        assert 'error' in order.metadata

    def test_notify_bot_returns_payload(self):
        from src.fulfillment_automation.models import DispatchRequest
        dispatcher = self._make()
        req = DispatchRequest(carrier_id='cj_logistics')
        order = dispatcher.dispatch(req)
        payload = dispatcher.notify_bot(order)
        assert payload['event'] == 'dispatch_completed'
        assert payload['order_id'] == order.order_id


# ─── TrackingRegistry ────────────────────────────────────────────────────────

class TestTrackingRegistry:
    def _make(self):
        from src.fulfillment_automation.tracking_registry import TrackingRegistry
        return TrackingRegistry()

    def test_register_returns_tracking_info(self):
        registry = self._make()
        info = registry.register('fa_001', 'CJ12345', 'cj_logistics')
        assert info.order_id == 'fa_001'
        assert info.tracking_number == 'CJ12345'
        assert info.carrier_id == 'cj_logistics'
        assert info.carrier_name == 'CJ대한통운'
        assert info.status == 'registered'

    def test_register_unknown_carrier_uses_id_as_name(self):
        registry = self._make()
        info = registry.register('fa_002', 'XX999', 'unknown_carrier')
        assert info.carrier_name == 'unknown_carrier'

    def test_get_returns_registered(self):
        registry = self._make()
        registry.register('fa_003', 'HJ99999', 'hanjin')
        info = registry.get('HJ99999')
        assert info is not None
        assert info.carrier_id == 'hanjin'

    def test_get_unknown_returns_none(self):
        registry = self._make()
        assert registry.get('NONEXISTENT') is None

    def test_get_by_order(self):
        registry = self._make()
        registry.register('fa_order_001', 'CJ1', 'cj_logistics')
        registry.register('fa_order_001', 'HJ1', 'hanjin')
        records = registry.get_by_order('fa_order_001')
        assert len(records) == 2

    def test_get_by_order_empty(self):
        registry = self._make()
        assert registry.get_by_order('nonexistent') == []

    def test_list_all(self):
        registry = self._make()
        registry.register('fa_x', 'CJ001', 'cj_logistics')
        registry.register('fa_y', 'HJ001', 'hanjin')
        all_records = registry.list_all()
        assert len(all_records) == 2

    def test_register_from_order(self):
        from src.fulfillment_automation.models import FulfillmentOrder, FulfillmentStatus
        registry = self._make()
        order = FulfillmentOrder(
            order_id='fa_dispatch_001',
            carrier_id='lotte',
            tracking_number='LT99999999',
        )
        info = registry.register_from_order(order)
        assert info is not None
        assert info.tracking_number == 'LT99999999'
        assert order.status == FulfillmentStatus.tracking_registered

    def test_register_from_order_missing_tracking(self):
        from src.fulfillment_automation.models import FulfillmentOrder
        registry = self._make()
        order = FulfillmentOrder(order_id='fa_no_tracking')
        info = registry.register_from_order(order)
        assert info is None

    def test_sync_status(self):
        registry = self._make()
        registry.register('fa_sync', 'CJ_SYNC_001', 'cj_logistics')
        info = registry.sync_status('CJ_SYNC_001')
        assert info.status == 'in_transit'
        assert info.last_synced_at is not None
        assert len(info.events) > 0

    def test_sync_status_unknown_raises(self):
        registry = self._make()
        with pytest.raises(KeyError):
            registry.sync_status('NONEXISTENT_TRK')

    def test_sync_status_unknown_carrier(self):
        registry = self._make()
        info = registry.register('fa_unk', 'XX_TRK_001', 'unknown_carrier')
        synced = registry.sync_status('XX_TRK_001')
        assert synced is info

    def test_sync_all(self):
        registry = self._make()
        registry.register('fa_a', 'CJ_A', 'cj_logistics')
        registry.register('fa_b', 'HJ_B', 'hanjin')
        results = registry.sync_all()
        assert len(results) == 2

    def test_notify_order_tracking_returns_payload(self):
        registry = self._make()
        payload = registry.notify_order_tracking('fa_001', 'CJ99999', 'cj_logistics')
        assert payload['event'] == 'tracking_registered'
        assert payload['order_id'] == 'fa_001'
        assert payload['tracking_number'] == 'CJ99999'


# ─── 통합 플로우 테스트 ───────────────────────────────────────────────────────

class TestFullFulfillmentAutomationFlow:
    """outbound-confirmed → dispatch → tracking_register 전체 플로우."""

    def test_end_to_end_flow(self):
        from src.fulfillment_automation.dispatcher import AutoDispatcher
        from src.fulfillment_automation.models import FulfillmentStatus
        from src.fulfillment_automation.tracking_registry import TrackingRegistry

        dispatcher = AutoDispatcher()
        registry = TrackingRegistry()

        # 1) outbound-confirmed 이벤트 소비
        event = {
            'outbound_request_id': 'OB-E2E-001',
            'package_ids': ['PKG-E2E-001'],
            'recipient_name': '세종대왕',
            'recipient_address': '서울시 종로구',
            'weight_kg': 1.5,
            'carrier_id': 'cj_logistics',
        }
        order = dispatcher.consume_outbound_confirmed(event)
        assert order.status == FulfillmentStatus.dispatched
        assert order.tracking_number.startswith('CJ')

        # 2) 운송장 등록
        tracking_info = registry.register_from_order(order)
        assert tracking_info is not None
        assert order.status == FulfillmentStatus.tracking_registered

        # 3) 상태 동기화
        synced = registry.sync_status(order.tracking_number)
        assert synced.status == 'in_transit'

        # 4) 봇 알림
        payload = dispatcher.notify_bot(order)
        assert payload['tracking_number'] == order.tracking_number

    def test_end_to_end_without_carrier_selection(self):
        from src.fulfillment_automation.dispatcher import AutoDispatcher
        from src.fulfillment_automation.models import FulfillmentStatus
        from src.fulfillment_automation.tracking_registry import TrackingRegistry

        dispatcher = AutoDispatcher()
        registry = TrackingRegistry()

        event = {
            'outbound_request_id': 'OB-E2E-002',
            'strategy': 'cheapest',
            'recipient_name': '홍길동',
            'recipient_address': '부산시 해운대구',
        }
        order = dispatcher.consume_outbound_confirmed(event)
        assert order.status == FulfillmentStatus.dispatched

        info = registry.register_from_order(order)
        assert info is not None
        assert order.status == FulfillmentStatus.tracking_registered

    def test_multiple_orders_independent(self):
        from src.fulfillment_automation.dispatcher import AutoDispatcher

        dispatcher = AutoDispatcher()
        orders = []
        for i in range(5):
            from src.fulfillment_automation.models import DispatchRequest
            req = DispatchRequest(carrier_id='cj_logistics')
            orders.append(dispatcher.dispatch(req))

        assert len(dispatcher.list_orders()) == 5
        tracking_numbers = {o.tracking_number for o in orders}
        assert len(tracking_numbers) == 5  # all unique


# ─── __init__.py exports ─────────────────────────────────────────────────────

class TestFulfillmentAutomationPackageExports:
    def test_all_exports(self):
        from src.fulfillment_automation import (
            AutoDispatcher,
            CarrierBase,
            CarrierRegistry,
            CJLogisticsCarrier,
            DispatchRequest,
            FulfillmentOrder,
            FulfillmentStatus,
            HanjinCarrier,
            LotteCarrier,
            TrackingInfo,
            TrackingRegistry,
        )
        assert AutoDispatcher is not None
        assert TrackingRegistry is not None
        assert FulfillmentStatus is not None


# ─── API 엔드포인트 테스트 ────────────────────────────────────────────────────

class TestFulfillmentAutomationAPI:
    def _make_app(self):
        from flask import Flask
        from src.api.fulfillment_api import fulfillment_bp
        app = Flask(__name__)
        app.register_blueprint(fulfillment_bp)
        app.config['TESTING'] = True
        return app

    def test_dispatch_post(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                '/api/v1/fulfillment/dispatch',
                json={
                    'outbound_request_id': 'OB-API-001',
                    'package_ids': ['PKG-001'],
                    'recipient_name': '테스트',
                    'recipient_address': '서울',
                    'carrier_id': 'cj_logistics',
                },
            )
            assert resp.status_code == 201
            data = resp.get_json()
            assert 'order_id' in data
            # After dispatch the tracking is also registered, so status is tracking_registered
            assert data['status'] in ('dispatched', 'tracking_registered')
            assert data['carrier_id'] == 'cj_logistics'

    def test_dispatch_post_empty_body(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post('/api/v1/fulfillment/dispatch', json={})
            assert resp.status_code == 201
            data = resp.get_json()
            assert 'order_id' in data

    def test_dispatch_post_strategy(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                '/api/v1/fulfillment/dispatch',
                json={'strategy': 'fastest'},
            )
            assert resp.status_code == 201
            data = resp.get_json()
            assert data['status'] in ('dispatched', 'tracking_registered')

    def test_automation_tracking_register_post(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                '/api/v1/fulfillment/automation/tracking/register',
                json={
                    'order_id': 'fa_api_001',
                    'tracking_number': 'CJ_API_TEST_001',
                    'carrier_id': 'cj_logistics',
                },
            )
            assert resp.status_code == 201
            data = resp.get_json()
            assert data['tracking_number'] == 'CJ_API_TEST_001'
            assert data['carrier_id'] == 'cj_logistics'
            assert data['status'] == 'registered'

    def test_automation_tracking_register_missing_fields(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                '/api/v1/fulfillment/automation/tracking/register',
                json={'order_id': 'fa_001'},
            )
            assert resp.status_code == 400

    def test_get_status_found(self):
        app = self._make_app()
        with app.test_client() as client:
            # First dispatch
            resp = client.post(
                '/api/v1/fulfillment/dispatch',
                json={'carrier_id': 'hanjin'},
            )
            assert resp.status_code == 201
            order_id = resp.get_json()['order_id']

            # Then get status
            status_resp = client.get(f'/api/v1/fulfillment/status/{order_id}')
            assert status_resp.status_code == 200
            status_data = status_resp.get_json()
            assert 'order' in status_data
            assert 'tracking' in status_data
            assert status_data['order']['order_id'] == order_id

    def test_get_status_not_found(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/api/v1/fulfillment/status/nonexistent_order')
            assert resp.status_code == 404

    def test_get_status_with_tracking(self):
        app = self._make_app()
        with app.test_client() as client:
            # Dispatch
            resp = client.post(
                '/api/v1/fulfillment/dispatch',
                json={'carrier_id': 'lotte'},
            )
            order_id = resp.get_json()['order_id']
            tracking_number = resp.get_json()['tracking_number']

            # Register tracking
            client.post(
                '/api/v1/fulfillment/automation/tracking/register',
                json={
                    'order_id': order_id,
                    'tracking_number': tracking_number,
                    'carrier_id': 'lotte',
                },
            )

            # Get status
            status_resp = client.get(f'/api/v1/fulfillment/status/{order_id}')
            data = status_resp.get_json()
            assert len(data['tracking']) >= 1
