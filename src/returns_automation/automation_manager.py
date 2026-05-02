"""src/returns_automation/automation_manager.py — Phase 118: 반품/교환 자동화 통합 오케스트레이터.

입구점. 요청 접수 → 분류 → 자동 처리 → 외부 이벤트 진행 → 메트릭 제공.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from .models import (
    AutoReturnRequest,
    ExchangeRequest,
    ReturnClassification,
    ReturnDecision,
    ReturnItem,
    ReturnReasonCategory,
    ReturnStatus,
)
from .auto_approval_engine import AutoApprovalEngine
from .escalation_router import EscalationRouter
from .exchange_orchestrator import ExchangeOrchestrator
from .inspection_orchestrator import InspectionOrchestrator
from .refund_orchestrator import RefundOrchestrator
from .return_classifier import ReturnClassifier
from .reverse_logistics import ReverseLogisticsManager
from .workflow_definition import ReturnsAutomationWorkflow

logger = logging.getLogger(__name__)


class ReturnsAutomationManager:
    """반품/교환 자동 처리 통합 오케스트레이터.

    모든 반품/교환 처리의 입구점.
    """

    def __init__(self) -> None:
        self._requests: Dict[str, AutoReturnRequest] = {}
        self._classifier = ReturnClassifier()
        self._approval_engine = AutoApprovalEngine()
        self._reverse_logistics = ReverseLogisticsManager()
        self._inspection = InspectionOrchestrator()
        self._refund = RefundOrchestrator()
        self._exchange = ExchangeOrchestrator()
        self._escalation = EscalationRouter()
        self._workflow = ReturnsAutomationWorkflow()
        # 메트릭 카운터
        self._total = 0
        self._auto_approved = 0
        self._auto_rejected = 0
        self._disputed = 0
        self._processing_times: List[float] = []

    def submit_request(
        self,
        order_id: str,
        user_id: str,
        items: List[dict],
        reason_code: str,
        reason_text: str = '',
        photos: Optional[List[str]] = None,
        order: Optional[dict] = None,
        customer: Optional[dict] = None,
        request_type: str = 'return',
        target_sku: str = '',
        target_option: str = '',
    ) -> AutoReturnRequest:
        """반품/교환 요청 접수 + 자동 분류 + 자동 처리.

        Args:
            order_id: 주문 ID
            user_id: 고객 ID
            items: 반품 상품 목록 [{'sku', 'product_name', 'quantity', 'unit_price'}]
            reason_code: 반품 사유 코드 (ReturnReasonCategory 값)
            reason_text: 반품 사유 텍스트
            photos: 사진 URL 목록
            order: 주문 정보 dict
            customer: 고객 정보 dict
            request_type: 'return' 또는 'exchange'
            target_sku: 교환 대상 SKU (교환 요청 시)
            target_option: 교환 대상 옵션 (교환 요청 시)

        Returns:
            처리된 AutoReturnRequest 또는 ExchangeRequest 객체
        """
        start_time = datetime.now(timezone.utc)
        self._total += 1

        # 아이템 변환
        return_items = []
        for it in items:
            return_items.append(ReturnItem(
                sku=it.get('sku', ''),
                product_name=it.get('product_name', ''),
                quantity=int(it.get('quantity', 1)),
                unit_price=Decimal(str(it.get('unit_price', 0))),
                order_item_id=it.get('order_item_id', ''),
            ))

        # 요청 객체 생성
        try:
            reason_enum = ReturnReasonCategory(reason_code)
        except ValueError:
            reason_enum = ReturnReasonCategory.other

        if request_type == 'exchange':
            req: AutoReturnRequest = ExchangeRequest(
                order_id=order_id,
                user_id=user_id,
                items=return_items,
                reason_code=reason_enum,
                reason_text=reason_text,
                photos=photos or [],
                target_sku=target_sku,
                target_option=target_option,
            )
        else:
            req = AutoReturnRequest(
                order_id=order_id,
                user_id=user_id,
                items=return_items,
                reason_code=reason_enum,
                reason_text=reason_text,
                photos=photos or [],
            )

        self._requests[req.request_id] = req
        logger.info("[매니저] 요청 접수: %s (유형: %s)", req.request_id, request_type)

        # 1. 자동 분류
        order = order or {}
        customer = customer or {}
        classification = self._classifier.classify(req, order, customer)
        req.classification = classification
        req.status = ReturnStatus.classified

        # 2. 분류 결과에 따른 자동 처리
        if classification == ReturnClassification.auto_approve:
            self._auto_approve(req, order, customer)
        elif classification == ReturnClassification.auto_reject:
            self._auto_reject(req)
        elif classification == ReturnClassification.dispute:
            self._escalate(req)
        else:
            # manual_review — 대기 상태 유지
            logger.info("[매니저] %s → 수동 검토 대기", req.request_id)

        # 처리 시간 기록
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._processing_times.append(elapsed)

        return req

    def progress(self, request_id: str, event: str, payload: Optional[dict] = None) -> AutoReturnRequest:
        """외부 이벤트로 요청 상태를 진행시킨다.

        지원 이벤트:
          - pickup_scheduled: 픽업 예약 완료
          - in_return_transit: 반품 운송 시작
          - received: 반품 상품 수령
          - inspected: 검수 완료 (payload: grade, refund_amount)
          - refunded: 환불 완료
          - exchanged: 교환 완료

        Args:
            request_id: 요청 ID
            event: 이벤트명
            payload: 이벤트 데이터

        Returns:
            업데이트된 요청 객체
        """
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')

        payload = payload or {}
        event_to_status = {
            'pickup_scheduled': ReturnStatus.pickup_scheduled,
            'in_return_transit': ReturnStatus.in_return_transit,
            'received': ReturnStatus.received,
            'inspected': ReturnStatus.inspected,
            'refunded': ReturnStatus.refunded,
            'exchanged': ReturnStatus.exchanged,
            'partially_refunded': ReturnStatus.partially_refunded,
        }

        new_status = event_to_status.get(event)
        if new_status:
            req.status = self._workflow.transition(req.status, new_status, notes=event)

        if event == 'inspected' and payload.get('grade'):
            req.inspection_grade = payload['grade']

        logger.info("[매니저] %s 이벤트: %s → 상태: %s", request_id, event, req.status.value)
        return req

    def approve(
        self,
        request_id: str,
        notes: str = '',
        order: Optional[dict] = None,
        customer: Optional[dict] = None,
    ) -> AutoReturnRequest:
        """수동 승인 처리."""
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')
        order = order or {}
        customer = customer or {}
        self._auto_approve(req, order, customer, notes=notes)
        return req

    def reject(self, request_id: str, notes: str = '') -> AutoReturnRequest:
        """수동 거절 처리."""
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')
        self._auto_reject(req, notes=notes)
        return req

    def escalate(self, request_id: str, reason: str = '') -> AutoReturnRequest:
        """수동 분쟁 에스컬레이션."""
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')
        self._escalate(req, reason=reason)
        return req

    def schedule_pickup(
        self,
        request_id: str,
        address: dict,
        carrier: str = 'cj',
    ) -> dict:
        """회수 픽업 예약."""
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')

        waybill = self._reverse_logistics.issue_return_waybill(req, carrier)
        pickup = self._reverse_logistics.schedule_pickup(req, address, carrier)

        req.waybill_no = waybill['waybill_no']
        req.carrier = carrier
        req.status = self._workflow.transition(req.status, ReturnStatus.pickup_scheduled)

        return {'waybill': waybill, 'pickup': pickup}

    def process_inspection(
        self,
        request_id: str,
        condition_score: int = 90,
        package_intact: bool = True,
        functional: bool = True,
        notes: str = '',
    ) -> dict:
        """검수 처리."""
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')

        result = self._inspection.inspect(
            req, condition_score, package_intact, functional, notes=notes
        )
        req.inspection_grade = result.get('grade', '')

        if req.status == ReturnStatus.received:
            req.status = self._workflow.transition(req.status, ReturnStatus.inspected)

        return result

    def process_refund_for_request(
        self,
        request_id: str,
        order: Optional[dict] = None,
    ) -> dict:
        """환불 처리."""
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')
        order = order or {}

        if req.decision is None:
            amount = Decimal(str(order.get('order_amount', 0)))
            req.decision = ReturnDecision(
                decision='approved',
                refund_amount=amount,
                notes='수동 환불 처리',
            )

        result = self._refund.process_refund(req, req.decision)
        if req.status == ReturnStatus.inspected:
            req.status = self._workflow.transition(req.status, ReturnStatus.refunded)
        return result

    def process_exchange_for_request(
        self,
        request_id: str,
        order: Optional[dict] = None,
    ) -> dict:
        """교환 처리."""
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f'요청을 찾을 수 없습니다: {request_id}')

        result = self._exchange.process_exchange(req, order or {})
        if req.status in (ReturnStatus.inspected, ReturnStatus.approved):
            if result.get('fallback_refund'):
                try:
                    req.status = self._workflow.transition(req.status, ReturnStatus.refunded)
                except ValueError:
                    pass
            else:
                try:
                    req.status = self._workflow.transition(req.status, ReturnStatus.exchanged)
                except ValueError:
                    pass
        return result

    def get_status(self, request_id: str) -> Optional[dict]:
        """요청 상태 조회."""
        req = self._requests.get(request_id)
        if req is None:
            return None
        return req.to_dict()

    def list_pending(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[dict]:
        """대기 중인 요청 목록 조회.

        Args:
            status: 상태 필터 (ReturnStatus 값)
            user_id: 고객 ID 필터
        """
        items = list(self._requests.values())
        if status:
            items = [r for r in items if r.status.value == status]
        if user_id:
            items = [r for r in items if r.user_id == user_id]
        return [r.to_dict() for r in items]

    def metrics(self) -> dict:
        """자동화 메트릭 반환.

        Returns:
            dict with auto_approve_rate, avg_processing_time_sec, dispute_rate
        """
        if self._total == 0:
            return {
                'total': 0,
                'auto_approved': 0,
                'auto_rejected': 0,
                'disputed': 0,
                'manual_review': 0,
                'auto_approve_rate': 0.0,
                'dispute_rate': 0.0,
                'avg_processing_time_sec': 0.0,
            }

        manual = self._total - self._auto_approved - self._auto_rejected - self._disputed
        avg_time = sum(self._processing_times) / len(self._processing_times) if self._processing_times else 0.0

        return {
            'total': self._total,
            'auto_approved': self._auto_approved,
            'auto_rejected': self._auto_rejected,
            'disputed': self._disputed,
            'manual_review': max(0, manual),
            'auto_approve_rate': round(self._auto_approved / self._total, 4),
            'dispute_rate': round(self._disputed / self._total, 4),
            'avg_processing_time_sec': round(avg_time, 4),
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────

    def _auto_approve(
        self,
        req: AutoReturnRequest,
        order: dict,
        customer: dict,
        notes: str = '',
    ) -> None:
        """자동 승인 처리."""
        decision = self._approval_engine.evaluate(req, order, customer)
        if notes:
            decision.notes = notes or decision.notes
        req.decision = decision

        if decision.decision == 'rejected':
            req.status = self._workflow.transition(req.status, ReturnStatus.rejected)
            self._auto_rejected += 1
        else:
            req.status = self._workflow.transition(req.status, ReturnStatus.approved)
            self._auto_approved += 1
            logger.info("[매니저] %s 자동 승인: 환불액 %s원", req.request_id, decision.refund_amount)

    def _auto_reject(self, req: AutoReturnRequest, notes: str = '') -> None:
        """자동 거절 처리."""
        req.decision = ReturnDecision(
            decision='rejected',
            notes=notes or '자동 거절',
        )
        req.status = self._workflow.transition(req.status, ReturnStatus.rejected)
        self._auto_rejected += 1
        logger.info("[매니저] %s 자동 거절", req.request_id)

    def _escalate(self, req: AutoReturnRequest, reason: str = '') -> None:
        """분쟁 에스컬레이션."""
        self._escalation.escalate_to_dispute(req, reason=reason or req.reason_text)
        req.status = self._workflow.transition(req.status, ReturnStatus.disputed)
        self._disputed += 1
        logger.info("[매니저] %s 분쟁 에스컬레이션", req.request_id)
