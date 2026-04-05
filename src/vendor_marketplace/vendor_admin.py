"""src/vendor_marketplace/vendor_admin.py — 플랫폼 관리자 기능 (Phase 98)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .commission import CommissionCalculator, CommissionRule
from .vendor_models import Vendor, VendorStatus, VendorTier

logger = logging.getLogger(__name__)

# 규정 준수 임계값
COMPLIANCE_THRESHOLDS = {
    'max_return_rate': 0.20,       # 반품률 20% 이상 → 경고
    'min_response_rate': 0.80,     # 응답률 80% 미만 → 경고
    'max_delivery_delay_rate': 0.15,  # 배송 지연률 15% 이상 → 경고
    'auto_suspend_score': 40.0,    # 종합 스코어 40점 미만 → 자동 정지
}


class VendorAdminManager:
    """전체 판매자 관리 — 목록/검색/필터, 심사 대기열, 일괄 처리."""

    def __init__(self, onboarding_manager=None) -> None:
        self._onboarding = onboarding_manager

    def list_vendors(
        self,
        status: Optional[str] = None,
        tier: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[dict]:
        """판매자 목록 조회 (필터링)."""
        if self._onboarding is None:
            return []
        vendors = self._onboarding.list_vendors(status=status, tier=tier)
        if keyword:
            keyword = keyword.lower()
            vendors = [
                v for v in vendors
                if keyword in v.name.lower() or keyword in v.email.lower()
            ]
        return [v.to_dict() for v in vendors]

    def get_review_queue(self) -> List[dict]:
        """심사 대기열 (under_review 상태 판매자)."""
        return self.list_vendors(status=VendorStatus.under_review.value)

    def bulk_approve(self, vendor_ids: List[str]) -> dict:
        """다수 판매자 일괄 승인."""
        if self._onboarding is None:
            return {'approved': [], 'failed': []}
        approved, failed = [], []
        for vid in vendor_ids:
            try:
                self._onboarding.approve(vid)
                approved.append(vid)
            except Exception as exc:
                failed.append({'vendor_id': vid, 'error': str(exc)})
                logger.warning('일괄 승인 실패: %s — %s', vid, exc)
        return {'approved': approved, 'failed': failed}

    def bulk_reject(self, vendor_ids: List[str], reason: str = '') -> dict:
        """다수 판매자 일괄 거절."""
        if self._onboarding is None:
            return {'rejected': [], 'failed': []}
        rejected, failed = [], []
        for vid in vendor_ids:
            try:
                self._onboarding.reject(vid, reason)
                rejected.append(vid)
            except Exception as exc:
                failed.append({'vendor_id': vid, 'error': str(exc)})
        return {'rejected': rejected, 'failed': failed}

    def suspend_vendor(self, vendor_id: str, reason: str = '') -> dict:
        """판매자 정지."""
        if self._onboarding is None:
            raise RuntimeError('onboarding_manager 미설정')
        vendor = self._onboarding.suspend(vendor_id, reason)
        return vendor.to_dict()

    def unsuspend_vendor(self, vendor_id: str) -> dict:
        """판매자 정지 해제 (active 복구)."""
        if self._onboarding is None:
            raise RuntimeError('onboarding_manager 미설정')
        vendor = self._onboarding.activate(vendor_id)
        return vendor.to_dict()


class PlatformFeeManager:
    """플랫폼 수수료 정책 관리."""

    def __init__(self, calculator: Optional[CommissionCalculator] = None) -> None:
        self._calculator = calculator or CommissionCalculator()

    def create_rule(
        self,
        vendor_tier: str,
        rate: float,
        category: str = '',
        min_amount: float = 0.0,
        max_amount: float = float('inf'),
        promotion_rate: Optional[float] = None,
        promotion_until=None,
    ) -> CommissionRule:
        """수수료 규칙 생성."""
        rule = CommissionRule(
            vendor_tier=vendor_tier,
            category=category,
            rate=rate,
            min_amount=min_amount,
            max_amount=max_amount,
            promotion_rate=promotion_rate,
            promotion_until=promotion_until,
        )
        self._calculator.add_rule(rule)
        logger.info('수수료 규칙 생성: %s (tier=%s, category=%s, rate=%.1f%%)',
                    rule.rule_id, vendor_tier, category, rate)
        return rule

    def deactivate_rule(self, rule_id: str) -> bool:
        """수수료 규칙 비활성화."""
        for rule in self._calculator.list_rules(active_only=False):
            if rule.rule_id == rule_id:
                rule.is_active = False
                return True
        return False

    def list_rules(self, active_only: bool = True) -> List[dict]:
        return [r.to_dict() for r in self._calculator.list_rules(active_only=active_only)]

    @property
    def calculator(self) -> CommissionCalculator:
        return self._calculator


class VendorComplianceChecker:
    """판매자 규정 준수 자동 체크."""

    def __init__(self, onboarding_manager=None) -> None:
        self._onboarding = onboarding_manager

    def check(self, vendor_id: str, metrics: dict) -> dict:
        """규정 준수 체크.

        metrics: {
            'return_rate': float,        # 0~1
            'response_rate': float,      # 0~1
            'delivery_delay_rate': float,  # 0~1
            'total_score': float,        # 0~100
        }
        """
        warnings = []
        should_suspend = False

        if metrics.get('return_rate', 0) > COMPLIANCE_THRESHOLDS['max_return_rate']:
            warnings.append(
                f'반품률 초과: {metrics["return_rate"]:.1%} (기준: {COMPLIANCE_THRESHOLDS["max_return_rate"]:.1%})'
            )

        if metrics.get('response_rate', 1) < COMPLIANCE_THRESHOLDS['min_response_rate']:
            warnings.append(
                f'응답률 부족: {metrics["response_rate"]:.1%} (기준: {COMPLIANCE_THRESHOLDS["min_response_rate"]:.1%})'
            )

        if metrics.get('delivery_delay_rate', 0) > COMPLIANCE_THRESHOLDS['max_delivery_delay_rate']:
            warnings.append(
                f'배송 지연률 초과: {metrics["delivery_delay_rate"]:.1%} (기준: {COMPLIANCE_THRESHOLDS["max_delivery_delay_rate"]:.1%})'
            )

        if metrics.get('total_score', 100) < COMPLIANCE_THRESHOLDS['auto_suspend_score']:
            warnings.append(
                f'종합 스코어 부족: {metrics["total_score"]:.1f}점 (기준: {COMPLIANCE_THRESHOLDS["auto_suspend_score"]:.0f}점)'
            )
            should_suspend = True

        if should_suspend and self._onboarding is not None:
            try:
                self._onboarding.suspend(vendor_id, '자동 정지: 규정 준수 기준 미달')
                logger.warning('자동 정지 처리: %s', vendor_id)
            except Exception as exc:
                logger.error('자동 정지 실패: %s — %s', vendor_id, exc)

        return {
            'vendor_id': vendor_id,
            'passed': len(warnings) == 0,
            'warnings': warnings,
            'auto_suspended': should_suspend,
            'checked_at': datetime.now(timezone.utc).isoformat(),
        }
