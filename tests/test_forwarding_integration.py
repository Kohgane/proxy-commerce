"""tests/test_forwarding_integration.py — Phase 83: 배송대행 통합 자동화 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── models ──────────────────────────────────────────────────────────────────

class TestForwardingPackage:
    def _make(self, **kw):
        from src.forwarding_integration.models import ForwardingPackage
        return ForwardingPackage(**kw)

    def test_defaults(self):
        pkg = self._make()
        assert pkg.package_id
        assert pkg.status == 'pending'
        assert pkg.quantity == 1
        assert pkg.weight_kg == 0.0
        assert pkg.origin_country == 'US'
        assert pkg.destination_country == 'KR'

    def test_custom_values(self):
        pkg = self._make(
            purchase_order_id='PO-001',
            product_name='Test Product',
            quantity=3,
            weight_kg=1.5,
            provider='malltail',
        )
        assert pkg.purchase_order_id == 'PO-001'
        assert pkg.product_name == 'Test Product'
        assert pkg.quantity == 3
        assert pkg.weight_kg == 1.5
        assert pkg.provider == 'malltail'

    def test_to_dict_keys(self):
        pkg = self._make(product_name='Book', provider='malltail')
        d = pkg.to_dict()
        for key in (
            'package_id', 'purchase_order_id', 'customer_order_id',
            'product_name', 'quantity', 'weight_kg', 'provider',
            'origin_country', 'destination_country', 'status',
            'tracking_number', 'created_at', 'metadata',
        ):
            assert key in d

    def test_to_dict_values(self):
        pkg = self._make(product_name='Shirt', quantity=2, provider='ihanex')
        d = pkg.to_dict()
        assert d['product_name'] == 'Shirt'
        assert d['quantity'] == 2
        assert d['provider'] == 'ihanex'

    def test_unique_ids(self):
        from src.forwarding_integration.models import ForwardingPackage
        ids = {ForwardingPackage().package_id for _ in range(10)}
        assert len(ids) == 10

    def test_created_at_is_string(self):
        pkg = self._make()
        assert isinstance(pkg.created_at, str)


class TestInboundRegistration:
    def _make(self, **kw):
        from src.forwarding_integration.models import InboundRegistration
        return InboundRegistration(**kw)

    def test_defaults(self):
        reg = self._make()
        assert reg.registration_id
        assert reg.status == 'registered'
        assert reg.quantity == 1

    def test_to_dict_keys(self):
        reg = self._make()
        d = reg.to_dict()
        for key in (
            'registration_id', 'package_id', 'provider', 'purchase_order_id',
            'product_name', 'quantity', 'weight_kg', 'warehouse_address',
            'status', 'registered_at', 'metadata',
        ):
            assert key in d

    def test_custom_values(self):
        reg = self._make(
            package_id='PKG-001',
            provider='malltail',
            purchase_order_id='PO-001',
            product_name='Electronics',
            quantity=2,
            weight_kg=0.5,
        )
        assert reg.package_id == 'PKG-001'
        assert reg.provider == 'malltail'
        assert reg.quantity == 2


class TestConsolidationRequest:
    def _make(self, **kw):
        from src.forwarding_integration.models import ConsolidationRequest
        return ConsolidationRequest(**kw)

    def test_defaults(self):
        req = self._make()
        assert req.request_id
        assert req.status == 'pending'
        assert req.package_ids == []
        assert req.destination_country == 'KR'

    def test_to_dict_keys(self):
        req = self._make(package_ids=['p1', 'p2'], provider='malltail')
        d = req.to_dict()
        for key in (
            'request_id', 'package_ids', 'provider',
            'destination_country', 'status', 'created_at', 'metadata',
        ):
            assert key in d

    def test_package_ids_stored(self):
        req = self._make(package_ids=['a', 'b', 'c'])
        assert req.package_ids == ['a', 'b', 'c']
        assert req.to_dict()['package_ids'] == ['a', 'b', 'c']


class TestOutboundRequest:
    def _make(self, **kw):
        from src.forwarding_integration.models import OutboundRequest
        return OutboundRequest(**kw)

    def test_defaults(self):
        req = self._make()
        assert req.request_id
        assert req.status == 'requested'
        assert req.tracking_number == ''

    def test_to_dict_keys(self):
        req = self._make()
        d = req.to_dict()
        for key in (
            'request_id', 'package_ids', 'provider', 'destination_country',
            'recipient_name', 'recipient_address', 'tracking_number',
            'status', 'created_at', 'metadata',
        ):
            assert key in d

    def test_custom_values(self):
        req = self._make(
            package_ids=['p1'],
            provider='ihanex',
            recipient_name='홍길동',
            recipient_address='서울시 강남구 테헤란로 1',
            tracking_number='IH123456',
            status='processing',
        )
        assert req.recipient_name == '홍길동'
        assert req.tracking_number == 'IH123456'
        assert req.status == 'processing'


class TestForwardingStatus:
    def _make(self, **kw):
        from src.forwarding_integration.models import ForwardingStatus
        return ForwardingStatus(**kw)

    def test_defaults(self):
        s = self._make()
        assert s.current_status == 'unknown'
        assert s.events == []
        assert s.tracking_number == ''

    def test_to_dict_keys(self):
        s = self._make()
        d = s.to_dict()
        for key in (
            'package_id', 'current_status', 'provider',
            'tracking_number', 'last_updated', 'events', 'metadata',
        ):
            assert key in d

    def test_custom_values(self):
        s = self._make(
            package_id='PKG-1',
            current_status='in_transit',
            provider='malltail',
            tracking_number='MT123',
            events=[{'event': 'departed'}],
        )
        assert s.package_id == 'PKG-1'
        assert s.current_status == 'in_transit'
        assert len(s.events) == 1


# ─── ForwardingProvider ABC ───────────────────────────────────────────────────

class TestForwardingProviderABC:
    def test_cannot_instantiate(self):
        from src.forwarding_integration.providers.base import ForwardingProvider
        with pytest.raises(TypeError):
            ForwardingProvider()  # type: ignore[abstract]


# ─── MalltailProvider ────────────────────────────────────────────────────────

class TestMalltailProvider:
    def _make(self):
        from src.forwarding_integration.providers.malltail import MalltailProvider
        return MalltailProvider()

    def _make_package(self, **kw):
        from src.forwarding_integration.models import ForwardingPackage
        return ForwardingPackage(provider='malltail', product_name='Book', **kw)

    def test_provider_id(self):
        p = self._make()
        assert p.provider_id == 'malltail'

    def test_name(self):
        p = self._make()
        assert 'malltail' in p.name.lower() or 'Malltail' in p.name

    def test_register_inbound_returns_registration(self):
        p = self._make()
        pkg = self._make_package(purchase_order_id='PO-100', quantity=2)
        reg = p.register_inbound(pkg)
        assert reg.registration_id
        assert reg.package_id == pkg.package_id
        assert reg.provider == 'malltail'
        assert reg.status == 'registered'
        assert reg.purchase_order_id == 'PO-100'
        assert reg.quantity == 2

    def test_register_inbound_warehouse_address(self):
        p = self._make()
        reg = p.register_inbound(self._make_package())
        assert reg.warehouse_address
        assert reg.warehouse_address.get('country') == 'US'

    def test_confirm_arrival_updates_status(self):
        p = self._make()
        reg = p.register_inbound(self._make_package())
        updated = p.confirm_arrival(reg.registration_id)
        assert updated.status == 'arrived'
        assert updated.registration_id == reg.registration_id

    def test_confirm_arrival_not_found(self):
        p = self._make()
        with pytest.raises(KeyError):
            p.confirm_arrival('nonexistent')

    def test_request_consolidation(self):
        p = self._make()
        req = p.request_consolidation(['pkg1', 'pkg2'], 'KR')
        assert req.request_id
        assert req.provider == 'malltail'
        assert req.package_ids == ['pkg1', 'pkg2']
        assert req.destination_country == 'KR'
        assert req.status == 'pending'

    def test_request_consolidation_uppercases_country(self):
        p = self._make()
        req = p.request_consolidation(['p1'], 'kr')
        assert req.destination_country == 'KR'

    def test_request_outbound_returns_request(self):
        p = self._make()
        req = p.request_outbound(
            ['pkg1'], 'KR', '홍길동', '서울 강남구'
        )
        assert req.request_id
        assert req.provider == 'malltail'
        assert req.tracking_number.startswith('MT')
        assert req.status == 'processing'
        assert req.recipient_name == '홍길동'
        assert req.recipient_address == '서울 강남구'

    def test_request_outbound_unique_tracking(self):
        p = self._make()
        r1 = p.request_outbound(['p1'], 'KR', 'A', 'addr1')
        r2 = p.request_outbound(['p2'], 'KR', 'B', 'addr2')
        assert r1.tracking_number != r2.tracking_number

    def test_track_package_returns_status(self):
        p = self._make()
        status = p.track_package('PKG-999')
        assert status.package_id == 'PKG-999'
        assert status.provider == 'malltail'
        assert status.current_status
        assert status.tracking_number.startswith('MT')

    def test_track_package_consistent(self):
        p = self._make()
        s1 = p.track_package('PKG-X')
        s2 = p.track_package('PKG-X')
        assert s1.tracking_number == s2.tracking_number


# ─── IHanexProvider ──────────────────────────────────────────────────────────

class TestIHanexProvider:
    def _make(self):
        from src.forwarding_integration.providers.ihanex import IHanexProvider
        return IHanexProvider()

    def _make_package(self):
        from src.forwarding_integration.models import ForwardingPackage
        return ForwardingPackage(provider='ihanex', product_name='Shoes')

    def test_provider_id(self):
        p = self._make()
        assert p.provider_id == 'ihanex'

    def test_name(self):
        p = self._make()
        assert 'ihanex' in p.name.lower() or 'iHanex' in p.name

    def test_register_inbound(self):
        p = self._make()
        reg = p.register_inbound(self._make_package())
        assert reg.provider == 'ihanex'
        assert reg.status == 'registered'

    def test_confirm_arrival(self):
        p = self._make()
        reg = p.register_inbound(self._make_package())
        updated = p.confirm_arrival(reg.registration_id)
        assert updated.status == 'arrived'

    def test_confirm_arrival_not_found(self):
        p = self._make()
        with pytest.raises(KeyError):
            p.confirm_arrival('nope')

    def test_request_consolidation(self):
        p = self._make()
        req = p.request_consolidation(['a', 'b'], 'US')
        assert req.provider == 'ihanex'
        assert req.destination_country == 'US'

    def test_request_outbound_tracking_prefix(self):
        p = self._make()
        req = p.request_outbound(['p1'], 'KR', 'Kim', 'Seoul')
        assert req.tracking_number.startswith('IH')

    def test_track_package(self):
        p = self._make()
        s = p.track_package('PKG-IH-1')
        assert s.provider == 'ihanex'
        assert s.tracking_number.startswith('IH')


# ─── OhMyZipProvider ─────────────────────────────────────────────────────────

class TestOhMyZipProvider:
    def _make(self):
        from src.forwarding_integration.providers.ohmyzip import OhMyZipProvider
        return OhMyZipProvider()

    def _make_package(self):
        from src.forwarding_integration.models import ForwardingPackage
        return ForwardingPackage(provider='ohmyzip', product_name='Watch')

    def test_provider_id(self):
        p = self._make()
        assert p.provider_id == 'ohmyzip'

    def test_name(self):
        p = self._make()
        assert 'ohmyzip' in p.name.lower() or 'OhMyZip' in p.name

    def test_register_inbound(self):
        p = self._make()
        reg = p.register_inbound(self._make_package())
        assert reg.provider == 'ohmyzip'
        assert reg.status == 'registered'

    def test_confirm_arrival(self):
        p = self._make()
        reg = p.register_inbound(self._make_package())
        updated = p.confirm_arrival(reg.registration_id)
        assert updated.status == 'arrived'

    def test_confirm_arrival_not_found(self):
        p = self._make()
        with pytest.raises(KeyError):
            p.confirm_arrival('missing')

    def test_request_consolidation(self):
        p = self._make()
        req = p.request_consolidation(['x', 'y', 'z'], 'KR')
        assert req.provider == 'ohmyzip'
        assert len(req.package_ids) == 3

    def test_request_outbound_tracking_prefix(self):
        p = self._make()
        req = p.request_outbound(['q1'], 'KR', 'Park', 'Busan')
        assert req.tracking_number.startswith('OMZ')

    def test_track_package(self):
        p = self._make()
        s = p.track_package('PKG-OMZ-1')
        assert s.provider == 'ohmyzip'
        assert s.tracking_number.startswith('OMZ')


# ─── ProviderRegistry ────────────────────────────────────────────────────────

class TestProviderRegistry:
    def _make(self):
        from src.forwarding_integration.provider_registry import ProviderRegistry
        return ProviderRegistry()

    def test_default_providers_registered(self):
        registry = self._make()
        ids = registry.provider_ids()
        assert 'malltail' in ids
        assert 'ihanex' in ids
        assert 'ohmyzip' in ids

    def test_get_provider(self):
        registry = self._make()
        p = registry.get('malltail')
        assert p.provider_id == 'malltail'

    def test_get_ihanex(self):
        registry = self._make()
        p = registry.get('ihanex')
        assert p.provider_id == 'ihanex'

    def test_get_ohmyzip(self):
        registry = self._make()
        p = registry.get('ohmyzip')
        assert p.provider_id == 'ohmyzip'

    def test_get_not_found(self):
        registry = self._make()
        with pytest.raises(KeyError):
            registry.get('nonexistent')

    def test_list_providers(self):
        registry = self._make()
        providers = registry.list_providers()
        assert len(providers) >= 3
        for p in providers:
            assert 'provider_id' in p
            assert 'name' in p

    def test_register_custom_provider(self):
        from unittest.mock import MagicMock
        registry = self._make()
        mock = MagicMock()
        mock.provider_id = 'custom_provider'
        mock.name = 'Custom'
        registry.register(mock)
        assert registry.get('custom_provider') is mock

    def test_provider_ids_list(self):
        registry = self._make()
        ids = registry.provider_ids()
        assert isinstance(ids, list)
        assert len(ids) >= 3

    def test_get_default_registry_singleton(self):
        from src.forwarding_integration.provider_registry import get_default_registry
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2


# ─── ForwardingEngine ────────────────────────────────────────────────────────

class TestForwardingEngine:
    def _make(self):
        from src.forwarding_integration.forwarding_engine import ForwardingEngine
        from src.forwarding_integration.provider_registry import ProviderRegistry
        return ForwardingEngine(registry=ProviderRegistry())

    def test_create_package(self):
        engine = self._make()
        pkg = engine.create_package(
            purchase_order_id='PO-1',
            product_name='Jacket',
            provider='malltail',
            quantity=1,
            weight_kg=0.8,
        )
        assert pkg.package_id
        assert pkg.purchase_order_id == 'PO-1'
        assert pkg.product_name == 'Jacket'
        assert pkg.provider == 'malltail'
        assert pkg.status == 'pending'

    def test_create_package_stored(self):
        engine = self._make()
        pkg = engine.create_package('PO-2', 'Phone', 'ihanex')
        retrieved = engine.get_package(pkg.package_id)
        assert retrieved.package_id == pkg.package_id

    def test_get_package_not_found(self):
        engine = self._make()
        with pytest.raises(KeyError):
            engine.get_package('nonexistent')

    def test_list_packages_empty(self):
        engine = self._make()
        assert engine.list_packages() == []

    def test_list_packages_all(self):
        engine = self._make()
        engine.create_package('PO-1', 'A', 'malltail')
        engine.create_package('PO-2', 'B', 'ihanex')
        assert len(engine.list_packages()) == 2

    def test_list_packages_by_status(self):
        engine = self._make()
        engine.create_package('PO-1', 'A', 'malltail')
        pkgs = engine.list_packages(status='pending')
        assert len(pkgs) == 1

    def test_list_packages_status_no_match(self):
        engine = self._make()
        engine.create_package('PO-1', 'A', 'malltail')
        pkgs = engine.list_packages(status='arrived')
        assert len(pkgs) == 0

    def test_register_inbound_from_purchase(self):
        engine = self._make()
        reg = engine.register_inbound_from_purchase(
            purchase_order_id='PO-10',
            product_name='Bag',
            provider='malltail',
            quantity=1,
            weight_kg=0.5,
        )
        assert reg.registration_id
        assert reg.purchase_order_id == 'PO-10'
        assert reg.status == 'registered'

    def test_register_inbound_creates_package(self):
        engine = self._make()
        reg = engine.register_inbound_from_purchase(
            purchase_order_id='PO-11',
            product_name='Toy',
            provider='malltail',
        )
        # A package should have been created and its metadata updated
        packages = engine.list_packages()
        assert len(packages) == 1
        assert packages[0].metadata.get('registration_id') == reg.registration_id

    def test_register_inbound_package_status(self):
        engine = self._make()
        engine.register_inbound_from_purchase('PO-12', 'Hat', 'malltail')
        pkgs = engine.list_packages(status='inbound_registered')
        assert len(pkgs) == 1

    def test_register_inbound_invalid_provider(self):
        engine = self._make()
        with pytest.raises(KeyError):
            engine.register_inbound_from_purchase('PO-X', 'X', 'unknown_provider')

    def test_confirm_arrival(self):
        engine = self._make()
        reg = engine.register_inbound_from_purchase('PO-20', 'Sneakers', 'malltail')
        pkg_id = engine.list_packages()[0].package_id
        updated = engine.confirm_arrival(pkg_id, reg.registration_id)
        assert updated.status == 'arrived'

    def test_confirm_arrival_updates_package_status(self):
        engine = self._make()
        reg = engine.register_inbound_from_purchase('PO-21', 'Hat', 'ihanex')
        pkg_id = engine.list_packages()[0].package_id
        engine.confirm_arrival(pkg_id, reg.registration_id)
        pkg = engine.get_package(pkg_id)
        assert pkg.status == 'arrived'

    def test_confirm_arrival_package_not_found(self):
        engine = self._make()
        with pytest.raises(KeyError):
            engine.confirm_arrival('bad_pkg', 'bad_reg')

    def test_request_consolidation(self):
        engine = self._make()
        p1 = engine.create_package('PO-30', 'A', 'malltail')
        p2 = engine.create_package('PO-31', 'B', 'malltail')
        req = engine.request_consolidation(
            [p1.package_id, p2.package_id], 'malltail', 'KR'
        )
        assert req.request_id
        assert req.provider == 'malltail'
        assert req.destination_country == 'KR'
        assert p1.package_id in req.package_ids
        assert p2.package_id in req.package_ids

    def test_request_consolidation_updates_package_status(self):
        engine = self._make()
        pkg = engine.create_package('PO-32', 'C', 'malltail')
        engine.request_consolidation([pkg.package_id], 'malltail')
        assert engine.get_package(pkg.package_id).status == 'consolidation_requested'

    def test_request_consolidation_empty_raises(self):
        engine = self._make()
        with pytest.raises(ValueError):
            engine.request_consolidation([], 'malltail')

    def test_request_consolidation_invalid_provider(self):
        engine = self._make()
        with pytest.raises(KeyError):
            engine.request_consolidation(['p1'], 'no_such_provider')

    def test_request_outbound(self):
        engine = self._make()
        pkg = engine.create_package('PO-40', 'Laptop', 'malltail', weight_kg=2.0)
        req = engine.request_outbound(
            [pkg.package_id], 'malltail', 'KR', '홍길동', '서울시 마포구 123'
        )
        assert req.request_id
        assert req.tracking_number.startswith('MT')
        assert req.status == 'processing'
        assert req.recipient_name == '홍길동'

    def test_request_outbound_updates_package(self):
        engine = self._make()
        pkg = engine.create_package('PO-41', 'Phone', 'ihanex')
        req = engine.request_outbound(
            [pkg.package_id], 'ihanex', 'KR', 'Kim', 'Busan'
        )
        updated = engine.get_package(pkg.package_id)
        assert updated.status == 'outbound_requested'
        assert updated.tracking_number == req.tracking_number

    def test_request_outbound_empty_raises(self):
        engine = self._make()
        with pytest.raises(ValueError):
            engine.request_outbound([], 'malltail', 'KR', 'A', 'B')

    def test_request_outbound_invalid_provider(self):
        engine = self._make()
        with pytest.raises(KeyError):
            engine.request_outbound(['p1'], 'ghost', 'KR', 'A', 'B')

    def test_sync_status(self):
        engine = self._make()
        pkg = engine.create_package('PO-50', 'Watch', 'malltail')
        status = engine.sync_status(pkg.package_id)
        assert status.package_id == pkg.package_id
        assert status.provider == 'malltail'
        assert status.current_status

    def test_sync_status_updates_package(self):
        engine = self._make()
        pkg = engine.create_package('PO-51', 'Ring', 'malltail')
        engine.sync_status(pkg.package_id)
        updated = engine.get_package(pkg.package_id)
        assert updated.status == 'in_transit'

    def test_sync_status_not_found(self):
        engine = self._make()
        with pytest.raises(KeyError):
            engine.sync_status('nonexistent')

    def test_sync_all_statuses_empty(self):
        engine = self._make()
        results = engine.sync_all_statuses()
        assert results == []

    def test_sync_all_statuses(self):
        engine = self._make()
        engine.create_package('PO-60', 'A', 'malltail')
        engine.create_package('PO-61', 'B', 'ihanex')
        results = engine.sync_all_statuses()
        assert len(results) == 2

    def test_engine_with_ohmyzip(self):
        engine = self._make()
        reg = engine.register_inbound_from_purchase('PO-70', 'Coat', 'ohmyzip')
        assert reg.provider == 'ohmyzip'
        pkgs = engine.list_packages(status='inbound_registered')
        assert len(pkgs) == 1

    def test_full_lifecycle(self):
        """입고 등록 → 도착 확인 → 출고 요청 → 상태 동기화 전체 흐름."""
        engine = self._make()
        # 1) 입고 등록
        reg = engine.register_inbound_from_purchase(
            'PO-FULL', 'Camera', 'malltail', quantity=1, weight_kg=0.5
        )
        assert reg.status == 'registered'
        pkg_id = engine.list_packages()[0].package_id

        # 2) 도착 확인
        arrival = engine.confirm_arrival(pkg_id, reg.registration_id)
        assert arrival.status == 'arrived'

        # 3) 출고 요청
        outbound = engine.request_outbound(
            [pkg_id], 'malltail', 'KR', '김철수', '서울시 송파구 456'
        )
        assert outbound.tracking_number

        # 4) 상태 동기화
        status = engine.sync_status(pkg_id)
        assert status.package_id == pkg_id


# ─── API Blueprint (Phase 83 new endpoints) ──────────────────────────────────

@pytest.fixture
def integration_client():
    from flask import Flask
    from src.api.forwarding_api import forwarding_bp
    import src.api.forwarding_api as api_module
    # reset engine so each test gets a fresh instance
    api_module._fwd_engine = None
    flask_app = Flask(__name__)
    flask_app.register_blueprint(forwarding_bp)
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c
    api_module._fwd_engine = None


class TestForwardingIntegrationAPI:

    # POST /inbound/register
    def test_inbound_register_success(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={
                'purchase_order_id': 'PO-API-001',
                'product_name': 'API Product',
                'provider': 'malltail',
                'quantity': 2,
                'weight_kg': 1.0,
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['purchase_order_id'] == 'PO-API-001'
        assert data['provider'] == 'malltail'
        assert data['status'] == 'registered'
        assert 'registration_id' in data

    def test_inbound_register_missing_purchase_order_id(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={'product_name': 'X', 'provider': 'malltail'},
        )
        assert resp.status_code == 400

    def test_inbound_register_missing_product_name(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={'purchase_order_id': 'PO-X', 'provider': 'malltail'},
        )
        assert resp.status_code == 400

    def test_inbound_register_empty_body(self, integration_client):
        resp = integration_client.post('/api/v1/forwarding/inbound/register', json={})
        assert resp.status_code == 400

    def test_inbound_register_ihanex(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={
                'purchase_order_id': 'PO-IH-001',
                'product_name': 'Shoe',
                'provider': 'ihanex',
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()['provider'] == 'ihanex'

    def test_inbound_register_ohmyzip(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={
                'purchase_order_id': 'PO-OMZ-001',
                'product_name': 'Bag',
                'provider': 'ohmyzip',
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()['provider'] == 'ohmyzip'

    def test_inbound_register_invalid_provider(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={
                'purchase_order_id': 'PO-X',
                'product_name': 'Item',
                'provider': 'unknown_provider',
            },
        )
        assert resp.status_code == 404

    # POST /arrival/confirm
    def test_arrival_confirm_success(self, integration_client):
        # first register
        reg_resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={
                'purchase_order_id': 'PO-ARR-001',
                'product_name': 'Camera',
                'provider': 'malltail',
            },
        )
        reg_data = reg_resp.get_json()
        reg_id = reg_data['registration_id']

        # find package_id via status - we need to get the engine's package
        import src.api.forwarding_api as api_module
        engine = api_module._fwd_engine
        pkgs = engine.list_packages()
        pkg_id = pkgs[0].package_id

        resp = integration_client.post(
            '/api/v1/forwarding/arrival/confirm',
            json={'package_id': pkg_id, 'registration_id': reg_id},
        )
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'arrived'

    def test_arrival_confirm_missing_package_id(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/arrival/confirm',
            json={'registration_id': 'R1'},
        )
        assert resp.status_code == 400

    def test_arrival_confirm_missing_registration_id(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/arrival/confirm',
            json={'package_id': 'P1'},
        )
        assert resp.status_code == 400

    def test_arrival_confirm_not_found(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/arrival/confirm',
            json={'package_id': 'nonexistent', 'registration_id': 'nonexistent'},
        )
        assert resp.status_code == 404

    # POST /consolidate
    def test_consolidate_success(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/consolidate',
            json={
                'package_ids': ['p1', 'p2', 'p3'],
                'provider': 'malltail',
                'destination_country': 'KR',
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['provider'] == 'malltail'
        assert data['destination_country'] == 'KR'
        assert 'p1' in data['package_ids']
        assert 'request_id' in data

    def test_consolidate_missing_package_ids(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/consolidate',
            json={'provider': 'malltail'},
        )
        assert resp.status_code == 400

    def test_consolidate_empty_package_ids(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/consolidate',
            json={'package_ids': [], 'provider': 'malltail'},
        )
        assert resp.status_code == 400

    def test_consolidate_ihanex(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/consolidate',
            json={'package_ids': ['x', 'y'], 'provider': 'ihanex'},
        )
        assert resp.status_code == 201
        assert resp.get_json()['provider'] == 'ihanex'

    def test_consolidate_invalid_provider(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/consolidate',
            json={'package_ids': ['x'], 'provider': 'ghost'},
        )
        assert resp.status_code == 404

    # POST /outbound/request
    def test_outbound_request_success(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={
                'package_ids': ['p10', 'p11'],
                'provider': 'malltail',
                'destination_country': 'KR',
                'recipient_name': '박지성',
                'recipient_address': '서울시 종로구 1',
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['provider'] == 'malltail'
        assert data['recipient_name'] == '박지성'
        assert data['tracking_number'].startswith('MT')
        assert data['status'] == 'processing'

    def test_outbound_request_missing_package_ids(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={'provider': 'malltail', 'recipient_name': 'A', 'recipient_address': 'B'},
        )
        assert resp.status_code == 400

    def test_outbound_request_missing_recipient(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={'package_ids': ['p1'], 'provider': 'malltail', 'recipient_address': 'B'},
        )
        assert resp.status_code == 400

    def test_outbound_request_missing_address(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={'package_ids': ['p1'], 'provider': 'malltail', 'recipient_name': 'A'},
        )
        assert resp.status_code == 400

    def test_outbound_request_empty_package_ids(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={
                'package_ids': [],
                'provider': 'malltail',
                'recipient_name': 'A',
                'recipient_address': 'B',
            },
        )
        assert resp.status_code == 400

    def test_outbound_request_ihanex_tracking(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={
                'package_ids': ['q1'],
                'provider': 'ihanex',
                'recipient_name': 'Lee',
                'recipient_address': 'Incheon',
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()['tracking_number'].startswith('IH')

    def test_outbound_request_ohmyzip_tracking(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={
                'package_ids': ['r1'],
                'provider': 'ohmyzip',
                'recipient_name': 'Choi',
                'recipient_address': 'Daejeon',
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()['tracking_number'].startswith('OMZ')

    def test_outbound_request_invalid_provider(self, integration_client):
        resp = integration_client.post(
            '/api/v1/forwarding/outbound/request',
            json={
                'package_ids': ['p1'],
                'provider': 'nope',
                'recipient_name': 'A',
                'recipient_address': 'B',
            },
        )
        assert resp.status_code == 404

    # GET /status/<package_id>
    def test_get_status_success(self, integration_client):
        # register inbound to create a package in the engine
        reg_resp = integration_client.post(
            '/api/v1/forwarding/inbound/register',
            json={
                'purchase_order_id': 'PO-STA-001',
                'product_name': 'Gadget',
                'provider': 'malltail',
            },
        )
        import src.api.forwarding_api as api_module
        engine = api_module._fwd_engine
        pkg_id = engine.list_packages()[0].package_id

        resp = integration_client.get(f'/api/v1/forwarding/status/{pkg_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['package_id'] == pkg_id
        assert 'current_status' in data
        assert data['provider'] == 'malltail'

    def test_get_status_not_found(self, integration_client):
        resp = integration_client.get('/api/v1/forwarding/status/nonexistent')
        assert resp.status_code == 404
