"""tests/test_forwarding.py — Phase 102: 배송대행지 연동 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── ForwardingAgent ABC / Implementations ──────────────────────────────────

class TestMoltailAgent:
    def _make_agent(self):
        from src.forwarding.agent import MoltailAgent
        return MoltailAgent()

    def test_agent_id(self):
        agent = self._make_agent()
        assert agent.agent_id == 'moltail'

    def test_name(self):
        agent = self._make_agent()
        assert agent.name == '몰테일'

    def test_reliability_score(self):
        agent = self._make_agent()
        assert agent.reliability_score == 0.95

    def test_get_warehouse_address_us(self):
        agent = self._make_agent()
        addr = agent.get_warehouse_address('US')
        assert 'Irvine' in addr['full']
        assert addr['country'] == 'USA'

    def test_get_warehouse_address_jp(self):
        agent = self._make_agent()
        addr = agent.get_warehouse_address('JP')
        assert '大阪' in addr['full']

    def test_get_warehouse_address_unknown_defaults_us(self):
        agent = self._make_agent()
        addr = agent.get_warehouse_address('CN')
        assert 'Irvine' in addr['full']

    def test_check_incoming(self):
        agent = self._make_agent()
        result = agent.check_incoming('TRK123456')
        assert result['tracking_number'] == 'TRK123456'
        assert result['status'] == 'received'
        assert result['agent_id'] == 'moltail'
        assert result['weight_kg'] > 0
        assert isinstance(result['photo_urls'], list)

    def test_estimate_shipping_cost_us(self):
        agent = self._make_agent()
        result = agent.estimate_shipping_cost(1.0, 'US')
        assert result['cost_usd'] > 0
        assert result['agent_id'] == 'moltail'
        assert result['currency'] == 'USD'

    def test_estimate_shipping_cost_express(self):
        agent = self._make_agent()
        std = agent.estimate_shipping_cost(2.0, 'US', 'standard')
        exp = agent.estimate_shipping_cost(2.0, 'US', 'express')
        assert exp['cost_usd'] > std['cost_usd']

    def test_estimate_shipping_cost_minimum(self):
        agent = self._make_agent()
        result = agent.estimate_shipping_cost(0.001, 'US')
        assert result['cost_usd'] >= 10.0  # minimum charge

    def test_request_consolidation(self):
        agent = self._make_agent()
        result = agent.request_consolidation(['order1', 'order2'])
        assert 'group_id' in result
        assert result['status'] == 'approved'
        assert result['agent_id'] == 'moltail'

    def test_request_shipment(self):
        agent = self._make_agent()
        result = agent.request_shipment('grp001', {'address': 'test'})
        assert 'shipment_id' in result
        assert 'tracking_number' in result
        assert result['tracking_number'].startswith('MT')

    def test_get_tracking(self):
        agent = self._make_agent()
        result = agent.get_tracking('ship001')
        assert result['shipment_id'] == 'ship001'
        assert 'events' in result
        assert len(result['events']) > 0


class TestIhanexAgent:
    def _make_agent(self):
        from src.forwarding.agent import IhanexAgent
        return IhanexAgent()

    def test_agent_id(self):
        agent = self._make_agent()
        assert agent.agent_id == 'ihanex'

    def test_name(self):
        agent = self._make_agent()
        assert agent.name == '이하넥스'

    def test_reliability_score(self):
        agent = self._make_agent()
        assert agent.reliability_score == 0.88

    def test_estimate_cheaper_than_moltail(self):
        from src.forwarding.agent import MoltailAgent
        ihanex = self._make_agent()
        moltail = MoltailAgent()
        ihanex_cost = ihanex.estimate_shipping_cost(2.0, 'US')['cost_usd']
        moltail_cost = moltail.estimate_shipping_cost(2.0, 'US')['cost_usd']
        assert ihanex_cost < moltail_cost

    def test_request_shipment_tracking_prefix(self):
        agent = self._make_agent()
        result = agent.request_shipment('grp002', {})
        assert result['tracking_number'].startswith('IH')

    def test_get_warehouse_address_us(self):
        agent = self._make_agent()
        addr = agent.get_warehouse_address('US')
        assert 'Dallas' in addr['full']

    def test_check_incoming(self):
        agent = self._make_agent()
        result = agent.check_incoming('TRK789')
        assert result['agent_id'] == 'ihanex'
        assert result['status'] == 'received'


class TestForwardingAgentManager:
    def _make_manager(self):
        from src.forwarding.agent import ForwardingAgentManager
        return ForwardingAgentManager()

    def test_default_agents_registered(self):
        manager = self._make_manager()
        agents = manager.list_agents()
        ids = [a['agent_id'] for a in agents]
        assert 'moltail' in ids
        assert 'ihanex' in ids

    def test_get_agent(self):
        manager = self._make_manager()
        agent = manager.get_agent('moltail')
        assert agent.agent_id == 'moltail'

    def test_get_agent_not_found(self):
        manager = self._make_manager()
        with pytest.raises(KeyError):
            manager.get_agent('unknown_agent')

    def test_register_agent(self):
        from src.forwarding.agent import ForwardingAgentManager, MoltailAgent
        manager = self._make_manager()
        mock_agent = MagicMock()
        mock_agent.agent_id = 'custom'
        manager.register_agent(mock_agent)
        assert manager.get_agent('custom') is mock_agent

    def test_list_agents_structure(self):
        manager = self._make_manager()
        agents = manager.list_agents()
        for a in agents:
            assert 'agent_id' in a
            assert 'name' in a
            assert 'reliability' in a

    def test_recommend_reliability(self):
        manager = self._make_manager()
        agent = manager.recommend_agent('reliability')
        assert agent.agent_id == 'moltail'  # higher reliability

    def test_recommend_cost(self):
        manager = self._make_manager()
        agent = manager.recommend_agent('cost')
        assert agent.agent_id == 'ihanex'  # cheaper

    def test_recommend_speed(self):
        manager = self._make_manager()
        agent = manager.recommend_agent('speed')
        assert agent.agent_id == 'moltail'

    def test_recommend_balanced(self):
        manager = self._make_manager()
        agent = manager.recommend_agent('balanced')
        assert agent.agent_id in ('moltail', 'ihanex')

    def test_recommend_default_balanced(self):
        manager = self._make_manager()
        agent = manager.recommend_agent()
        assert agent is not None


# ─── IncomingRecord / IncomingVerifier ──────────────────────────────────────

class TestIncomingRecord:
    def test_defaults(self):
        from src.forwarding.incoming import IncomingRecord, IncomingStatus
        record = IncomingRecord()
        assert record.record_id
        assert record.status == IncomingStatus.WAITING
        assert record.weight_kg == 0.0
        assert record.photo_urls == []
        assert record.issue_type is None

    def test_custom_values(self):
        from src.forwarding.incoming import IncomingRecord, IncomingStatus
        record = IncomingRecord(
            order_id='order_001',
            agent_id='moltail',
            tracking_number='TRK001',
            weight_kg=1.5,
        )
        assert record.order_id == 'order_001'
        assert record.tracking_number == 'TRK001'
        assert record.weight_kg == 1.5


class TestIncomingVerifier:
    def _make_verifier(self):
        from src.forwarding.incoming import IncomingVerifier
        return IncomingVerifier()

    def test_verify_creates_record(self):
        verifier = self._make_verifier()
        record = verifier.verify('order_001', 'TRK001', 'moltail')
        assert record.order_id == 'order_001'
        assert record.tracking_number == 'TRK001'
        assert record.agent_id == 'moltail'

    def test_verify_same_tracking_returns_same_record(self):
        verifier = self._make_verifier()
        r1 = verifier.verify('order_001', 'TRK001', 'moltail')
        r2 = verifier.verify('order_001', 'TRK001', 'moltail')
        assert r1.record_id == r2.record_id

    def test_verify_updates_status_from_agent(self):
        from src.forwarding.incoming import IncomingStatus
        verifier = self._make_verifier()
        record = verifier.verify('order_001', 'TRK001', 'moltail')
        # MoltailAgent mock returns 'received'
        assert record.status == IncomingStatus.RECEIVED

    def test_check_status(self):
        from src.forwarding.incoming import IncomingStatus
        verifier = self._make_verifier()
        record = verifier.verify('order_001', 'TRK001', 'moltail')
        updated = verifier.check_status(record.record_id)
        assert updated.record_id == record.record_id
        assert updated.status == IncomingStatus.RECEIVED

    def test_check_status_not_found(self):
        verifier = self._make_verifier()
        with pytest.raises(KeyError):
            verifier.check_status('nonexistent')

    def test_list_records_all(self):
        verifier = self._make_verifier()
        verifier.verify('order_001', 'TRK001', 'moltail')
        verifier.verify('order_002', 'TRK002', 'moltail')
        records = verifier.list_records()
        assert len(records) == 2

    def test_list_records_by_status(self):
        from src.forwarding.incoming import IncomingStatus
        verifier = self._make_verifier()
        verifier.verify('order_001', 'TRK001', 'moltail')
        records = verifier.list_records(status=IncomingStatus.RECEIVED)
        assert len(records) == 1

    def test_process_inspection_passed(self):
        from src.forwarding.incoming import IncomingStatus
        verifier = self._make_verifier()
        record = verifier.verify('order_001', 'TRK001', 'moltail')
        updated = verifier.process_inspection(record.record_id, passed=True, notes='정상')
        assert updated.status == IncomingStatus.READY_TO_SHIP
        assert updated.inspection_notes == '정상'
        assert updated.issue_type is None

    def test_process_inspection_failed(self):
        from src.forwarding.incoming import IncomingStatus
        verifier = self._make_verifier()
        record = verifier.verify('order_001', 'TRK001', 'moltail')
        updated = verifier.process_inspection(
            record.record_id, passed=False, notes='파손', issue_type='damaged'
        )
        assert updated.status == IncomingStatus.ISSUE_FOUND
        assert updated.issue_type == 'damaged'

    def test_process_inspection_not_found(self):
        verifier = self._make_verifier()
        with pytest.raises(KeyError):
            verifier.process_inspection('nonexistent', passed=True)

    def test_get_stats(self):
        from src.forwarding.incoming import IncomingStatus
        verifier = self._make_verifier()
        verifier.verify('order_001', 'TRK001', 'moltail')
        stats = verifier.get_stats()
        assert 'waiting' in stats
        assert 'received' in stats
        assert stats['received'] == 1


# ─── ConsolidationGroup / ConsolidationManager ──────────────────────────────

class TestConsolidationGroup:
    def test_defaults(self):
        from src.forwarding.consolidation import ConsolidationGroup, ConsolidationStatus
        group = ConsolidationGroup()
        assert group.group_id
        assert group.status == ConsolidationStatus.PENDING
        assert group.order_ids == []
        assert group.savings_usd == 0.0


class TestConsolidationManager:
    def _make_manager(self):
        from src.forwarding.consolidation import ConsolidationManager
        return ConsolidationManager()

    def test_create_group(self):
        from src.forwarding.consolidation import ConsolidationStatus
        manager = self._make_manager()
        group = manager.create_group(['order1', 'order2'], 'moltail', 1.0)
        assert group.group_id
        assert group.order_ids == ['order1', 'order2']
        assert group.agent_id == 'moltail'
        assert group.status == ConsolidationStatus.PENDING

    def test_create_group_empty_raises(self):
        manager = self._make_manager()
        with pytest.raises(ValueError):
            manager.create_group([], 'moltail')

    def test_create_group_auto_weight(self):
        manager = self._make_manager()
        group = manager.create_group(['order1', 'order2'], 'moltail')
        assert group.estimated_weight_kg > 0

    def test_get_group(self):
        manager = self._make_manager()
        group = manager.create_group(['order1'], 'moltail', 0.5)
        retrieved = manager.get_group(group.group_id)
        assert retrieved.group_id == group.group_id

    def test_get_group_not_found(self):
        manager = self._make_manager()
        with pytest.raises(KeyError):
            manager.get_group('nonexistent')

    def test_list_groups(self):
        manager = self._make_manager()
        manager.create_group(['order1'], 'moltail', 0.5)
        manager.create_group(['order2', 'order3'], 'ihanex', 1.0)
        groups = manager.list_groups()
        assert len(groups) == 2

    def test_list_groups_by_status(self):
        from src.forwarding.consolidation import ConsolidationStatus
        manager = self._make_manager()
        manager.create_group(['order1'], 'moltail', 0.5)
        groups = manager.list_groups(status=ConsolidationStatus.PENDING)
        assert len(groups) == 1

    def test_execute_group(self):
        from src.forwarding.consolidation import ConsolidationStatus
        manager = self._make_manager()
        group = manager.create_group(['order1', 'order2'], 'moltail', 1.0)
        executed = manager.execute_group(group.group_id)
        assert executed.status == ConsolidationStatus.COMPLETED
        assert executed.executed_at is not None

    def test_cancel_group(self):
        from src.forwarding.consolidation import ConsolidationStatus
        manager = self._make_manager()
        group = manager.create_group(['order1'], 'moltail', 0.5)
        cancelled = manager.cancel_group(group.group_id)
        assert cancelled.status == ConsolidationStatus.CANCELLED

    def test_cancel_completed_raises(self):
        manager = self._make_manager()
        group = manager.create_group(['order1'], 'moltail', 0.5)
        manager.execute_group(group.group_id)
        with pytest.raises(ValueError):
            manager.cancel_group(group.group_id)

    def test_calculate_savings(self):
        manager = self._make_manager()
        savings = manager.calculate_savings(['order1', 'order2', 'order3'], 0.5)
        assert 'individual_cost' in savings
        assert 'consolidated_cost' in savings
        assert 'savings' in savings
        assert 'savings_pct' in savings
        assert savings['individual_cost'] > savings['consolidated_cost']

    def test_auto_recommend_enough_orders(self):
        manager = self._make_manager()
        group = manager.auto_recommend(['order1', 'order2'], 'moltail')
        assert group is not None

    def test_auto_recommend_single_order_returns_none(self):
        manager = self._make_manager()
        result = manager.auto_recommend(['order1'], 'moltail')
        assert result is None

    def test_split_shipment(self):
        manager = self._make_manager()
        parts = manager.split_shipment('order001', split_count=3)
        assert len(parts) == 3
        for i, part in enumerate(parts):
            assert part['part'] == i + 1
            assert part['total_parts'] == 3
            assert part['order_id'] == 'order001'

    def test_split_shipment_invalid(self):
        manager = self._make_manager()
        with pytest.raises(ValueError):
            manager.split_shipment('order001', split_count=1)


# ─── ShipmentRecord / ShipmentTracker ───────────────────────────────────────

class TestShipmentRecord:
    def test_defaults(self):
        from src.forwarding.tracker import ShipmentRecord, ShipmentStatus
        record = ShipmentRecord()
        assert record.shipment_id
        assert record.status == ShipmentStatus.PENDING
        assert record.origin_country == 'US'
        assert record.destination_country == 'KR'
        assert record.events == []


class TestShipmentTracker:
    def _make_tracker(self):
        from src.forwarding.tracker import ShipmentTracker
        return ShipmentTracker()

    def test_create_shipment(self):
        from src.forwarding.tracker import ShipmentStatus
        tracker = self._make_tracker()
        record = tracker.create_shipment('TRK001', 'moltail', 'US')
        assert record.tracking_number == 'TRK001'
        assert record.agent_id == 'moltail'
        assert record.origin_country == 'US'
        assert record.status == ShipmentStatus.PENDING
        assert record.estimated_delivery is not None

    def test_get_shipment(self):
        tracker = self._make_tracker()
        record = tracker.create_shipment('TRK001', 'moltail', 'US')
        retrieved = tracker.get_shipment(record.shipment_id)
        assert retrieved.shipment_id == record.shipment_id

    def test_get_shipment_not_found(self):
        tracker = self._make_tracker()
        with pytest.raises(KeyError):
            tracker.get_shipment('nonexistent')

    def test_update_tracking(self):
        from src.forwarding.tracker import ShipmentStatus
        tracker = self._make_tracker()
        record = tracker.create_shipment('TRK001', 'moltail', 'US')
        updated = tracker.update_tracking(record.shipment_id)
        assert updated.shipment_id == record.shipment_id
        # Should have events from mock agent
        assert len(updated.events) > 0

    def test_list_shipments_all(self):
        tracker = self._make_tracker()
        tracker.create_shipment('TRK001', 'moltail', 'US')
        tracker.create_shipment('TRK002', 'ihanex', 'JP')
        shipments = tracker.list_shipments()
        assert len(shipments) == 2

    def test_list_shipments_by_status(self):
        from src.forwarding.tracker import ShipmentStatus
        tracker = self._make_tracker()
        tracker.create_shipment('TRK001', 'moltail', 'US')
        shipments = tracker.list_shipments(status=ShipmentStatus.PENDING)
        assert len(shipments) == 1

    def test_calculate_eta_moltail_us(self):
        tracker = self._make_tracker()
        eta = tracker.calculate_eta('moltail', 'US')
        now = datetime.now(timezone.utc)
        delta = eta - now
        assert 6 <= delta.days <= 8

    def test_calculate_eta_ihanex_us(self):
        tracker = self._make_tracker()
        eta = tracker.calculate_eta('ihanex', 'US')
        now = datetime.now(timezone.utc)
        delta = eta - now
        assert 8 <= delta.days <= 10

    def test_get_stats(self):
        tracker = self._make_tracker()
        tracker.create_shipment('TRK001', 'moltail', 'US')
        stats = tracker.get_stats()
        assert 'by_status' in stats
        assert 'total' in stats
        assert stats['total'] == 1


# ─── CostEstimator ──────────────────────────────────────────────────────────

class TestCostEstimator:
    def _make_estimator(self):
        from src.forwarding.cost_estimator import CostEstimator
        return CostEstimator()

    def test_estimate_basic(self):
        estimator = self._make_estimator()
        cb = estimator.estimate(1.0, 'KR', 'moltail')
        assert cb.base_shipping_usd > 0
        assert cb.fuel_surcharge_usd > 0
        assert cb.agent_fee_usd == 3.0
        assert cb.total_usd > 0

    def test_estimate_ihanex_cheaper(self):
        estimator = self._make_estimator()
        moltail_cb = estimator.estimate(2.0, 'KR', 'moltail')
        ihanex_cb = estimator.estimate(2.0, 'KR', 'ihanex')
        assert ihanex_cb.total_usd < moltail_cb.total_usd

    def test_estimate_customs_waived_below_threshold(self):
        estimator = self._make_estimator()
        cb = estimator.estimate(1.0, 'KR', 'moltail', product_value_usd=100.0)
        assert cb.customs_duty_usd == 0.0
        assert cb.vat_usd == 0.0

    def test_estimate_customs_applied_above_threshold(self):
        estimator = self._make_estimator()
        cb = estimator.estimate(1.0, 'KR', 'moltail', product_value_usd=200.0)
        assert cb.customs_duty_usd > 0
        assert cb.vat_usd > 0

    def test_estimate_insurance(self):
        estimator = self._make_estimator()
        cb = estimator.estimate(1.0, 'KR', 'moltail', product_value_usd=500.0)
        assert cb.insurance_usd == pytest.approx(5.0, rel=0.01)

    def test_estimate_express_more_expensive(self):
        estimator = self._make_estimator()
        std = estimator.estimate(2.0, 'KR', 'moltail', service='standard')
        exp = estimator.estimate(2.0, 'KR', 'moltail', service='express')
        assert exp.base_shipping_usd > std.base_shipping_usd

    def test_estimate_minimum_charge(self):
        estimator = self._make_estimator()
        cb = estimator.estimate(0.001, 'KR', 'moltail')
        assert cb.base_shipping_usd >= 10.0

    def test_estimate_electronics_duty_rate(self):
        estimator = self._make_estimator()
        cb = estimator.estimate(1.0, 'KR', 'moltail', product_value_usd=200.0, category='electronics')
        assert cb.customs_duty_usd == pytest.approx(200.0 * 0.08, rel=0.01)

    def test_simulate_consolidation(self):
        estimator = self._make_estimator()
        result = estimator.simulate_consolidation([0.5, 0.5, 0.5], 'KR', 'moltail')
        assert 'individual_total' in result
        assert 'consolidated_cost' in result
        assert 'savings' in result
        assert result['savings'] >= 0

    def test_get_cheapest_agent(self):
        estimator = self._make_estimator()
        result = estimator.get_cheapest_agent(2.0, 'KR')
        assert 'agent_id' in result
        assert 'cost' in result
        assert 'savings_vs_expensive' in result
        assert result['agent_id'] == 'ihanex'  # ihanex is cheaper


# ─── ForwardingDashboard ─────────────────────────────────────────────────────

class TestForwardingDashboard:
    def _make_dashboard(self):
        from src.forwarding.dashboard import ForwardingDashboard
        from src.forwarding.incoming import IncomingVerifier
        from src.forwarding.consolidation import ConsolidationManager
        from src.forwarding.tracker import ShipmentTracker
        from src.forwarding.cost_estimator import CostEstimator
        from src.forwarding.agent import ForwardingAgentManager
        return ForwardingDashboard(
            verifier=IncomingVerifier(),
            manager=ConsolidationManager(),
            tracker=ShipmentTracker(),
            estimator=CostEstimator(),
            agent_manager=ForwardingAgentManager(),
        )

    def test_get_summary_empty(self):
        dashboard = self._make_dashboard()
        summary = dashboard.get_summary()
        assert 'incoming_stats' in summary
        assert 'consolidation_stats' in summary
        assert 'shipment_stats' in summary
        assert 'total_shipments' in summary
        assert summary['total_shipments'] == 0

    def test_get_summary_with_data(self):
        from src.forwarding.incoming import IncomingVerifier
        from src.forwarding.tracker import ShipmentTracker
        from src.forwarding.dashboard import ForwardingDashboard
        verifier = IncomingVerifier()
        verifier.verify('order1', 'TRK001', 'moltail')
        tracker = ShipmentTracker()
        tracker.create_shipment('TRK001', 'moltail', 'US')
        dashboard = ForwardingDashboard(verifier=verifier, tracker=tracker)
        summary = dashboard.get_summary()
        assert summary['total_shipments'] == 1
        assert summary['incoming_stats'].get('received', 0) == 1

    def test_get_agent_stats(self):
        dashboard = self._make_dashboard()
        stats = dashboard.get_agent_stats()
        assert len(stats) == 2
        for s in stats:
            assert 'agent_id' in s
            assert 'name' in s
            assert 'reliability' in s
            assert 'avg_processing_days' in s

    def test_get_cost_stats_empty(self):
        dashboard = self._make_dashboard()
        stats = dashboard.get_cost_stats()
        assert 'total_cost_usd' in stats
        assert stats['total_cost_usd'] == 0.0

    def test_dashboard_no_components(self):
        from src.forwarding.dashboard import ForwardingDashboard
        dashboard = ForwardingDashboard()
        summary = dashboard.get_summary()
        assert summary['total_shipments'] == 0


# ─── API Blueprint ───────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from flask import Flask
    from src.api.forwarding_api import forwarding_bp
    flask_app = Flask(__name__)
    flask_app.register_blueprint(forwarding_bp)
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


class TestForwardingAPI:
    def test_list_shipments(self, client):
        resp = client.get('/api/v1/forwarding/shipments')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_create_shipment(self, client):
        resp = client.post(
            '/api/v1/forwarding/shipments',
            json={'tracking_number': 'TRK_API_001', 'agent_id': 'moltail'},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['tracking_number'] == 'TRK_API_001'
        assert data['agent_id'] == 'moltail'

    def test_create_shipment_missing_tracking(self, client):
        resp = client.post('/api/v1/forwarding/shipments', json={})
        assert resp.status_code == 400

    def test_get_shipment_not_found(self, client):
        resp = client.get('/api/v1/forwarding/shipments/nonexistent')
        assert resp.status_code == 404

    def test_get_shipment(self, client):
        create_resp = client.post(
            '/api/v1/forwarding/shipments',
            json={'tracking_number': 'TRK_API_002', 'agent_id': 'moltail'},
        )
        shipment_id = create_resp.get_json()['shipment_id']
        resp = client.get(f'/api/v1/forwarding/shipments/{shipment_id}')
        assert resp.status_code == 200

    def test_get_shipment_tracking(self, client):
        create_resp = client.post(
            '/api/v1/forwarding/shipments',
            json={'tracking_number': 'TRK_API_003', 'agent_id': 'moltail'},
        )
        shipment_id = create_resp.get_json()['shipment_id']
        resp = client.get(f'/api/v1/forwarding/shipments/{shipment_id}/tracking')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'events' in data

    def test_check_incoming(self, client):
        resp = client.post(
            '/api/v1/forwarding/incoming/check',
            json={'order_id': 'order1', 'tracking_number': 'TRK_INC_001', 'agent_id': 'moltail'},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['tracking_number'] == 'TRK_INC_001'

    def test_check_incoming_missing_tracking(self, client):
        resp = client.post('/api/v1/forwarding/incoming/check', json={})
        assert resp.status_code == 400

    def test_list_incoming(self, client):
        resp = client.get('/api/v1/forwarding/incoming')
        assert resp.status_code == 200

    def test_get_incoming_not_found(self, client):
        resp = client.get('/api/v1/forwarding/incoming/nonexistent')
        assert resp.status_code == 404

    def test_create_consolidation(self, client):
        resp = client.post(
            '/api/v1/forwarding/consolidation',
            json={'order_ids': ['order1', 'order2'], 'agent_id': 'moltail', 'estimated_weight_kg': 1.0},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['order_ids'] == ['order1', 'order2']

    def test_create_consolidation_missing_orders(self, client):
        resp = client.post('/api/v1/forwarding/consolidation', json={})
        assert resp.status_code == 400

    def test_list_consolidation(self, client):
        resp = client.get('/api/v1/forwarding/consolidation')
        assert resp.status_code == 200

    def test_execute_consolidation(self, client):
        create_resp = client.post(
            '/api/v1/forwarding/consolidation',
            json={'order_ids': ['order1', 'order2'], 'agent_id': 'moltail'},
        )
        group_id = create_resp.get_json()['group_id']
        resp = client.post(f'/api/v1/forwarding/consolidation/{group_id}/execute')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'completed'

    def test_execute_consolidation_not_found(self, client):
        resp = client.post('/api/v1/forwarding/consolidation/nonexistent/execute')
        assert resp.status_code == 404

    def test_estimate_cost(self, client):
        resp = client.post(
            '/api/v1/forwarding/estimate',
            json={'weight_kg': 2.0, 'country': 'KR', 'agent_id': 'moltail'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_usd' in data
        assert data['total_usd'] > 0

    def test_estimate_cost_zero_weight(self, client):
        resp = client.post(
            '/api/v1/forwarding/estimate',
            json={'weight_kg': 0, 'country': 'KR', 'agent_id': 'moltail'},
        )
        assert resp.status_code == 400

    def test_list_agents(self, client):
        resp = client.get('/api/v1/forwarding/agents')
        assert resp.status_code == 200
        agents = resp.get_json()
        assert len(agents) >= 2

    def test_recommend_agent(self, client):
        resp = client.get('/api/v1/forwarding/agents/moltail/recommend?priority=reliability')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'agent_id' in data

    def test_get_dashboard(self, client):
        resp = client.get('/api/v1/forwarding/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'summary' in data
        assert 'agent_stats' in data


# ─── Bot Commands ─────────────────────────────────────────────────────────────

class TestBotCommands:
    def test_cmd_forwarding_status(self):
        from src.bot.commands import cmd_forwarding_status
        result = cmd_forwarding_status()
        assert '입고' in result or '배송' in result

    def test_cmd_incoming_check(self):
        from src.bot.commands import cmd_incoming_check
        result = cmd_incoming_check('TRK_BOT_001')
        assert 'TRK_BOT_001' in result or '입고' in result

    def test_cmd_incoming_check_empty(self):
        from src.bot.commands import cmd_incoming_check
        result = cmd_incoming_check('')
        assert '사용법' in result or 'error' in result.lower() or '오류' in result

    def test_cmd_shipping_estimate(self):
        from src.bot.commands import cmd_shipping_estimate
        result = cmd_shipping_estimate('2.0', 'KR')
        assert '$' in result or '배송비' in result

    def test_cmd_shipping_estimate_empty(self):
        from src.bot.commands import cmd_shipping_estimate
        result = cmd_shipping_estimate('', '')
        assert '사용법' in result or 'error' in result.lower()

    def test_cmd_shipping_estimate_invalid_weight(self):
        from src.bot.commands import cmd_shipping_estimate
        result = cmd_shipping_estimate('abc', 'KR')
        assert '숫자' in result or 'error' in result.lower() or '오류' in result

    def test_cmd_consolidation_list_empty(self):
        from src.bot.commands import cmd_consolidation_list
        result = cmd_consolidation_list()
        assert '없습니다' in result or '합배송' in result

    def test_cmd_forwarding_dashboard(self):
        from src.bot.commands import cmd_forwarding_dashboard
        result = cmd_forwarding_dashboard()
        assert '배송' in result or '대시보드' in result


# ─── Formatters ──────────────────────────────────────────────────────────────

class TestFormatters:
    def test_format_forwarding_status(self):
        from src.bot.formatters import format_message
        result = format_message('forwarding_status', {
            'incoming_stats': {'waiting': 3, 'received': 5},
            'shipment_stats': {'in_transit': 2, 'delivered': 10},
        })
        assert '3' in result
        assert '5' in result

    def test_format_incoming_record(self):
        from src.bot.formatters import format_message
        result = format_message('incoming_record', {
            'order_id': 'order_001',
            'tracking_number': 'TRK001',
            'status': 'received',
            'weight_kg': 1.5,
        })
        assert 'order_001' in result
        assert 'TRK001' in result

    def test_format_consolidation_group(self):
        from src.bot.formatters import format_message
        result = format_message('consolidation_group', {
            'group_id': 'grp001',
            'order_ids': ['o1', 'o2'],
            'status': 'pending',
            'estimated_weight_kg': 2.0,
            'savings_usd': 5.50,
        })
        assert 'grp001' in result
        assert '2' in result  # order count
        assert '5.50' in result

    def test_format_shipment_record(self):
        from src.bot.formatters import format_message
        result = format_message('shipment_record', {
            'shipment_id': 'ship001',
            'tracking_number': 'TRK001',
            'status': 'pending',
            'origin_country': 'US',
            'destination_country': 'KR',
        })
        assert 'ship001' in result
        assert 'US' in result

    def test_format_cost_estimate(self):
        from src.bot.formatters import format_message
        result = format_message('cost_estimate', {
            'base_shipping_usd': 12.0,
            'fuel_surcharge_usd': 1.2,
            'insurance_usd': 0.0,
            'agent_fee_usd': 3.0,
            'customs_duty_usd': 0.0,
            'vat_usd': 0.0,
            'total_usd': 16.2,
        })
        assert '12.00' in result
        assert '16.20' in result

    def test_format_forwarding_dashboard(self):
        from src.bot.formatters import format_message
        result = format_message('forwarding_dashboard', {
            'total_shipments': 10,
            'incoming_stats': {'waiting': 1},
            'shipment_stats': {'in_transit': 3},
            'consolidation_stats': {'total_groups': 2, 'total_savings_usd': 25.0},
        })
        assert '10' in result
        assert '25.00' in result
