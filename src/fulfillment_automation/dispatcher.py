"""src/fulfillment_automation/dispatcher.py — 자동 발송 오케스트레이터 (Phase 84).

배송대행 출고 확정(outbound-confirmed) 이벤트를 소비해 국내 택배 발송을 자동 처리한다.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .carriers.base import CarrierBase
from .carriers.cj_logistics import CJLogisticsCarrier
from .carriers.hanjin import HanjinCarrier
from .carriers.lotte import LotteCarrier
from .models import DispatchRequest, FulfillmentOrder, FulfillmentStatus

logger = logging.getLogger(__name__)


class CarrierRegistry:
    """등록된 택배사를 관리한다."""

    def __init__(self, carriers: Optional[List[CarrierBase]] = None) -> None:
        self._carriers: Dict[str, CarrierBase] = {}
        defaults = carriers or [CJLogisticsCarrier(), HanjinCarrier(), LotteCarrier()]
        for carrier in defaults:
            self._carriers[carrier.carrier_id] = carrier

    def get(self, carrier_id: str) -> CarrierBase:
        carrier = self._carriers.get(carrier_id)
        if carrier is None:
            raise KeyError(f'알 수 없는 택배사: {carrier_id}')
        return carrier

    def list_carriers(self) -> List[Dict]:
        return [
            {
                'carrier_id': c.carrier_id,
                'name': c.name,
                'base_cost_krw': c.base_cost_krw,
                'avg_delivery_days': c.avg_delivery_days,
            }
            for c in self._carriers.values()
        ]

    def recommend(self, weight_kg: float = 1.0, strategy: str = 'balanced') -> CarrierBase:
        """전략에 따라 최적 택배사를 추천한다."""
        carriers = list(self._carriers.values())
        if not carriers:
            raise RuntimeError('등록된 택배사가 없습니다')
        if strategy == 'cheapest':
            return min(carriers, key=lambda c: c.base_cost_krw)
        elif strategy == 'fastest':
            return min(carriers, key=lambda c: c.avg_delivery_days)
        else:  # balanced
            def score(c: CarrierBase) -> float:
                cost_norm = c.base_cost_krw / 10000.0
                speed_norm = c.avg_delivery_days / 5.0
                return 0.5 * cost_norm + 0.5 * speed_norm
            return min(carriers, key=score)


class AutoDispatcher:
    """자동 발송 오케스트레이터.

    배송대행 출고 확정 이벤트(outbound-confirmed)를 소비해 국내 배송 발송을
    자동으로 처리하고 FulfillmentOrder를 생성·관리한다.
    """

    def __init__(self, registry: Optional[CarrierRegistry] = None) -> None:
        self._registry = registry or CarrierRegistry()
        self._orders: Dict[str, FulfillmentOrder] = {}

    # ------------------------------------------------------------------
    # 이벤트 소비 — outbound-confirmed
    # ------------------------------------------------------------------

    def consume_outbound_confirmed(self, event: Dict) -> FulfillmentOrder:
        """배송대행 출고 확정 이벤트를 소비하고 국내 발송을 자동 처리한다.

        Args:
            event: {
                'outbound_request_id': str,
                'package_ids': list[str],
                'recipient_name': str,
                'recipient_address': str,
                'weight_kg': float,
                'carrier_id': str (optional),
                'strategy': str (optional, default 'balanced'),
                'items': list[dict] (optional),
            }

        Returns:
            생성된 FulfillmentOrder
        """
        outbound_request_id = event.get('outbound_request_id', '')
        package_ids = event.get('package_ids', [])
        recipient_name = event.get('recipient_name', '')
        recipient_address = event.get('recipient_address', '')
        weight_kg = float(event.get('weight_kg', 1.0))
        carrier_id = event.get('carrier_id')
        strategy = event.get('strategy', 'balanced')
        items = event.get('items', [])

        dispatch_req = DispatchRequest(
            outbound_request_id=outbound_request_id,
            package_ids=package_ids,
            carrier_id=carrier_id or '',
            recipient_name=recipient_name,
            recipient_address=recipient_address,
            weight_kg=weight_kg,
            strategy=strategy,
        )
        return self.dispatch(dispatch_req, items=items)

    # ------------------------------------------------------------------
    # 발송 처리
    # ------------------------------------------------------------------

    def dispatch(
        self,
        request: DispatchRequest,
        items: Optional[List[Dict]] = None,
    ) -> FulfillmentOrder:
        """발송 요청을 처리하고 FulfillmentOrder를 반환한다."""
        order = FulfillmentOrder(
            outbound_request_id=request.outbound_request_id,
            package_ids=request.package_ids,
            recipient_name=request.recipient_name,
            recipient_address=request.recipient_address,
            items=items or [],
            metadata={'dispatch_id': request.dispatch_id},
        )
        self._orders[order.order_id] = order
        order.update_status(FulfillmentStatus.dispatching)

        try:
            if request.carrier_id:
                carrier = self._registry.get(request.carrier_id)
            else:
                carrier = self._registry.recommend(
                    weight_kg=request.weight_kg,
                    strategy=request.strategy,
                )

            recipient = {
                'name': request.recipient_name,
                'address': request.recipient_address,
            }
            package_info = {'weight_kg': request.weight_kg}
            waybill = carrier.create_waybill(order.order_id, recipient, package_info)
            carrier.request_pickup(waybill['tracking_number'])

            order.carrier_id = carrier.carrier_id
            order.tracking_number = waybill['tracking_number']
            order.metadata['waybill'] = waybill
            order.update_status(FulfillmentStatus.dispatched)

            logger.info(
                'Auto-dispatched: order=%s carrier=%s tracking=%s',
                order.order_id, carrier.carrier_id, order.tracking_number,
            )
        except Exception as exc:
            logger.error('Dispatch failed for order=%s: %s', order.order_id, exc)
            order.update_status(FulfillmentStatus.failed)
            order.metadata['error'] = str(exc)

        return order

    # ------------------------------------------------------------------
    # 주문 조회
    # ------------------------------------------------------------------

    def get_order(self, order_id: str) -> Optional[FulfillmentOrder]:
        return self._orders.get(order_id)

    def list_orders(self, status: Optional[FulfillmentStatus] = None) -> List[FulfillmentOrder]:
        orders = list(self._orders.values())
        if status is not None:
            orders = [o for o in orders if o.status == status]
        return orders

    def get_stats(self) -> Dict:
        orders = list(self._orders.values())
        stats: Dict[str, int] = {s.value: 0 for s in FulfillmentStatus}
        for o in orders:
            stats[o.status.value] += 1
        return {
            'total': len(orders),
            'by_status': stats,
            'carriers': self._registry.list_carriers(),
        }

    # ------------------------------------------------------------------
    # 봇 알림 핸드오프
    # ------------------------------------------------------------------

    def notify_bot(self, order: FulfillmentOrder) -> Dict:
        """봇 레이어에 발송 완료를 알린다 (graceful degradation)."""
        payload: Dict = {
            'event': 'dispatch_completed',
            'order_id': order.order_id,
            'tracking_number': order.tracking_number,
            'carrier_id': order.carrier_id,
            'status': order.status.value,
        }
        try:
            from ..bot.dispatcher import BotDispatcher  # type: ignore[import-untyped]
            BotDispatcher().send(payload)
        except Exception as exc:
            logger.debug('Bot notification skipped: %s', exc)
        return payload
