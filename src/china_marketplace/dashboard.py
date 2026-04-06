"""src/china_marketplace/dashboard.py — 중국 구매 대시보드 (Phase 104)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from .engine import ChinaMarketplaceEngine
    from .agent_manager import AgentManager
    from .seller_verification import SellerVerificationService
    from .payment import ChinaPaymentService
    from .rpa_controller import RPAController

logger = logging.getLogger(__name__)


class ChinaPurchaseDashboard:
    """중국 구매 대시보드 — 주문현황/에이전트성과/셀러분포/비용추이."""

    def __init__(
        self,
        engine: 'ChinaMarketplaceEngine',
        agent_manager: 'AgentManager',
        seller_service: 'SellerVerificationService',
        payment_service: 'ChinaPaymentService',
        rpa_controller: 'RPAController',
    ):
        self._engine = engine
        self._agent_manager = agent_manager
        self._seller_service = seller_service
        self._payment_service = payment_service
        self._rpa_controller = rpa_controller

    def get_summary(self) -> Dict:
        """전체 요약 대시보드 데이터."""
        order_stats = self._engine.get_stats()
        agent_stats = self._agent_manager.get_performance_stats()
        seller_stats = self._seller_service.get_stats()
        payment_stats = self._payment_service.get_stats()
        rpa_stats = self._rpa_controller.get_stats()

        return {
            'orders': order_stats,
            'agents': {
                'total': agent_stats.get('total', 0),
                'active': agent_stats.get('active', 0),
            },
            'sellers': seller_stats,
            'payments': {
                'total_records': payment_stats.get('total_records', 0),
                'total_amount_cny': payment_stats.get('total_amount_cny', 0),
                'total_amount_krw': payment_stats.get('total_amount_krw', 0),
            },
            'rpa': {
                'total_tasks': rpa_stats.get('total', 0),
                'success_rate': rpa_stats.get('success_rate', 0),
            },
        }

    def get_order_status_chart(self) -> Dict:
        """주문 상태별 차트 데이터 (마켓플레이스별/상태별)."""
        orders = self._engine.list_orders()
        taobao = [o for o in orders if o.marketplace == 'taobao']
        alibaba = [o for o in orders if o.marketplace == '1688']

        def count_by_status(order_list):
            counts: Dict[str, int] = {}
            for o in order_list:
                counts[o.status.value] = counts.get(o.status.value, 0) + 1
            return counts

        return {
            'taobao': {
                'total': len(taobao),
                'by_status': count_by_status(taobao),
            },
            '1688': {
                'total': len(alibaba),
                'by_status': count_by_status(alibaba),
            },
        }

    def get_agent_performance(self) -> Dict:
        """에이전트 성과 통계."""
        return self._agent_manager.get_performance_stats()

    def get_seller_distribution(self) -> Dict:
        """셀러 신뢰도 분포."""
        return self._seller_service.get_stats()

    def get_payment_stats(self) -> Dict:
        """결제/비용 통계."""
        stats = self._payment_service.get_stats()
        exchange = self._payment_service.get_exchange_rate()
        limits = self._payment_service.get_limit_status()
        return {
            'payment_stats': stats,
            'exchange_rate': exchange,
            'limits': limits,
        }

    def get_rpa_stats(self) -> Dict:
        """RPA 실행 통계."""
        return self._rpa_controller.get_stats()
