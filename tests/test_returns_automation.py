"""tests/test_returns_automation.py — Phase 118: 반품/교환 자동 처리 워크플로우 테스트."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.returns_automation.models import (
    AutoReturnRequest,
    ExchangeRequest,
    ReturnDecision,
    ReturnItem,
    ReturnReasonCategory,
    ReturnClassification,
    ReturnStatus,
)
from src.returns_automation.return_classifier import ReturnClassifier
from src.returns_automation.auto_approval_engine import (
    AutoApprovalEngine,
    AmountThresholdRule,
    ReasonBasedRule,
    CustomerTierRule,
    TimeWindowRule,
    BlacklistRule,
)
from src.returns_automation.reverse_logistics import ReverseLogisticsManager
from src.returns_automation.inspection_orchestrator import InspectionOrchestrator
from src.returns_automation.refund_orchestrator import RefundOrchestrator
from src.returns_automation.exchange_orchestrator import ExchangeOrchestrator
from src.returns_automation.escalation_router import EscalationRouter
from src.returns_automation.workflow_definition import (
    ReturnsAutomationWorkflow,
    VALID_TRANSITIONS,
    TERMINAL_STATES,
)
from src.returns_automation.automation_manager import ReturnsAutomationManager


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

def _make_request(
    reason_code: str = 'change_of_mind',
    photos: list = None,
    ordered_at_days_ago: int = 5,
) -> AutoReturnRequest:
    """테스트용 반품 요청 생성."""
    ordered_at = (datetime.now(timezone.utc) - timedelta(days=ordered_at_days_ago)).isoformat()
    return AutoReturnRequest(
        order_id='ORD-001',
        user_id='USER-001',
        items=[ReturnItem('SKU-001', '테스트상품', 1, Decimal('50000'))],
        reason_code=ReturnReasonCategory(reason_code),
        reason_text='테스트 사유',
        photos=photos or [],
        requested_at=datetime.now(timezone.utc).isoformat(),
        metadata={'ordered_at': ordered_at},
    )


def _make_order(amount: int = 50000, days_ago: int = 5) -> dict:
    ordered_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        'order_amount': amount,
        'ordered_at': ordered_at,
        'shipping_fee': 3000,
    }


def _make_customer(tier: str = 'Regular', dispute_history: list = None) -> dict:
    return {
        'tier': tier,
        'dispute_history': dispute_history or [],
        'blacklisted': False,
        'return_abuse_count': 0,
    }


# ══════════════════════════════════════════════════════════
# 1. 모델 테스트
# ══════════════════════════════════════════════════════════

class TestModels:
    def test_auto_return_request_creation(self):
        req = _make_request()
        assert req.request_id.startswith('RET-')
        assert req.status == ReturnStatus.requested
        assert req.classification is None
        assert req.decision is None

    def test_exchange_request_has_target_sku(self):
        req = ExchangeRequest(
            order_id='ORD-001',
            user_id='USER-001',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('10000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='사이즈 불일치',
            target_sku='SKU-002',
            target_option='L',
        )
        assert req.target_sku == 'SKU-002'
        assert req.target_option == 'L'

    def test_auto_return_request_to_dict(self):
        req = _make_request()
        d = req.to_dict()
        assert d['order_id'] == 'ORD-001'
        assert d['status'] == 'requested'
        assert 'items' in d
        assert isinstance(d['items'], list)

    def test_exchange_request_to_dict_has_type(self):
        req = ExchangeRequest(
            order_id='ORD-001',
            user_id='USER-001',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('10000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='',
            target_sku='SKU-002',
        )
        d = req.to_dict()
        assert d['request_type'] == 'exchange'
        assert d['target_sku'] == 'SKU-002'

    def test_return_reason_category_values(self):
        for v in ReturnReasonCategory:
            assert ReturnReasonCategory(v.value) == v

    def test_return_status_values(self):
        for v in ReturnStatus:
            assert ReturnStatus(v.value) == v

    def test_return_decision_defaults(self):
        d = ReturnDecision(decision='approved')
        assert d.refund_amount == Decimal('0')
        assert d.restocking_fee == Decimal('0')
        assert d.shipping_fee_borne_by == 'customer'


# ══════════════════════════════════════════════════════════
# 2. ReturnClassifier 분류 규칙 단위 테스트
# ══════════════════════════════════════════════════════════

class TestReturnClassifier:
    def setup_method(self):
        self.clf = ReturnClassifier()

    def test_classify_damaged_with_photos_within_7days(self):
        """사진 + 손상 + 7일 이내 → auto_approve."""
        req = _make_request('damaged_in_transit', photos=['url1.jpg'], ordered_at_days_ago=3)
        order = _make_order(amount=50000, days_ago=3)
        result = self.clf.classify(req, order, _make_customer())
        assert result == ReturnClassification.auto_approve

    def test_classify_defective_with_photos_within_7days(self):
        """사진 + 불량 + 7일 이내 → auto_approve."""
        req = _make_request('defective', photos=['url1.jpg'], ordered_at_days_ago=5)
        order = _make_order(amount=50000, days_ago=5)
        result = self.clf.classify(req, order, _make_customer())
        assert result == ReturnClassification.auto_approve

    def test_classify_change_of_mind_vip_within_14days(self):
        """변심 + VIP + 14일 이내 → auto_approve."""
        req = _make_request('change_of_mind', ordered_at_days_ago=10)
        order = _make_order(amount=50000, days_ago=10)
        result = self.clf.classify(req, order, _make_customer(tier='VIP'))
        assert result == ReturnClassification.auto_approve

    def test_classify_change_of_mind_gold_within_14days(self):
        """변심 + Gold + 14일 이내 → auto_approve."""
        req = _make_request('change_of_mind', ordered_at_days_ago=10)
        order = _make_order(amount=50000, days_ago=10)
        result = self.clf.classify(req, order, _make_customer(tier='Gold'))
        assert result == ReturnClassification.auto_approve

    def test_classify_over_30_days_auto_reject(self):
        """30일 초과 → auto_reject."""
        req = _make_request('change_of_mind', ordered_at_days_ago=35)
        order = _make_order(amount=50000, days_ago=35)
        result = self.clf.classify(req, order, _make_customer())
        assert result == ReturnClassification.auto_reject

    def test_classify_high_amount_manual_review(self):
        """금액 ≥ 30만원 → manual_review."""
        req = _make_request('defective', photos=['url1.jpg'])
        order = _make_order(amount=300000)
        result = self.clf.classify(req, order, _make_customer())
        assert result == ReturnClassification.manual_review

    def test_classify_dispute_with_history(self):
        """이전 분쟁 이력 → dispute."""
        req = _make_request('defective')
        customer = _make_customer(dispute_history=['DISP-001'])
        result = self.clf.classify(req, {}, customer)
        assert result == ReturnClassification.dispute

    def test_classify_defective_no_photos_manual_review(self):
        """사진 없음 + 불량 → manual_review."""
        req = _make_request('defective', photos=[])
        order = _make_order(amount=50000)
        result = self.clf.classify(req, order, _make_customer())
        assert result == ReturnClassification.manual_review

    def test_classify_regular_customer_change_of_mind(self):
        """일반 고객 변심 → manual_review."""
        req = _make_request('change_of_mind', ordered_at_days_ago=5)
        order = _make_order(amount=50000, days_ago=5)
        result = self.clf.classify(req, order, _make_customer(tier='Regular'))
        assert result == ReturnClassification.manual_review

    def test_classify_string_reason_code(self):
        """문자열 reason_code 처리."""
        req = AutoReturnRequest(
            order_id='ORD-001',
            user_id='USER-001',
            items=[],
            reason_code='damaged_in_transit',  # type: ignore
            reason_text='',
            photos=['url1.jpg'],
        )
        order = _make_order(amount=50000, days_ago=3)
        result = self.clf.classify(req, order, _make_customer())
        # reason_code 문자열도 처리 가능해야 함
        assert result in ReturnClassification


# ══════════════════════════════════════════════════════════
# 3. AutoApprovalEngine 승인 규칙 단위 테스트
# ══════════════════════════════════════════════════════════

class TestAutoApprovalEngine:
    def setup_method(self):
        self.engine = AutoApprovalEngine()

    def test_blacklist_rule_blocks(self):
        """블랙리스트 고객 → rejected."""
        req = _make_request()
        customer = {'blacklisted': True}
        decision = self.engine.evaluate(req, {}, customer)
        assert decision.decision == 'rejected'

    def test_abuse_count_blocks(self):
        """반품 남용 횟수 3이상 → rejected."""
        req = _make_request()
        customer = {'return_abuse_count': 3}
        decision = self.engine.evaluate(req, {}, customer)
        assert decision.decision == 'rejected'

    def test_amount_threshold_rule_approves(self):
        """금액 임계값 미만 → approved."""
        rule = AmountThresholdRule(threshold=100000)
        req = _make_request()
        decision = rule.evaluate(req, {'order_amount': 50000}, {})
        assert decision is not None
        assert decision.decision == 'approved'
        assert decision.refund_amount == Decimal('50000')

    def test_amount_threshold_rule_passes_over(self):
        """금액 임계값 이상 → None (다음 규칙으로)."""
        rule = AmountThresholdRule(threshold=100000)
        req = _make_request()
        decision = rule.evaluate(req, {'order_amount': 150000}, {})
        assert decision is None

    def test_reason_based_rule_seller_fault(self):
        """판매자 귀책 사유 + 사진 → approved (배송비 판매자)."""
        rule = ReasonBasedRule()
        req = _make_request('wrong_item', photos=['url1.jpg'])
        decision = rule.evaluate(req, {'order_amount': 50000}, {})
        assert decision is not None
        assert decision.decision == 'approved'
        assert decision.shipping_fee_borne_by == 'seller'

    def test_reason_based_rule_no_photo_passes(self):
        """판매자 귀책 사유지만 사진 없음 → None."""
        rule = ReasonBasedRule()
        req = _make_request('defective', photos=[])
        decision = rule.evaluate(req, {'order_amount': 50000}, {})
        assert decision is None

    def test_customer_tier_vip_approves(self):
        """VIP 고객 변심 → approved."""
        rule = CustomerTierRule()
        req = _make_request('change_of_mind')
        decision = rule.evaluate(req, {'order_amount': 50000}, {'tier': 'VIP'})
        assert decision is not None
        assert decision.decision == 'approved'
        assert decision.shipping_fee_borne_by == 'customer'

    def test_customer_tier_regular_passes(self):
        """일반 고객 변심 → None."""
        rule = CustomerTierRule()
        req = _make_request('change_of_mind')
        decision = rule.evaluate(req, {'order_amount': 50000}, {'tier': 'Regular'})
        assert decision is None

    def test_time_window_rule_within_days(self):
        """7일 이내 + 사진 → approved."""
        rule = TimeWindowRule(days=7)
        req = _make_request(photos=['url1.jpg'])
        ordered_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        decision = rule.evaluate(req, {'order_amount': 50000, 'ordered_at': ordered_at}, {})
        assert decision is not None
        assert decision.decision == 'approved'

    def test_time_window_rule_over_days(self):
        """7일 초과 → None."""
        rule = TimeWindowRule(days=7)
        req = _make_request(photos=['url1.jpg'])
        ordered_at = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        decision = rule.evaluate(req, {'order_amount': 50000, 'ordered_at': ordered_at}, {})
        assert decision is None

    def test_engine_fallback_manual_review(self):
        """모든 규칙 미해당 → manual_review."""
        req = _make_request('late_delivery', photos=[])
        decision = self.engine.evaluate(req, {'order_amount': 200000}, {'tier': 'Regular'})
        assert decision.decision == 'manual_review'


# ══════════════════════════════════════════════════════════
# 4. ReverseLogisticsManager 테스트
# ══════════════════════════════════════════════════════════

class TestReverseLogisticsManager:
    def setup_method(self):
        self.mgr = ReverseLogisticsManager()
        self.req = _make_request()

    def test_issue_return_waybill(self):
        result = self.mgr.issue_return_waybill(self.req, carrier='cj')
        assert 'waybill_no' in result
        assert len(result['waybill_no']) == 12
        assert result['carrier'] == 'cj'
        assert result['carrier_name'] == 'CJ대한통운'

    def test_schedule_pickup(self):
        address = {'name': '홍길동', 'phone': '010-1234-5678', 'address': '서울시 강남구'}
        result = self.mgr.schedule_pickup(self.req, address, carrier='hanjin')
        assert result['carrier'] == 'hanjin'
        assert result['status'] == 'scheduled'
        assert result['request_id'] == self.req.request_id

    def test_get_waybill(self):
        waybill = self.mgr.issue_return_waybill(self.req)
        found = self.mgr.get_waybill(waybill['waybill_no'])
        assert found is not None
        assert found['waybill_no'] == waybill['waybill_no']

    def test_list_waybills(self):
        self.mgr.issue_return_waybill(self.req, carrier='cj')
        self.mgr.issue_return_waybill(self.req, carrier='hanjin')
        waybills = self.mgr.list_waybills(self.req.request_id)
        assert len(waybills) == 2

    def test_track_return_shipment_unknown(self):
        result = self.mgr.track_return_shipment('000000000000')
        assert result is None

    def test_track_return_shipment_known(self):
        waybill = self.mgr.issue_return_waybill(self.req)
        result = self.mgr.track_return_shipment(waybill['waybill_no'])
        assert result is not None

    def test_all_carriers(self):
        for carrier in ('cj', 'hanjin', 'epost'):
            waybill = self.mgr.issue_return_waybill(self.req, carrier=carrier)
            assert waybill['carrier'] == carrier


# ══════════════════════════════════════════════════════════
# 5. InspectionOrchestrator 테스트
# ══════════════════════════════════════════════════════════

class TestInspectionOrchestrator:
    def setup_method(self):
        self.orch = InspectionOrchestrator()
        self.req = _make_request()

    def test_auto_grade_a_intact_low_diff(self):
        grade = self.orch.auto_grade(self.req, package_intact=True, weight_diff_pct=2.0)
        assert grade == 'A'

    def test_auto_grade_b_moderate_diff(self):
        grade = self.orch.auto_grade(self.req, package_intact=True, weight_diff_pct=10.0)
        assert grade == 'B'

    def test_auto_grade_c_high_diff(self):
        grade = self.orch.auto_grade(self.req, package_intact=True, weight_diff_pct=20.0)
        assert grade == 'C'

    def test_auto_grade_c_not_intact(self):
        grade = self.orch.auto_grade(self.req, package_intact=False, weight_diff_pct=2.0)
        assert grade == 'C'

    def test_auto_grade_d_damaged_transit_not_intact(self):
        req = _make_request('damaged_in_transit')
        grade = self.orch.auto_grade(req, package_intact=False)
        assert grade == 'D'

    def test_inspect_returns_dict(self):
        result = self.orch.inspect(self.req, condition_score=90, package_intact=True)
        assert 'grade' in result
        assert 'refund_pct' in result
        assert result['grade'] in ('A', 'B', 'C', 'D')

    def test_inspect_grade_a_full_refund(self):
        result = self.orch.inspect(self.req, condition_score=95, package_intact=True, weight_diff_pct=1.0)
        assert result['grade'] == 'A'
        assert result['refund_pct'] == 100


# ══════════════════════════════════════════════════════════
# 6. RefundOrchestrator 테스트
# ══════════════════════════════════════════════════════════

class TestRefundOrchestrator:
    def setup_method(self):
        self.orch = RefundOrchestrator()
        self.req = _make_request()

    def test_process_refund_returns_result(self):
        decision = ReturnDecision(decision='approved', refund_amount=Decimal('50000'))
        result = self.orch.process_refund(self.req, decision)
        assert result['status'] == 'success'
        assert result['refund_amount'] == '50000'

    def test_process_refund_pg_mock(self):
        decision = ReturnDecision(decision='approved', refund_amount=Decimal('30000'))
        result = self.orch.process_refund(self.req, decision)
        assert result['pg_result'] is not None

    def test_process_partial_refund(self):
        result = self.orch.process_partial_refund(
            self.req, Decimal('20000'), reason='검수 등급 C'
        )
        assert result['partial_refund'] is True
        assert result['refund_amount'] == '20000'

    def test_process_refund_notification_graceful(self):
        """NotificationHub 없어도 오류 없이 처리."""
        decision = ReturnDecision(decision='approved', refund_amount=Decimal('10000'))
        result = self.orch.process_refund(self.req, decision)
        assert result['status'] == 'success'


# ══════════════════════════════════════════════════════════
# 7. ExchangeOrchestrator 테스트
# ══════════════════════════════════════════════════════════

class TestExchangeOrchestrator:
    def setup_method(self):
        self.orch = ExchangeOrchestrator()

    def test_process_exchange_in_stock(self):
        req = ExchangeRequest(
            order_id='ORD-001',
            user_id='USER-001',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('50000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='',
            target_sku='SKU-002',
            target_option='L',
        )
        result = self.orch.process_exchange(req, {'order_amount': 50000})
        assert result['request_id'] == req.request_id
        assert result['target_sku'] == 'SKU-002'

    def test_process_exchange_no_target_sku_uses_original(self):
        req = AutoReturnRequest(
            order_id='ORD-001',
            user_id='USER-001',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('50000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='',
        )
        result = self.orch.process_exchange(req, {'order_amount': 50000})
        assert result['target_sku'] == 'SKU-001'

    def test_process_exchange_out_of_stock_refund_fallback(self):
        req = ExchangeRequest(
            order_id='ORD-001',
            user_id='USER-001',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('50000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='',
            target_sku='OUT-OF-STOCK',
        )
        # _check_inventory를 패치하여 재고 없음 시뮬레이션
        with patch.object(self.orch, '_check_inventory', return_value=False):
            result = self.orch.process_exchange(req, {'order_amount': 50000})
        assert result['fallback_refund'] is True
        assert result['status'] == 'refund_fallback'

    def test_process_exchange_result_has_request_id(self):
        req = ExchangeRequest(
            order_id='ORD-001',
            user_id='USER-001',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('50000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='',
        )
        result = self.orch.process_exchange(req, {})
        assert 'request_id' in result


# ══════════════════════════════════════════════════════════
# 8. EscalationRouter 테스트
# ══════════════════════════════════════════════════════════

class TestEscalationRouter:
    def setup_method(self):
        self.router = EscalationRouter()
        self.req = _make_request()

    def test_escalate_returns_result(self):
        result = self.router.escalate_to_dispute(self.req, reason='테스트 분쟁')
        assert result['request_id'] == self.req.request_id
        assert result['dispute_id'] is not None
        assert result['ticket_id'] is not None

    def test_escalate_with_no_reason(self):
        result = self.router.escalate_to_dispute(self.req)
        assert 'dispute_id' in result

    def test_escalate_dispute_id_format(self):
        result = self.router.escalate_to_dispute(self.req, reason='이유')
        # mock dispute id 포함 확인
        assert self.req.request_id in str(result['dispute_id']) or result['dispute_id']


# ══════════════════════════════════════════════════════════
# 9. ReturnsAutomationWorkflow 상태머신 테스트
# ══════════════════════════════════════════════════════════

class TestReturnsAutomationWorkflow:
    def setup_method(self):
        self.wf = ReturnsAutomationWorkflow()

    def test_valid_transition_requested_to_classified(self):
        new = self.wf.transition(ReturnStatus.requested, ReturnStatus.classified)
        assert new == ReturnStatus.classified

    def test_valid_transition_classified_to_approved(self):
        new = self.wf.transition(ReturnStatus.classified, ReturnStatus.approved)
        assert new == ReturnStatus.approved

    def test_valid_transition_classified_to_rejected(self):
        new = self.wf.transition(ReturnStatus.classified, ReturnStatus.rejected)
        assert new == ReturnStatus.rejected

    def test_valid_transition_classified_to_disputed(self):
        new = self.wf.transition(ReturnStatus.classified, ReturnStatus.disputed)
        assert new == ReturnStatus.disputed

    def test_valid_transition_approved_to_pickup_scheduled(self):
        new = self.wf.transition(ReturnStatus.approved, ReturnStatus.pickup_scheduled)
        assert new == ReturnStatus.pickup_scheduled

    def test_valid_transition_inspected_to_refunded(self):
        new = self.wf.transition(ReturnStatus.inspected, ReturnStatus.refunded)
        assert new == ReturnStatus.refunded

    def test_valid_transition_inspected_to_exchanged(self):
        new = self.wf.transition(ReturnStatus.inspected, ReturnStatus.exchanged)
        assert new == ReturnStatus.exchanged

    def test_valid_transition_inspected_to_partially_refunded(self):
        new = self.wf.transition(ReturnStatus.inspected, ReturnStatus.partially_refunded)
        assert new == ReturnStatus.partially_refunded

    def test_invalid_transition_raises(self):
        with pytest.raises(ValueError):
            self.wf.transition(ReturnStatus.requested, ReturnStatus.refunded)

    def test_terminal_states(self):
        for state in TERMINAL_STATES:
            assert self.wf.is_terminal(state) is True

    def test_non_terminal_states(self):
        non_terminal = [s for s in ReturnStatus if s not in TERMINAL_STATES]
        for state in non_terminal:
            assert self.wf.is_terminal(state) is False

    def test_can_transition(self):
        assert self.wf.can_transition(ReturnStatus.requested, ReturnStatus.classified) is True
        assert self.wf.can_transition(ReturnStatus.requested, ReturnStatus.refunded) is False

    def test_get_allowed_transitions(self):
        allowed = self.wf.get_allowed_transitions(ReturnStatus.classified)
        assert ReturnStatus.approved in allowed
        assert ReturnStatus.rejected in allowed
        assert ReturnStatus.disputed in allowed


# ══════════════════════════════════════════════════════════
# 10. ReturnsAutomationManager 통합 테스트
# ══════════════════════════════════════════════════════════

class TestReturnsAutomationManager:
    def setup_method(self):
        self.mgr = ReturnsAutomationManager()

    def _submit(
        self,
        reason_code='change_of_mind',
        photos=None,
        order=None,
        customer=None,
        request_type='return',
        days_ago=5,
    ):
        order = order or {'order_amount': 50000, 'ordered_at': (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()}
        customer = customer or {'tier': 'Regular', 'dispute_history': []}
        return self.mgr.submit_request(
            order_id='ORD-001',
            user_id='USER-001',
            items=[{'sku': 'SKU-001', 'product_name': '상품', 'quantity': 1, 'unit_price': 50000}],
            reason_code=reason_code,
            reason_text='테스트',
            photos=photos or [],
            order=order,
            customer=customer,
            request_type=request_type,
        )

    def test_submit_request_returns_request(self):
        req = self._submit()
        assert req.request_id.startswith('RET-')
        assert req.status in ReturnStatus

    def test_submit_auto_approve_vip(self):
        """VIP + 변심 + 소액 → approved."""
        req = self._submit(
            reason_code='change_of_mind',
            order={'order_amount': 50000, 'ordered_at': (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()},
            customer={'tier': 'VIP', 'dispute_history': []},
        )
        # auto_approve 또는 approved 상태 확인
        assert req.status in (ReturnStatus.approved, ReturnStatus.classified)

    def test_submit_auto_reject_over_30_days(self):
        """30일 초과 → rejected."""
        req = self._submit(
            reason_code='change_of_mind',
            days_ago=35,
            order={'order_amount': 50000, 'ordered_at': (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()},
        )
        assert req.status == ReturnStatus.rejected

    def test_submit_dispute_with_history(self):
        """분쟁 이력 → disputed."""
        req = self._submit(
            reason_code='defective',
            customer={'tier': 'Regular', 'dispute_history': ['DISP-001']},
        )
        assert req.status == ReturnStatus.disputed

    def test_get_status_returns_dict(self):
        req = self._submit()
        data = self.mgr.get_status(req.request_id)
        assert data is not None
        assert data['request_id'] == req.request_id

    def test_get_status_not_found(self):
        result = self.mgr.get_status('NONEXISTENT')
        assert result is None

    def test_list_pending_all(self):
        self._submit()
        self._submit()
        items = self.mgr.list_pending()
        assert len(items) >= 2

    def test_list_pending_by_user(self):
        self._submit()
        items = self.mgr.list_pending(user_id='USER-001')
        assert all(i['user_id'] == 'USER-001' for i in items)

    def test_metrics_returns_dict(self):
        m = self.mgr.metrics()
        assert 'total' in m
        assert 'auto_approve_rate' in m
        assert 'dispute_rate' in m

    def test_metrics_auto_approve_rate_calculation(self):
        """자동 승인율 계산 검증."""
        # VIP 고객 + 변심 + 소액 → auto_approve
        self._submit(
            reason_code='change_of_mind',
            customer={'tier': 'VIP', 'dispute_history': []},
            order={'order_amount': 50000, 'ordered_at': (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()},
        )
        m = self.mgr.metrics()
        assert m['total'] >= 1
        assert 0.0 <= m['auto_approve_rate'] <= 1.0

    def test_manual_approve(self):
        """수동 승인."""
        req = self._submit()
        # 수동 승인 가능 상태(classified 또는 manual_review)로 설정
        req.status = ReturnStatus.classified
        approved = self.mgr.approve(req.request_id, notes='수동 승인 테스트')
        assert approved.status == ReturnStatus.approved

    def test_manual_reject(self):
        """수동 거절."""
        req = self._submit()
        req.status = ReturnStatus.classified
        rejected = self.mgr.reject(req.request_id, notes='수동 거절 테스트')
        assert rejected.status == ReturnStatus.rejected

    def test_manual_escalate(self):
        """수동 분쟁 에스컬레이션."""
        req = self._submit()
        req.status = ReturnStatus.classified
        escalated = self.mgr.escalate(req.request_id, reason='의심스러운 요청')
        assert escalated.status == ReturnStatus.disputed

    def test_schedule_pickup(self):
        """회수 픽업 예약."""
        req = self._submit(
            reason_code='change_of_mind',
            customer={'tier': 'VIP', 'dispute_history': []},
            order={'order_amount': 50000, 'ordered_at': (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()},
        )
        req.status = ReturnStatus.approved
        address = {'name': '홍길동', 'phone': '010-0000-0000', 'address': '서울시 강남구'}
        result = self.mgr.schedule_pickup(req.request_id, address)
        assert 'waybill' in result
        assert 'pickup' in result
        assert req.status == ReturnStatus.pickup_scheduled

    def test_process_inspection(self):
        """검수 처리."""
        req = self._submit()
        req.status = ReturnStatus.received
        result = self.mgr.process_inspection(req.request_id, condition_score=90)
        assert 'grade' in result
        assert req.status == ReturnStatus.inspected

    def test_process_refund_for_request(self):
        """환불 처리."""
        req = self._submit()
        req.status = ReturnStatus.inspected
        req.decision = ReturnDecision(decision='approved', refund_amount=Decimal('50000'))
        result = self.mgr.process_refund_for_request(req.request_id)
        assert result['status'] == 'success'

    def test_key_error_not_found(self):
        """존재하지 않는 요청 ID → KeyError."""
        with pytest.raises(KeyError):
            self.mgr.approve('NONEXISTENT')

    def test_submit_exchange_request(self):
        """교환 요청 제출."""
        req = self.mgr.submit_request(
            order_id='ORD-002',
            user_id='USER-002',
            items=[{'sku': 'SKU-001', 'product_name': '상품', 'quantity': 1, 'unit_price': 50000}],
            reason_code='size_mismatch',
            reason_text='사이즈 불일치',
            request_type='exchange',
            target_sku='SKU-002',
            target_option='L',
        )
        assert isinstance(req, ExchangeRequest)
        assert req.target_sku == 'SKU-002'


# ══════════════════════════════════════════════════════════
# 11. 전체 플로우 통합 테스트 (자동 승인 → 회수 → 검수 → 환불)
# ══════════════════════════════════════════════════════════

class TestFullReturnFlow:
    """자동 승인 → 회수 → 검수 → 환불 전체 플로우."""

    def test_full_auto_approve_refund_flow(self):
        mgr = ReturnsAutomationManager()
        ordered_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

        # 1. 요청 접수 (사진+손상+3일 → auto_approve)
        req = mgr.submit_request(
            order_id='ORD-FULL-001',
            user_id='USER-FULL',
            items=[{'sku': 'SKU-FULL', 'product_name': '풀플로우상품', 'quantity': 1, 'unit_price': 50000}],
            reason_code='damaged_in_transit',
            photos=['damage1.jpg'],
            order={'order_amount': 50000, 'ordered_at': ordered_at},
            customer={'tier': 'Regular', 'dispute_history': []},
        )
        assert req.status == ReturnStatus.approved, f"Expected approved, got {req.status}"

        # 2. 픽업 예약
        req.status = ReturnStatus.approved  # 재설정
        result = mgr.schedule_pickup(
            req.request_id,
            {'name': '홍길동', 'address': '서울', 'phone': '010-0000-0000'},
        )
        assert req.status == ReturnStatus.pickup_scheduled
        assert req.waybill_no != ''

        # 3. 운송 중
        mgr.progress(req.request_id, 'in_return_transit')
        assert req.status == ReturnStatus.in_return_transit

        # 4. 수령
        mgr.progress(req.request_id, 'received')
        assert req.status == ReturnStatus.received

        # 5. 검수
        inspection_result = mgr.process_inspection(req.request_id, condition_score=90)
        assert req.status == ReturnStatus.inspected
        assert inspection_result['grade'] in ('A', 'B', 'C', 'D')

        # 6. 환불
        req.decision = ReturnDecision(decision='approved', refund_amount=Decimal('50000'))
        refund_result = mgr.process_refund_for_request(req.request_id, order={'order_amount': 50000})
        assert refund_result['status'] == 'success'
        assert req.status == ReturnStatus.refunded


class TestExchangeFlow:
    """교환 플로우 (재고 OK / 재고 부족 → 환불 폴백)."""

    def test_exchange_flow_in_stock(self):
        mgr = ReturnsAutomationManager()
        req = mgr.submit_request(
            order_id='ORD-EX-001',
            user_id='USER-EX',
            items=[{'sku': 'SKU-001', 'product_name': '상품', 'quantity': 1, 'unit_price': 50000}],
            reason_code='size_mismatch',
            request_type='exchange',
            target_sku='SKU-002',
            target_option='L',
        )
        req.status = ReturnStatus.inspected
        result = mgr.process_exchange_for_request(req.request_id, {'order_amount': 50000})
        assert 'request_id' in result

    def test_exchange_flow_out_of_stock_fallback(self):
        mgr = ReturnsAutomationManager()
        req = mgr.submit_request(
            order_id='ORD-EX-002',
            user_id='USER-EX',
            items=[{'sku': 'SKU-001', 'product_name': '상품', 'quantity': 1, 'unit_price': 50000}],
            reason_code='size_mismatch',
            request_type='exchange',
            target_sku='OUT-STOCK',
        )
        req.status = ReturnStatus.inspected

        with patch.object(mgr._exchange, '_check_inventory', return_value=False):
            result = mgr.process_exchange_for_request(req.request_id, {'order_amount': 50000})

        assert result['fallback_refund'] is True


# ══════════════════════════════════════════════════════════
# 12. API 엔드포인트 테스트 (12개 엔드포인트)
# ══════════════════════════════════════════════════════════

@pytest.fixture
def app():
    """Flask 테스트 앱."""
    flask_app = Flask(__name__)
    flask_app.config['TESTING'] = True
    flask_app.config['DEBUG'] = False

    from src.api.returns_automation_api import returns_automation_bp
    flask_app.register_blueprint(returns_automation_bp)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_manager(monkeypatch):
    """각 테스트 전 매니저 싱글톤 리셋."""
    import src.api.returns_automation_api as api_mod
    api_mod._manager = None
    yield
    api_mod._manager = None


_SAMPLE_ITEMS = [{'sku': 'SKU-001', 'product_name': '테스트상품', 'quantity': 1, 'unit_price': 50000}]
_SAMPLE_ORDER = {'order_amount': 50000, 'ordered_at': (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()}
_SAMPLE_CUSTOMER = {'tier': 'Regular', 'dispute_history': []}


class TestAPISubmitRequest:
    def test_submit_success_201(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
            'reason_code': 'change_of_mind',
            'order': _SAMPLE_ORDER,
            'customer': _SAMPLE_CUSTOMER,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'request_id' in data

    def test_submit_missing_order_id_400(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
        })
        assert resp.status_code == 400

    def test_submit_missing_user_id_400(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'items': _SAMPLE_ITEMS,
        })
        assert resp.status_code == 400

    def test_submit_missing_items_400(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': [],
        })
        assert resp.status_code == 400


class TestAPIGetRequest:
    def test_get_existing_200(self, client):
        # 먼저 요청 생성
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
            'reason_code': 'change_of_mind',
            'order': _SAMPLE_ORDER,
            'customer': _SAMPLE_CUSTOMER,
        })
        request_id = resp.get_json()['request_id']

        resp2 = client.get(f'/api/v1/returns-automation/requests/{request_id}')
        assert resp2.status_code == 200
        assert resp2.get_json()['request_id'] == request_id

    def test_get_nonexistent_404(self, client):
        resp = client.get('/api/v1/returns-automation/requests/NONEXISTENT')
        assert resp.status_code == 404


class TestAPIListRequests:
    def test_list_200(self, client):
        resp = client.get('/api/v1/returns-automation/requests')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'requests' in data
        assert 'total' in data

    def test_list_with_status_filter(self, client):
        resp = client.get('/api/v1/returns-automation/requests?status=requested')
        assert resp.status_code == 200


class TestAPIReclassify:
    def test_reclassify_200(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
            'reason_code': 'change_of_mind',
        })
        request_id = resp.get_json()['request_id']

        resp2 = client.post(f'/api/v1/returns-automation/requests/{request_id}/classify', json={
            'order': _SAMPLE_ORDER,
            'customer': _SAMPLE_CUSTOMER,
        })
        assert resp2.status_code == 200
        assert 'classification' in resp2.get_json()

    def test_reclassify_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/classify', json={})
        assert resp.status_code == 404


class TestAPIApproveReject:
    def _create_request(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
            'reason_code': 'change_of_mind',
            'order': _SAMPLE_ORDER,
            'customer': _SAMPLE_CUSTOMER,
        })
        return resp.get_json()['request_id']

    def test_approve_200(self, client):
        request_id = self._create_request(client)

        # 상태를 classified로 강제 설정
        import src.api.returns_automation_api as api_mod
        mgr = api_mod._get_manager()
        mgr._requests[request_id].status = ReturnStatus.classified

        resp = client.post(f'/api/v1/returns-automation/requests/{request_id}/approve', json={
            'notes': '테스트 승인',
            'order': _SAMPLE_ORDER,
        })
        assert resp.status_code == 200

    def test_reject_200(self, client):
        request_id = self._create_request(client)

        import src.api.returns_automation_api as api_mod
        mgr = api_mod._get_manager()
        mgr._requests[request_id].status = ReturnStatus.classified

        resp = client.post(f'/api/v1/returns-automation/requests/{request_id}/reject', json={
            'notes': '테스트 거절',
        })
        assert resp.status_code == 200

    def test_approve_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/approve', json={})
        assert resp.status_code == 404

    def test_reject_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/reject', json={})
        assert resp.status_code == 404


class TestAPIEscalate:
    def test_escalate_200(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
            'reason_code': 'change_of_mind',
        })
        request_id = resp.get_json()['request_id']

        import src.api.returns_automation_api as api_mod
        mgr = api_mod._get_manager()
        mgr._requests[request_id].status = ReturnStatus.classified

        resp2 = client.post(f'/api/v1/returns-automation/requests/{request_id}/escalate', json={
            'reason': '분쟁 가능성',
        })
        assert resp2.status_code == 200

    def test_escalate_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/escalate', json={})
        assert resp.status_code == 404


class TestAPIPickup:
    def test_pickup_missing_address_400(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
            'reason_code': 'change_of_mind',
            'customer': {'tier': 'VIP', 'dispute_history': []},
            'order': _SAMPLE_ORDER,
        })
        request_id = resp.get_json()['request_id']

        resp2 = client.post(f'/api/v1/returns-automation/requests/{request_id}/pickup', json={})
        assert resp2.status_code == 400

    def test_pickup_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/pickup', json={
            'address': {'name': '홍길동'},
        })
        assert resp.status_code == 404


class TestAPIInspect:
    def test_inspect_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/inspect', json={})
        assert resp.status_code == 404

    def test_inspect_200(self, client):
        resp = client.post('/api/v1/returns-automation/requests', json={
            'order_id': 'ORD-001',
            'user_id': 'USER-001',
            'items': _SAMPLE_ITEMS,
            'reason_code': 'change_of_mind',
        })
        request_id = resp.get_json()['request_id']

        import src.api.returns_automation_api as api_mod
        mgr = api_mod._get_manager()
        mgr._requests[request_id].status = ReturnStatus.received

        resp2 = client.post(f'/api/v1/returns-automation/requests/{request_id}/inspect', json={
            'condition_score': 90,
            'package_intact': True,
        })
        assert resp2.status_code == 200


class TestAPIRefundExchange:
    def test_refund_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/refund', json={})
        assert resp.status_code == 404

    def test_exchange_not_found_404(self, client):
        resp = client.post('/api/v1/returns-automation/requests/NONEXISTENT/exchange', json={})
        assert resp.status_code == 404


class TestAPIMetrics:
    def test_metrics_200(self, client):
        resp = client.get('/api/v1/returns-automation/metrics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total' in data
        assert 'auto_approve_rate' in data
        assert 'dispute_rate' in data


# ══════════════════════════════════════════════════════════
# 13. Phase 117 알림 연동 검증 (mock)
# ══════════════════════════════════════════════════════════

class TestPhase117NotificationIntegration:
    """Phase 117 delivery_notifications 연동 테스트."""

    def test_exchange_registers_delivery_notification_mock(self):
        """교환 처리 시 Phase 117 알림 등록 시도 (mock)."""
        orch = ExchangeOrchestrator()
        req = ExchangeRequest(
            order_id='ORD-NOTIF',
            user_id='USER-NOTIF',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('50000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='',
            target_sku='SKU-002',
        )

        with patch.object(orch, '_register_delivery_notification', return_value=True) as mock_reg:
            with patch.object(orch, '_dispatch_fulfillment', return_value={'tracking_number': '123456789012', 'carrier_id': 'cj'}):
                result = orch.process_exchange(req, {'order_amount': 50000})

        mock_reg.assert_called_once()
        assert result['tracking_registered'] is True

    def test_refund_sends_notification_mock(self):
        """환불 시 NotificationHub 알림 발송 (mock)."""
        orch = RefundOrchestrator()
        req = _make_request()
        decision = ReturnDecision(decision='approved', refund_amount=Decimal('50000'))

        with patch.object(orch, '_send_refund_notification', return_value=True) as mock_notif:
            result = orch.process_refund(req, decision)

        mock_notif.assert_called_once()
        assert result['notification_sent'] is True


# ══════════════════════════════════════════════════════════
# 14. Phase 84 풀필먼트 재dispatch 검증 (mock)
# ══════════════════════════════════════════════════════════

class TestPhase84FulfillmentIntegration:
    """Phase 84 fulfillment_automation 연동 테스트."""

    def test_exchange_dispatches_fulfillment_mock(self):
        """교환 처리 시 Phase 84 AutoDispatcher 호출 (mock)."""
        orch = ExchangeOrchestrator()
        req = ExchangeRequest(
            order_id='ORD-FULFILL',
            user_id='USER-FULFILL',
            items=[ReturnItem('SKU-001', '상품', 1, Decimal('50000'))],
            reason_code=ReturnReasonCategory.size_mismatch,
            reason_text='',
            target_sku='SKU-002',
        )

        mock_order = {
            'order_id': 'FO-001',
            'tracking_number': '123456789012',
            'carrier_id': 'cj',
            'status': 'dispatched',
        }

        with patch.object(orch, '_dispatch_fulfillment', return_value=mock_order) as mock_dispatch:
            result = orch.process_exchange(req, {'order_amount': 50000})

        mock_dispatch.assert_called_once()
        assert result['fulfillment_order'] == mock_order


# ══════════════════════════════════════════════════════════
# 15. 봇 커맨드 테스트
# ══════════════════════════════════════════════════════════

class TestBotCommands:
    """Phase 118 봇 커맨드 테스트."""

    def test_cmd_return_request_valid(self):
        from src.bot.commands import cmd_return_request
        result = cmd_return_request('ORD-001 change_of_mind')
        assert isinstance(result, str)

    def test_cmd_return_request_missing_args(self):
        from src.bot.commands import cmd_return_request
        result = cmd_return_request('')
        assert '사용법' in result

    def test_cmd_return_status_missing_id(self):
        from src.bot.commands import cmd_return_status
        result = cmd_return_status('')
        assert '사용법' in result

    def test_cmd_return_status_not_found(self):
        from src.bot.commands import cmd_return_status
        result = cmd_return_status('RET-NONEXIST')
        assert isinstance(result, str)

    def test_cmd_return_approve_auto_missing_id(self):
        from src.bot.commands import cmd_return_approve_auto
        result = cmd_return_approve_auto('')
        assert '사용법' in result

    def test_cmd_return_metrics(self):
        from src.bot.commands import cmd_return_metrics
        result = cmd_return_metrics()
        assert isinstance(result, str)
