"""src/returns_automation/return_classifier.py — Phase 118: 반품 자동 분류기.

분류 규칙 (우선순위 순):
  1. 사진 첨부 + damaged_in_transit/defective + 7일 이내 → auto_approve (전액)
  2. 미개봉(change_of_mind) + 14일 이내 + VIP/Gold 고객 → auto_approve (배송비 고객 부담)
  3. 금액 ≥ 300,000원 또는 사진 불충분 + defective → manual_review
  4. 30일 초과 또는 명백한 사용 흔적 → auto_reject
  5. 이전 분쟁 이력 있음 → dispute
  기본: manual_review
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .models import AutoReturnRequest, ReturnClassification, ReturnReasonCategory

logger = logging.getLogger(__name__)

# 자동 승인 금액 상한 (이 이상이면 manual_review)
AUTO_APPROVE_MAX_AMOUNT = 300_000
# 단순 반품 허용 기간 (일)
SIMPLE_RETURN_DAYS = 14
# 자동 거절 기간 초과 (일)
REJECT_DAYS_LIMIT = 30
# 사진 첨부 + 손상/불량 자동 승인 기간 (일)
DAMAGE_AUTO_APPROVE_DAYS = 7
# VIP/Gold 등급 목록
VIP_TIERS = {'VIP', 'Gold', 'vip', 'gold'}


class ReturnClassifier:
    """반품 요청 자동 분류기.

    classify() 메서드로 분류 결과를 반환한다.
    """

    def classify(
        self,
        request: AutoReturnRequest,
        order: Optional[dict] = None,
        customer: Optional[dict] = None,
    ) -> ReturnClassification:
        """반품/교환 요청을 규칙 기반으로 자동 분류한다.

        Args:
            request: 반품/교환 요청 객체
            order: 주문 정보 dict (order_amount, ordered_at 등)
            customer: 고객 정보 dict (tier, dispute_history 등)

        Returns:
            ReturnClassification 분류 결과
        """
        order = order or {}
        customer = customer or {}

        reason = request.reason_code
        if isinstance(reason, str):
            try:
                reason = ReturnReasonCategory(reason)
            except ValueError:
                reason = ReturnReasonCategory.other

        # 요청 경과 일수 계산
        days_since = self._days_since(request.requested_at, order.get('ordered_at'))
        has_photos = bool(request.photos)
        order_amount = int(order.get('order_amount', 0))
        customer_tier = customer.get('tier', '')
        dispute_history = customer.get('dispute_history', [])

        # 규칙 5: 이전 분쟁 이력 또는 분쟁 흔적 있음 → dispute
        if dispute_history:
            logger.info("[분류] %s → dispute (이전 분쟁 이력)", request.request_id)
            return ReturnClassification.dispute

        # 규칙 4: 30일 초과 → auto_reject
        if days_since is not None and days_since > REJECT_DAYS_LIMIT:
            logger.info("[분류] %s → auto_reject (30일 초과: %d일)", request.request_id, days_since)
            return ReturnClassification.auto_reject

        # 규칙 1: 사진 첨부 + damaged_in_transit/defective + 7일 이내 → auto_approve
        if (
            has_photos
            and reason in (ReturnReasonCategory.damaged_in_transit, ReturnReasonCategory.defective)
            and (days_since is None or days_since <= DAMAGE_AUTO_APPROVE_DAYS)
            and order_amount < AUTO_APPROVE_MAX_AMOUNT
        ):
            logger.info("[분류] %s → auto_approve (사진+손상/불량+7일이내)", request.request_id)
            return ReturnClassification.auto_approve

        # 규칙 2: change_of_mind + 14일 이내 + VIP/Gold → auto_approve (배송비 고객 부담)
        if (
            reason == ReturnReasonCategory.change_of_mind
            and (days_since is None or days_since <= SIMPLE_RETURN_DAYS)
            and customer_tier in VIP_TIERS
            and order_amount < AUTO_APPROVE_MAX_AMOUNT
        ):
            logger.info("[분류] %s → auto_approve (변심+VIP+14일이내)", request.request_id)
            return ReturnClassification.auto_approve

        # 규칙 3: 금액 ≥ 30만원 또는 사진 불충분 + defective → manual_review
        if order_amount >= AUTO_APPROVE_MAX_AMOUNT:
            logger.info("[분류] %s → manual_review (고액 주문: %d원)", request.request_id, order_amount)
            return ReturnClassification.manual_review

        if not has_photos and reason == ReturnReasonCategory.defective:
            logger.info("[분류] %s → manual_review (사진 없음+불량)", request.request_id)
            return ReturnClassification.manual_review

        # 기본: manual_review
        logger.info("[분류] %s → manual_review (기본 규칙)", request.request_id)
        return ReturnClassification.manual_review

    # ── 헬퍼 ─────────────────────────────────────────────

    def _days_since(self, requested_at: str, ordered_at: Optional[str]) -> Optional[int]:
        """주문일 기준 경과 일수 계산. ordered_at이 없으면 None 반환."""
        if not ordered_at:
            return None
        try:
            order_dt = datetime.fromisoformat(ordered_at.replace('Z', '+00:00'))
            # ordered_at 기준 요청일까지의 경과 일수
            req_dt = datetime.fromisoformat(requested_at.replace('Z', '+00:00'))
            delta = req_dt - order_dt
            return max(0, delta.days)
        except Exception as exc:
            logger.warning("날짜 파싱 실패: %s", exc)
            return None
