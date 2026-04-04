"""src/auto_purchase/purchase_engine.py — 자동 구매 오케스트레이터 (Phase 96)."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .marketplace_buyer import AmazonBuyer, AlibabaBuyer, MarketplaceBuyer, TaobaoBuyer
from .payment_automator import PaymentAutomator
from .purchase_models import Priority, PurchaseOrder, PurchaseResult, PurchaseStatus
from .purchase_monitor import PurchaseMonitor
from .purchase_rules import PurchaseRuleEngine, RuleContext
from .source_selector import SelectionStrategy, SourceSelector

logger = logging.getLogger(__name__)

# 동시 구매 최대 수 (rate limiting)
_MAX_CONCURRENT_PURCHASES = 5

# 지수 백오프 기저 시간 (초)
_RETRY_BASE_DELAY = 2.0


class AutoPurchaseEngine:
    """자동 구매 오케스트레이터.

    주문 접수 → 규칙 평가 → 소스 선택 → 자동 구매 → 결제 → 확인 전체 플로우 관리.

    구매 큐:
        urgent  — 즉시 처리
        normal  — 일반 처리
        low     — 대기 처리
    """

    def __init__(
        self,
        source_selector: SourceSelector = None,
        rule_engine: PurchaseRuleEngine = None,
        payment_automator: PaymentAutomator = None,
        monitor: PurchaseMonitor = None,
    ) -> None:
        self._selector = source_selector or SourceSelector()
        self._rules = rule_engine or PurchaseRuleEngine()
        self._payment = payment_automator or PaymentAutomator()
        self._monitor = monitor or PurchaseMonitor()

        # 마켓플레이스 구매자 레지스트리
        self._buyers: Dict[str, MarketplaceBuyer] = {
            'amazon_us': AmazonBuyer(region='US'),
            'amazon_jp': AmazonBuyer(region='JP'),
            'taobao': TaobaoBuyer(),
            'alibaba_1688': AlibabaBuyer(),
        }

        # 우선순위 큐 (dict of list)
        self._queues: Dict[str, List[PurchaseOrder]] = {
            Priority.URGENT: [],
            Priority.NORMAL: [],
            Priority.LOW: [],
        }

        # 진행 중인 구매 (order_id → PurchaseOrder)
        self._active: Dict[str, PurchaseOrder] = {}
        self._history: Dict[str, PurchaseOrder] = {}

    # ── 공개 API ──────────────────────────────────────────────────────────

    def submit_order(
        self,
        source_product_id: str,
        marketplace: str,
        quantity: int = 1,
        unit_price: float = 0.0,
        currency: str = 'USD',
        selling_price: float = 0.0,
        customer_order_id: str = '',
        shipping_address: Dict = None,
        priority: str = Priority.NORMAL,
    ) -> PurchaseOrder:
        """주문을 접수하고 큐에 추가한다."""
        order = PurchaseOrder(
            source_marketplace=marketplace,
            source_product_id=source_product_id,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            customer_order_id=customer_order_id,
            shipping_address=shipping_address or {},
            priority=Priority(priority),
            metadata={'selling_price': selling_price},
        )

        # 규칙 평가
        context = RuleContext(
            product_id=source_product_id,
            marketplace=marketplace,
            unit_price=unit_price,
            currency=currency,
            quantity=quantity,
            selling_price=selling_price,
        )
        rule_result = self._rules.evaluate(context)
        order.metadata['rule_decision'] = rule_result['decision']

        if rule_result['decision'] == 'reject':
            order.update_status(PurchaseStatus.FAILED, '; '.join(rule_result['reject_reasons']))
            self._history[order.order_id] = order
            self._monitor.register_order(order)
            self._monitor.update_order(order)
            logger.warning('Order rejected by rules: %s', order.order_id)
            return order

        if rule_result['decision'] == 'hold':
            order.update_status(PurchaseStatus.ON_HOLD, '; '.join(rule_result['hold_reasons']))
            self._history[order.order_id] = order
            self._monitor.register_order(order)
            logger.info('Order on hold: %s', order.order_id)
            return order

        # 큐에 추가
        queue_name = priority if priority in self._queues else Priority.NORMAL
        self._queues[queue_name].append(order)
        self._monitor.register_order(order)
        logger.info('Order queued [%s]: %s', priority, order.order_id)
        return order

    def process_order(self, order: PurchaseOrder) -> PurchaseResult:
        """단일 주문을 처리한다 (큐 외부에서 직접 호출 가능)."""
        if len(self._active) >= _MAX_CONCURRENT_PURCHASES:
            order.update_status(PurchaseStatus.ON_HOLD, '동시 구매 한도 초과 — 대기 중')
            logger.warning('Max concurrent purchases reached, order on hold: %s', order.order_id)
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message='동시 구매 한도 초과',
            )

        self._active[order.order_id] = order
        start_time = time.time()

        try:
            result = self._execute_with_retry(order)
        finally:
            self._active.pop(order.order_id, None)
            elapsed = time.time() - start_time
            logger.debug('Order %s completed in %.2fs', order.order_id, elapsed)

        return result

    def process_queue(self, max_items: int = 10) -> List[PurchaseResult]:
        """큐에서 주문을 꺼내 순서대로 처리한다."""
        results = []
        processed = 0
        for priority in [Priority.URGENT, Priority.NORMAL, Priority.LOW]:
            while self._queues[priority] and processed < max_items:
                order = self._queues[priority].pop(0)
                result = self.process_order(order)
                results.append(result)
                processed += 1
        return results

    def cancel_order(self, order_id: str) -> bool:
        """진행 중이거나 큐에 있는 주문을 취소한다."""
        # 큐에서 제거
        for queue in self._queues.values():
            for i, order in enumerate(queue):
                if order.order_id == order_id:
                    queue.pop(i)
                    order.update_status(PurchaseStatus.CANCELLED)
                    self._history[order_id] = order
                    self._monitor.update_order(order)
                    logger.info('Order cancelled from queue: %s', order_id)
                    return True

        # 마켓플레이스에서 취소 시도
        order = self._history.get(order_id) or self._active.get(order_id)
        if order and order.confirmation_code:
            buyer = self._buyers.get(order.source_marketplace)
            if buyer:
                cancelled = buyer.cancel_order(order.confirmation_code)
                if cancelled:
                    order.update_status(PurchaseStatus.CANCELLED)
                    self._monitor.update_order(order)
                    return True
        return False

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """주문 상태를 조회한다."""
        order = (
            self._active.get(order_id)
            or self._history.get(order_id)
            or self._monitor.get_order(order_id)
        )
        if not order:
            return None
        return {
            'order_id': order.order_id,
            'status': order.status.value,
            'marketplace': order.source_marketplace,
            'product_id': order.source_product_id,
            'quantity': order.quantity,
            'unit_price': order.unit_price,
            'currency': order.currency,
            'tracking_number': order.tracking_number,
            'confirmation_code': order.confirmation_code,
            'error_message': order.error_message,
            'created_at': order.created_at.isoformat(),
            'updated_at': order.updated_at.isoformat(),
            'rule_decision': order.metadata.get('rule_decision', ''),
        }

    def get_queue_status(self) -> Dict:
        """현재 큐 현황을 반환한다."""
        return {
            'urgent': len(self._queues[Priority.URGENT]),
            'normal': len(self._queues[Priority.NORMAL]),
            'low': len(self._queues[Priority.LOW]),
            'active': len(self._active),
            'total_queued': sum(len(q) for q in self._queues.values()),
        }

    def get_metrics(self) -> Dict:
        return self._monitor.get_metrics()

    def simulate(
        self,
        source_product_id: str,
        marketplace: str,
        quantity: int = 1,
        unit_price: float = 0.0,
        currency: str = 'USD',
        selling_price: float = 0.0,
        strategy: str = SelectionStrategy.BALANCED,
    ) -> Dict:
        """실제 구매 없이 플로우를 시뮬레이션한다."""
        buyer = self._buyers.get(marketplace)
        availability = {}
        if buyer:
            availability = buyer.check_availability(source_product_id)

        context = RuleContext(
            product_id=source_product_id,
            marketplace=marketplace,
            unit_price=unit_price,
            currency=currency,
            quantity=quantity,
            selling_price=selling_price,
        )
        rule_result = self._rules.evaluate(context)

        payment_method = self._payment.select_method(marketplace, unit_price * quantity, currency)

        return {
            'product_id': source_product_id,
            'marketplace': marketplace,
            'quantity': quantity,
            'unit_price': unit_price,
            'currency': currency,
            'availability': availability,
            'rule_decision': rule_result['decision'],
            'rule_results': [
                {'name': r.rule_name, 'decision': r.decision, 'reason': r.reason}
                for r in rule_result['results']
            ],
            'payment_method': payment_method.type if payment_method else None,
            'estimated_total_cost': unit_price * quantity,
            'margin_rate': round(context.margin_rate, 4),
            'would_proceed': rule_result['decision'] == 'pass',
        }

    # ── 내부 로직 ─────────────────────────────────────────────────────────

    def _execute_with_retry(self, order: PurchaseOrder) -> PurchaseResult:
        """지수 백오프 재시도 포함 주문 실행."""
        order.update_status(PurchaseStatus.SOURCE_SELECTED)
        self._monitor.update_order(order)

        for attempt in range(order.max_retries):
            try:
                result = self._do_purchase(order)
                if result.success:
                    return result
                order.retry_count += 1
                if attempt < order.max_retries - 1:
                    delay = _RETRY_BASE_DELAY ** (attempt + 1)
                    logger.info(
                        'Retry %d/%d for order %s in %.1fs',
                        attempt + 1, order.max_retries, order.order_id, delay,
                    )
                    time.sleep(delay)
            except Exception as exc:
                order.retry_count += 1
                logger.error('Purchase attempt error: %s', exc)
                if attempt == order.max_retries - 1:
                    order.update_status(PurchaseStatus.FAILED, str(exc))
                    self._history[order.order_id] = order
                    self._monitor.update_order(order)
                    return PurchaseResult(
                        success=False,
                        order_id=order.order_id,
                        error_message=str(exc),
                    )
                delay = _RETRY_BASE_DELAY ** (attempt + 1)
                time.sleep(delay)

        order.update_status(PurchaseStatus.FAILED, f'최대 재시도 {order.max_retries}회 초과')
        self._history[order.order_id] = order
        self._monitor.update_order(order)
        return PurchaseResult(
            success=False,
            order_id=order.order_id,
            error_message=f'최대 재시도 {order.max_retries}회 초과',
        )

    def _do_purchase(self, order: PurchaseOrder) -> PurchaseResult:
        """실제 구매를 실행한다."""
        buyer = self._buyers.get(order.source_marketplace)
        if not buyer:
            raise ValueError(f'Unknown marketplace: {order.source_marketplace}')

        # 재고 확인
        availability = buyer.check_availability(order.source_product_id)
        if not availability.get('available'):
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message=f'재고 없음: {order.source_product_id}',
                marketplace=order.source_marketplace,
            )

        # 구매 진행 상태 업데이트
        order.update_status(PurchaseStatus.PURCHASING)
        self._monitor.update_order(order)

        # 마켓플레이스 주문
        result = buyer.place_order(order)
        if not result.success:
            return result

        # 결제 처리
        order.update_status(PurchaseStatus.PAYMENT_PROCESSING)
        self._monitor.update_order(order)

        payment_record = self._payment.process_payment(
            order_id=order.order_id,
            marketplace=order.source_marketplace,
            amount=result.actual_cost,
            currency=result.currency,
        )

        if payment_record.status != 'completed':
            # 결제 실패 시 주문 취소 시도
            buyer.cancel_order(result.order_id)
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message='결제 실패',
                marketplace=order.source_marketplace,
            )

        # 확인 완료
        order.confirmation_code = result.confirmation_code
        order.update_status(PurchaseStatus.CONFIRMED)
        self._history[order.order_id] = order
        self._monitor.update_order(order)

        logger.info(
            'Purchase confirmed: %s (conf: %s, cost: %.2f %s)',
            order.order_id, result.confirmation_code,
            result.actual_cost, result.currency,
        )
        return result

    def register_buyer(self, marketplace: str, buyer: MarketplaceBuyer) -> None:
        """커스텀 마켓플레이스 구매자를 등록한다."""
        self._buyers[marketplace] = buyer

    def list_marketplaces(self) -> List[str]:
        return list(self._buyers.keys())
