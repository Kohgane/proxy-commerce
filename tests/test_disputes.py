"""tests/test_disputes.py — Phase 91: 분쟁 관리 시스템 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from src.disputes.dispute_manager import DisputeManager, DisputeStatus, DisputeType, Dispute
from src.disputes.evidence import EvidenceCollector, EvidenceType, MAX_EVIDENCE_PER_DISPUTE
from src.disputes.mediation import MediationService, MediationResult
from src.disputes.refund_decision import RefundDecision, RefundType, SellerPenalty
from src.disputes.analytics import DisputeAnalytics


# ---------------------------------------------------------------------------
# DisputeManager CRUD
# ---------------------------------------------------------------------------

class TestDisputeManagerCreate:
    def test_create_returns_dispute(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '상품 미수령', 'item_not_received')
        assert d.dispute_id
        assert d.order_id == 'ORD-001'
        assert d.customer_id == 'CUST-001'
        assert d.status == DisputeStatus.OPENED
        assert d.dispute_type == DisputeType.ITEM_NOT_RECEIVED

    def test_create_invalid_type(self):
        mgr = DisputeManager()
        with pytest.raises(ValueError):
            mgr.create('ORD-001', 'CUST-001', '이유', 'invalid_type')

    def test_create_with_amount(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue', amount=30000)
        assert d.amount == 30000

    def test_get_existing(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'wrong_item')
        found = mgr.get(d.dispute_id)
        assert found is not None
        assert found.dispute_id == d.dispute_id

    def test_get_nonexistent(self):
        mgr = DisputeManager()
        assert mgr.get('nonexistent') is None

    def test_list_all(self):
        mgr = DisputeManager()
        mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        assert len(mgr.list()) == 2

    def test_list_by_status(self):
        mgr = DisputeManager()
        mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        opened = mgr.list(status='opened')
        assert len(opened) == 2

    def test_list_by_type(self):
        mgr = DisputeManager()
        mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        filtered = mgr.list(dispute_type='quality_issue')
        assert len(filtered) == 1

    def test_list_by_customer(self):
        mgr = DisputeManager()
        mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        filtered = mgr.list(customer_id='CUST-001')
        assert len(filtered) == 1

    def test_to_dict_keys(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        dd = d.to_dict()
        for key in ('dispute_id', 'order_id', 'customer_id', 'reason', 'dispute_type',
                    'status', 'evidence_ids', 'created_at', 'updated_at', 'resolved_at', 'amount'):
            assert key in dd


class TestDisputeManagerStatusTransition:
    def test_valid_transition_opened_to_under_review(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        d2 = mgr.transition(d.dispute_id, 'under_review')
        assert d2.status == DisputeStatus.UNDER_REVIEW

    def test_valid_transition_to_mediation(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.transition(d.dispute_id, 'under_review')
        d2 = mgr.transition(d.dispute_id, 'mediation')
        assert d2.status == DisputeStatus.MEDIATION

    def test_valid_transition_to_resolved(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.transition(d.dispute_id, 'under_review')
        d2 = mgr.transition(d.dispute_id, 'resolved')
        assert d2.status == DisputeStatus.RESOLVED
        assert d2.resolved_at is not None

    def test_valid_transition_to_rejected(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        d2 = mgr.transition(d.dispute_id, 'rejected')
        assert d2.status == DisputeStatus.REJECTED
        assert d2.resolved_at is not None

    def test_invalid_transition_resolved_to_opened(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.transition(d.dispute_id, 'under_review')
        mgr.transition(d.dispute_id, 'resolved')
        with pytest.raises(ValueError):
            mgr.transition(d.dispute_id, 'opened')

    def test_invalid_transition_opened_to_resolved(self):
        """opened에서 바로 resolved는 불가."""
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        with pytest.raises(ValueError):
            mgr.transition(d.dispute_id, 'resolved')

    def test_transition_nonexistent(self):
        mgr = DisputeManager()
        with pytest.raises(KeyError):
            mgr.transition('nonexistent', 'under_review')

    def test_transition_invalid_status(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        with pytest.raises(ValueError):
            mgr.transition(d.dispute_id, 'invalid_status')

    def test_stats(self):
        mgr = DisputeManager()
        mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        stats = mgr.stats()
        assert stats['total'] == 2
        assert stats['by_status']['opened'] == 2
        assert 'quality_issue' in stats['by_type']


# ---------------------------------------------------------------------------
# EvidenceCollector
# ---------------------------------------------------------------------------

class TestEvidenceCollector:
    def test_add_evidence(self):
        ec = EvidenceCollector()
        ev = ec.add('D-001', 'photo', 'photo.jpg')
        assert ev.evidence_id
        assert ev.dispute_id == 'D-001'
        assert ev.evidence_type == EvidenceType.PHOTO

    def test_add_invalid_type(self):
        ec = EvidenceCollector()
        with pytest.raises(ValueError):
            ec.add('D-001', 'invalid_type', 'file.jpg')

    def test_list_evidence(self):
        ec = EvidenceCollector()
        ec.add('D-001', 'photo', 'photo1.jpg')
        ec.add('D-001', 'screenshot', 'ss.png')
        evs = ec.list('D-001')
        assert len(evs) == 2

    def test_list_empty(self):
        ec = EvidenceCollector()
        assert ec.list('nonexistent') == []

    def test_get_evidence(self):
        ec = EvidenceCollector()
        ev = ec.add('D-001', 'photo', 'photo.jpg')
        found = ec.get('D-001', ev.evidence_id)
        assert found is not None
        assert found.evidence_id == ev.evidence_id

    def test_get_nonexistent(self):
        ec = EvidenceCollector()
        assert ec.get('D-001', 'nonexistent') is None

    def test_delete_evidence(self):
        ec = EvidenceCollector()
        ev = ec.add('D-001', 'photo', 'photo.jpg')
        result = ec.delete('D-001', ev.evidence_id)
        assert result is True
        assert ec.count('D-001') == 0

    def test_delete_nonexistent(self):
        ec = EvidenceCollector()
        result = ec.delete('D-001', 'nonexistent')
        assert result is False

    def test_max_evidence_limit(self):
        ec = EvidenceCollector()
        for i in range(MAX_EVIDENCE_PER_DISPUTE):
            ec.add('D-001', 'photo', f'photo{i}.jpg')
        with pytest.raises(ValueError):
            ec.add('D-001', 'photo', 'one_more.jpg')

    def test_has_photo_evidence_true(self):
        ec = EvidenceCollector()
        ec.add('D-001', 'photo', 'photo.jpg')
        assert ec.has_photo_evidence('D-001') is True

    def test_has_photo_evidence_screenshot(self):
        ec = EvidenceCollector()
        ec.add('D-001', 'screenshot', 'ss.png')
        assert ec.has_photo_evidence('D-001') is True

    def test_has_photo_evidence_false(self):
        ec = EvidenceCollector()
        ec.add('D-001', 'invoice', 'invoice.pdf')
        assert ec.has_photo_evidence('D-001') is False

    def test_to_dict_keys(self):
        ec = EvidenceCollector()
        ev = ec.add('D-001', 'photo', 'photo.jpg', file_size=1024)
        dd = ev.to_dict()
        for key in ('evidence_id', 'dispute_id', 'evidence_type', 'file_name',
                    'file_type', 'file_size', 'description', 'uploaded_at'):
            assert key in dd


# ---------------------------------------------------------------------------
# MediationService 자동 판정
# ---------------------------------------------------------------------------

class TestMediationService:
    def test_small_amount_auto_refund(self):
        svc = MediationService()
        decision = svc.mediate('D-001', amount=30000, dispute_type='quality_issue')
        assert decision.result == MediationResult.FULL_REFUND
        assert decision.is_auto is True

    def test_shipping_delay_auto_refund(self):
        svc = MediationService()
        decision = svc.mediate('D-001', amount=150000, dispute_type='item_not_received',
                               shipping_delay_days=10)
        assert decision.result == MediationResult.FULL_REFUND

    def test_photo_evidence_auto_refund(self):
        svc = MediationService()
        decision = svc.mediate('D-001', amount=150000, dispute_type='item_not_as_described',
                               has_photo_evidence=True)
        assert decision.result == MediationResult.FULL_REFUND

    def test_no_rules_pending_review(self):
        svc = MediationService()
        decision = svc.mediate('D-001', amount=150000, dispute_type='quality_issue',
                               shipping_delay_days=0, has_photo_evidence=False)
        assert decision.result == MediationResult.PENDING_REVIEW
        assert 'D-001' in svc.pending_queue()

    def test_pending_queue_removal(self):
        svc = MediationService()
        svc.mediate('D-001', amount=150000, dispute_type='quality_issue')
        svc.remove_from_queue('D-001')
        assert 'D-001' not in svc.pending_queue()

    def test_get_decision(self):
        svc = MediationService()
        svc.mediate('D-001', amount=30000, dispute_type='quality_issue')
        dec = svc.get_decision('D-001')
        assert dec is not None
        assert dec.dispute_id == 'D-001'

    def test_resolve_manually(self):
        svc = MediationService()
        svc.mediate('D-001', amount=150000, dispute_type='quality_issue')
        dec = svc.resolve_manually('D-001', 'partial_refund', '수동 판정', refund_ratio=0.5)
        assert dec.result == MediationResult.PARTIAL_REFUND
        assert dec.is_auto is False
        assert 'D-001' not in svc.pending_queue()

    def test_resolve_manually_invalid_result(self):
        svc = MediationService()
        with pytest.raises(ValueError):
            svc.resolve_manually('D-001', 'invalid_result', '이유')

    def test_to_dict_keys(self):
        svc = MediationService()
        dec = svc.mediate('D-001', amount=30000, dispute_type='quality_issue')
        dd = dec.to_dict()
        for key in ('dispute_id', 'result', 'reason', 'refund_ratio', 'decided_at', 'is_auto'):
            assert key in dd


# ---------------------------------------------------------------------------
# RefundDecision 환불 계산
# ---------------------------------------------------------------------------

class TestRefundDecision:
    def test_full_refund(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'full_refund')
        assert result.refund_type == RefundType.FULL
        assert result.refund_amount == 100000
        assert result.refund_ratio == 1.0

    def test_partial_refund_no_usage(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'partial_refund', usage_days=0, damage_level=0.0)
        assert result.refund_type == RefundType.PARTIAL
        assert result.refund_amount == 100000

    def test_partial_refund_medium_usage(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'partial_refund', usage_days=15)
        assert result.refund_amount == 90000

    def test_partial_refund_long_usage(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'partial_refund', usage_days=60)
        assert result.refund_amount == 70000

    def test_partial_refund_very_long_usage(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'partial_refund', usage_days=100)
        assert result.refund_amount == 50000

    def test_partial_refund_with_damage(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'partial_refund', usage_days=0, damage_level=0.5)
        assert result.refund_amount == 50000

    def test_rejected(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'rejected')
        assert result.refund_type == RefundType.REJECTED
        assert result.refund_amount == 0.0

    def test_invalid_refund_type(self):
        rd = RefundDecision()
        with pytest.raises(ValueError):
            rd.decide('D-001', 100000, 'invalid_type')

    def test_seller_penalty_none(self):
        rd = RefundDecision()
        penalty = rd.record_seller_dispute('SELLER-001', total_orders=100)
        assert penalty == SellerPenalty.NONE

    def test_seller_penalty_warning(self):
        rd = RefundDecision()
        # 분쟁률 6%: 6/100
        for _ in range(6):
            penalty = rd.record_seller_dispute('SELLER-001', total_orders=100)
        assert penalty == SellerPenalty.WARNING

    def test_seller_penalty_restricted(self):
        rd = RefundDecision()
        # 분쟁률 11%: 11/100
        for _ in range(11):
            penalty = rd.record_seller_dispute('SELLER-001', total_orders=100)
        assert penalty == SellerPenalty.RESTRICTED

    def test_get_seller_stats(self):
        rd = RefundDecision()
        rd.record_seller_dispute('SELLER-001', total_orders=50)
        stats = rd.get_seller_stats('SELLER-001')
        assert stats is not None
        assert stats['dispute_count'] == 1
        assert stats['total_orders'] == 50

    def test_get_seller_penalty_unknown(self):
        rd = RefundDecision()
        assert rd.get_seller_penalty('UNKNOWN') is None

    def test_to_dict_keys(self):
        rd = RefundDecision()
        result = rd.decide('D-001', 100000, 'full_refund')
        dd = result.to_dict()
        for key in ('dispute_id', 'refund_type', 'original_amount', 'refund_amount', 'refund_ratio', 'reason'):
            assert key in dd


# ---------------------------------------------------------------------------
# DisputeAnalytics
# ---------------------------------------------------------------------------

class TestDisputeAnalytics:
    def _make_disputes(self, mgr, n=3):
        disputes = []
        for i in range(n):
            d = mgr.create(f'ORD-{i:03}', f'CUST-{i:03}', '이유', 'quality_issue')
            disputes.append(d)
        return disputes

    def test_dispute_rate(self):
        ana = DisputeAnalytics()
        rate = ana.dispute_rate(5, 100)
        assert rate == 0.05

    def test_dispute_rate_zero_orders(self):
        ana = DisputeAnalytics()
        assert ana.dispute_rate(5, 0) == 0.0

    def test_average_resolution_time_no_resolved(self):
        mgr = DisputeManager()
        disputes = self._make_disputes(mgr, 3)
        ana = DisputeAnalytics()
        assert ana.average_resolution_time(disputes) == 0.0

    def test_average_resolution_time_with_resolved(self):
        mgr = DisputeManager()
        d = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.transition(d.dispute_id, 'under_review')
        mgr.transition(d.dispute_id, 'resolved')
        ana = DisputeAnalytics()
        avg = ana.average_resolution_time([mgr.get(d.dispute_id)])
        assert avg >= 0.0

    def test_by_type(self):
        mgr = DisputeManager()
        mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        mgr.create('ORD-003', 'CUST-003', '이유', 'quality_issue')
        disputes = mgr.list()
        ana = DisputeAnalytics()
        result = ana.by_type(disputes)
        assert result['quality_issue'] == 2
        assert result['wrong_item'] == 1

    def test_by_status(self):
        mgr = DisputeManager()
        d1 = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        d2 = mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        mgr.transition(d1.dispute_id, 'under_review')
        disputes = mgr.list()
        ana = DisputeAnalytics()
        result = ana.by_status(disputes)
        assert result['under_review'] == 1
        assert result['opened'] == 1

    def test_by_seller(self):
        mgr = DisputeManager()
        d1 = mgr.create('ORD-001', 'CUST-001', '이유', 'quality_issue')
        d2 = mgr.create('ORD-002', 'CUST-002', '이유', 'wrong_item')
        disputes = mgr.list()
        order_seller_map = {'ORD-001': 'SELLER-A', 'ORD-002': 'SELLER-A'}
        ana = DisputeAnalytics()
        result = ana.by_seller(disputes, order_seller_map)
        assert result['SELLER-A']['count'] == 2

    def test_summary(self):
        mgr = DisputeManager()
        self._make_disputes(mgr, 3)
        disputes = mgr.list()
        ana = DisputeAnalytics()
        summary = ana.summary(disputes, total_orders=100)
        assert summary['total_disputes'] == 3
        assert summary['dispute_rate'] == 0.03
        assert 'by_type' in summary
        assert 'by_status' in summary


# ---------------------------------------------------------------------------
# API 엔드포인트 테스트
# ---------------------------------------------------------------------------

class TestDisputesAPI:
    @pytest.fixture
    def client(self):
        from flask import Flask
        from src.api.disputes_api import disputes_bp, _get_services
        import src.api.disputes_api as api_module
        # 서비스 초기화 초기화
        api_module._manager = None
        api_module._evidence = None
        api_module._mediation = None
        api_module._refund = None
        api_module._analytics = None

        app = Flask(__name__)
        app.register_blueprint(disputes_bp)
        app.config['TESTING'] = True
        return app.test_client()

    def test_create_dispute(self, client):
        resp = client.post('/api/v1/disputes/', json={
            'order_id': 'ORD-001',
            'customer_id': 'CUST-001',
            'reason': '상품 미수령',
            'dispute_type': 'item_not_received',
            'amount': 50000,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['dispute_id']
        assert data['status'] == 'opened'

    def test_create_dispute_missing_fields(self, client):
        resp = client.post('/api/v1/disputes/', json={'order_id': 'ORD-001'})
        assert resp.status_code == 400

    def test_list_disputes(self, client):
        client.post('/api/v1/disputes/', json={
            'order_id': 'ORD-001', 'customer_id': 'CUST-001',
            'reason': '이유', 'dispute_type': 'quality_issue',
        })
        resp = client.get('/api/v1/disputes/')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_dispute(self, client):
        resp = client.post('/api/v1/disputes/', json={
            'order_id': 'ORD-001', 'customer_id': 'CUST-001',
            'reason': '이유', 'dispute_type': 'quality_issue',
        })
        dispute_id = resp.get_json()['dispute_id']
        resp2 = client.get(f'/api/v1/disputes/{dispute_id}')
        assert resp2.status_code == 200

    def test_get_dispute_not_found(self, client):
        resp = client.get('/api/v1/disputes/nonexistent')
        assert resp.status_code == 404

    def test_update_status(self, client):
        resp = client.post('/api/v1/disputes/', json={
            'order_id': 'ORD-001', 'customer_id': 'CUST-001',
            'reason': '이유', 'dispute_type': 'quality_issue',
        })
        dispute_id = resp.get_json()['dispute_id']
        resp2 = client.put(f'/api/v1/disputes/{dispute_id}/status',
                           json={'status': 'under_review'})
        assert resp2.status_code == 200
        assert resp2.get_json()['status'] == 'under_review'

    def test_add_evidence(self, client):
        resp = client.post('/api/v1/disputes/', json={
            'order_id': 'ORD-001', 'customer_id': 'CUST-001',
            'reason': '이유', 'dispute_type': 'quality_issue',
        })
        dispute_id = resp.get_json()['dispute_id']
        resp2 = client.post(f'/api/v1/disputes/{dispute_id}/evidence', json={
            'evidence_type': 'photo',
            'file_name': 'photo.jpg',
            'file_size': 1024,
        })
        assert resp2.status_code == 201
        assert resp2.get_json()['evidence_id']

    def test_list_evidence(self, client):
        resp = client.post('/api/v1/disputes/', json={
            'order_id': 'ORD-001', 'customer_id': 'CUST-001',
            'reason': '이유', 'dispute_type': 'quality_issue',
        })
        dispute_id = resp.get_json()['dispute_id']
        resp2 = client.get(f'/api/v1/disputes/{dispute_id}/evidence')
        assert resp2.status_code == 200
        assert isinstance(resp2.get_json(), list)

    def test_mediate(self, client):
        resp = client.post('/api/v1/disputes/', json={
            'order_id': 'ORD-001', 'customer_id': 'CUST-001',
            'reason': '이유', 'dispute_type': 'quality_issue',
            'amount': 30000,
        })
        dispute_id = resp.get_json()['dispute_id']
        resp2 = client.post(f'/api/v1/disputes/{dispute_id}/mediate', json={})
        assert resp2.status_code == 200
        assert resp2.get_json()['result'] == 'full_refund'

    def test_analytics(self, client):
        resp = client.get('/api/v1/disputes/analytics?total_orders=100')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_disputes' in data
        assert 'dispute_rate' in data
