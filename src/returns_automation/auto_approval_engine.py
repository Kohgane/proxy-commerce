"""src/returns_automation/auto_approval_engine.py — Phase 118: 자동 승인 규칙 엔진.

ABC `ApprovalRule` + 5가지 구체 규칙:
  - AmountThresholdRule : 금액 기준 자동 승인
  - ReasonBasedRule     : 사유 기반 자동 승인
  - CustomerTierRule    : VIP/Gold 등급 우대
  - TimeWindowRule      : 구매 후 N일 이내 자동 승인
  - BlacklistRule       : 악성 환불 이력 차단
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from .models import AutoReturnRequest, ReturnDecision, ReturnReasonCategory

logger = logging.getLogger(__name__)

# 자동 승인 금액 상한 (원)
DEFAULT_AMOUNT_THRESHOLD = 100_000
# 단순 변심 자동 승인 허용 일수
CHANGE_OF_MIND_DAYS = 14
# VIP/Gold 단순 변심 자동 승인 허용 일수
VIP_CHANGE_OF_MIND_DAYS = 30


class ApprovalRule(ABC):
    """자동 승인 규칙 추상 기반 클래스."""

    @abstractmethod
    def evaluate(
        self,
        request: AutoReturnRequest,
        order: dict,
        customer: dict,
    ) -> Optional[ReturnDecision]:
        """규칙을 평가한다.

        Returns:
            ReturnDecision: 규칙에 해당하면 결정 반환
            None: 해당 없으면 None (다음 규칙으로 넘김)
        """

    @property
    @abstractmethod
    def priority(self) -> int:
        """낮을수록 먼저 평가됨."""


class AmountThresholdRule(ApprovalRule):
    """금액 기준 자동 승인 규칙.

    주문 금액이 임계값 미만이면 자동 승인.
    """

    def __init__(self, threshold: int = DEFAULT_AMOUNT_THRESHOLD) -> None:
        self.threshold = threshold

    @property
    def priority(self) -> int:
        return 10

    def evaluate(
        self,
        request: AutoReturnRequest,
        order: dict,
        customer: dict,
    ) -> Optional[ReturnDecision]:
        """금액 임계값 이하면 자동 승인."""
        amount = int(order.get('order_amount', 0))
        if amount < self.threshold:
            return ReturnDecision(
                decision='approved',
                refund_amount=Decimal(str(amount)),
                notes=f'금액 임계값({self.threshold:,}원) 미만 자동 승인',
            )
        return None


class ReasonBasedRule(ApprovalRule):
    """사유 기반 자동 승인 규칙.

    wrong_item/defective/damaged_in_transit 사유는 판매자 귀책으로 자동 승인.
    """

    # 판매자 귀책 사유 목록
    SELLER_FAULT_REASONS = {
        ReturnReasonCategory.wrong_item,
        ReturnReasonCategory.defective,
        ReturnReasonCategory.damaged_in_transit,
        ReturnReasonCategory.not_as_described,
    }

    @property
    def priority(self) -> int:
        return 20

    def evaluate(
        self,
        request: AutoReturnRequest,
        order: dict,
        customer: dict,
    ) -> Optional[ReturnDecision]:
        """판매자 귀책 사유는 배송비 판매자 부담으로 자동 승인."""
        reason = request.reason_code
        if isinstance(reason, str):
            try:
                reason = ReturnReasonCategory(reason)
            except ValueError:
                return None

        if reason in self.SELLER_FAULT_REASONS and request.photos:
            amount = Decimal(str(order.get('order_amount', 0)))
            return ReturnDecision(
                decision='approved',
                refund_amount=amount,
                shipping_fee_borne_by='seller',
                notes=f'판매자 귀책 사유({reason.value}) 자동 승인',
            )
        return None


class CustomerTierRule(ApprovalRule):
    """고객 등급 우대 규칙.

    VIP/Gold 등급 고객은 변심 반품도 자동 승인 (배송비 고객 부담).
    """

    VIP_TIERS = {'VIP', 'Gold', 'vip', 'gold'}

    @property
    def priority(self) -> int:
        return 30

    def evaluate(
        self,
        request: AutoReturnRequest,
        order: dict,
        customer: dict,
    ) -> Optional[ReturnDecision]:
        """VIP/Gold 고객의 변심 반품 자동 승인."""
        tier = customer.get('tier', '')
        reason = request.reason_code
        if isinstance(reason, str):
            try:
                reason = ReturnReasonCategory(reason)
            except ValueError:
                return None

        if tier in self.VIP_TIERS and reason == ReturnReasonCategory.change_of_mind:
            amount = Decimal(str(order.get('order_amount', 0)))
            shipping_fee = Decimal(str(order.get('shipping_fee', 3000)))
            return ReturnDecision(
                decision='approved',
                refund_amount=amount,
                restocking_fee=Decimal('0'),
                shipping_fee_borne_by='customer',
                notes=f'VIP/Gold 등급({tier}) 변심 반품 자동 승인 — 반품 배송비 고객 부담',
            )
        return None


class TimeWindowRule(ApprovalRule):
    """구매 후 N일 이내 자동 승인 규칙."""

    def __init__(self, days: int = 7) -> None:
        self.days = days

    @property
    def priority(self) -> int:
        return 40

    def evaluate(
        self,
        request: AutoReturnRequest,
        order: dict,
        customer: dict,
    ) -> Optional[ReturnDecision]:
        """구매 후 N일 이내이고 사진이 있으면 자동 승인."""
        ordered_at = order.get('ordered_at')
        if not ordered_at:
            return None
        try:
            order_dt = datetime.fromisoformat(ordered_at.replace('Z', '+00:00'))
            req_dt = datetime.fromisoformat(request.requested_at.replace('Z', '+00:00'))
            days_elapsed = (req_dt - order_dt).days
        except Exception:
            return None

        if days_elapsed <= self.days and request.photos:
            amount = Decimal(str(order.get('order_amount', 0)))
            return ReturnDecision(
                decision='approved',
                refund_amount=amount,
                notes=f'구매 후 {days_elapsed}일 이내({self.days}일 기준) + 사진 첨부 자동 승인',
            )
        return None


class BlacklistRule(ApprovalRule):
    """악성 환불 이력 차단 규칙.

    블랙리스트에 등록된 고객은 자동 거절.
    """

    @property
    def priority(self) -> int:
        return 5  # 가장 먼저 평가

    def evaluate(
        self,
        request: AutoReturnRequest,
        order: dict,
        customer: dict,
    ) -> Optional[ReturnDecision]:
        """블랙리스트 고객 자동 거절."""
        blacklisted = customer.get('blacklisted', False)
        abuse_count = int(customer.get('return_abuse_count', 0))

        if blacklisted or abuse_count >= 3:
            return ReturnDecision(
                decision='rejected',
                refund_amount=Decimal('0'),
                notes=f'악성 환불 이력 차단 (blacklisted={blacklisted}, abuse_count={abuse_count})',
            )
        return None


class AutoApprovalEngine:
    """자동 승인 규칙 엔진.

    등록된 규칙을 우선순위 순으로 평가하여 첫 번째 매칭 결정을 반환한다.
    """

    def __init__(self, rules: Optional[List[ApprovalRule]] = None) -> None:
        if rules is None:
            # 기본 규칙 세트
            rules = [
                BlacklistRule(),
                AmountThresholdRule(),
                ReasonBasedRule(),
                CustomerTierRule(),
                TimeWindowRule(days=7),
            ]
        # 우선순위 오름차순 정렬
        self._rules: List[ApprovalRule] = sorted(rules, key=lambda r: r.priority)

    def evaluate(
        self,
        request: AutoReturnRequest,
        order: Optional[dict] = None,
        customer: Optional[dict] = None,
    ) -> ReturnDecision:
        """등록된 규칙을 순서대로 평가하여 결정을 반환한다.

        모든 규칙에 해당하지 않으면 manual_review 결정 반환.
        """
        order = order or {}
        customer = customer or {}

        for rule in self._rules:
            try:
                decision = rule.evaluate(request, order, customer)
                if decision is not None:
                    logger.info(
                        "[승인엔진] %s → %s (%s)",
                        request.request_id,
                        decision.decision,
                        type(rule).__name__,
                    )
                    return decision
            except Exception as exc:
                logger.error("[승인엔진] 규칙 평가 오류 (%s): %s", type(rule).__name__, exc)

        # 기본: 수동 검토
        return ReturnDecision(
            decision='manual_review',
            notes='자동 승인 규칙 미해당 — 수동 검토 필요',
        )
