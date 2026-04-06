"""src/exception_handler/dashboard.py — 예외 처리 대시보드 (Phase 105)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from .engine import ExceptionEngine
    from .damage_handler import DamageHandler
    from .price_detector import PriceChangeDetector
    from .retry_manager import RetryManager
    from .auto_recovery import AutoRecoveryService
    from .delay_handler import DeliveryDelayHandler
    from .payment_failure import PaymentFailureHandler

logger = logging.getLogger(__name__)


class ExceptionDashboard:
    """실시간 예외 현황 대시보드."""

    def __init__(
        self,
        engine: Optional['ExceptionEngine'] = None,
        damage_handler: Optional['DamageHandler'] = None,
        price_detector: Optional['PriceChangeDetector'] = None,
        retry_manager: Optional['RetryManager'] = None,
        recovery_service: Optional['AutoRecoveryService'] = None,
        delay_handler: Optional['DeliveryDelayHandler'] = None,
        payment_handler: Optional['PaymentFailureHandler'] = None,
    ) -> None:
        self.engine = engine
        self.damage_handler = damage_handler
        self.price_detector = price_detector
        self.retry_manager = retry_manager
        self.recovery_service = recovery_service
        self.delay_handler = delay_handler
        self.payment_handler = payment_handler

    def get_summary(self) -> Dict:
        summary: Dict = {}

        if self.engine:
            summary['exceptions'] = self.engine.get_stats()

        if self.damage_handler:
            summary['damage'] = self.damage_handler.get_stats()

        if self.price_detector:
            alerts = self.price_detector.list_alerts()
            summary['price_alerts'] = {
                'total': len(alerts),
                'unacknowledged': sum(1 for a in alerts if not a.acknowledged),
            }

        if self.retry_manager:
            summary['retries'] = self.retry_manager.get_stats()

        if self.recovery_service:
            summary['recovery'] = self.recovery_service.get_stats()

        if self.delay_handler:
            summary['delivery_delays'] = self.delay_handler.get_stats()

        if self.payment_handler:
            summary['payment_failures'] = self.payment_handler.get_stats()

        return summary

    def get_exception_trend(self) -> Dict:
        """예외 발생 추이 (주별/월별) — mock 구현."""
        return {
            'weekly': {
                'this_week': 12,
                'last_week': 18,
                'change_pct': -33.3,
            },
            'monthly': {
                'this_month': 45,
                'last_month': 62,
                'change_pct': -27.4,
            },
        }

    def get_cost_impact(self) -> Dict:
        """비용 영향 분석."""
        total_damage_comp = 0.0
        total_recovery_cost = 0.0
        total_payment_affected = 0.0

        if self.damage_handler:
            stats = self.damage_handler.get_stats()
            total_damage_comp = stats.get('total_compensation', 0.0)

        if self.recovery_service:
            stats = self.recovery_service.get_stats()
            total_recovery_cost = stats.get('total_cost', 0.0)

        if self.payment_handler:
            stats = self.payment_handler.get_stats()
            total_payment_affected = stats.get('total_amount_affected', 0.0)

        return {
            'damage_compensation': total_damage_comp,
            'recovery_cost': total_recovery_cost,
            'payment_amount_affected': total_payment_affected,
            'total_impact': total_damage_comp + total_recovery_cost,
        }

    def get_resolution_metrics(self) -> Dict:
        """복구 성공률 및 평균 해결 시간 (mock)."""
        recovery_rate = 0.0
        if self.recovery_service:
            stats = self.recovery_service.get_stats()
            recovery_rate = stats.get('success_rate', 0.0)

        return {
            'auto_recovery_rate': recovery_rate,
            'avg_resolution_hours': 2.5,  # mock
            'escalation_rate': 0.08,       # mock
        }
