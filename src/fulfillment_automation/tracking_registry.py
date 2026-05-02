"""src/fulfillment_automation/tracking_registry.py — 운송장 자동 등록 및 상태 동기화 (Phase 84)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .carriers.base import CarrierBase
from .carriers.cj_logistics import CJLogisticsCarrier
from .carriers.hanjin import HanjinCarrier
from .carriers.lotte import LotteCarrier
from .models import FulfillmentOrder, FulfillmentStatus, TrackingInfo

logger = logging.getLogger(__name__)


class TrackingRegistry:
    """운송장 자동 등록 및 상태 동기화 레지스트리.

    FulfillmentOrder에 운송장 번호를 등록하고 택배사 API를 통해 상태를 동기화한다.
    주문 정보를 봇 레이어에 전달하는 기능도 포함한다.
    """

    def __init__(self, carriers: Optional[List[CarrierBase]] = None) -> None:
        _defaults = carriers or [CJLogisticsCarrier(), HanjinCarrier(), LotteCarrier()]
        self._carriers: Dict[str, CarrierBase] = {c.carrier_id: c for c in _defaults}
        self._tracking_records: Dict[str, TrackingInfo] = {}

    # ------------------------------------------------------------------
    # 운송장 등록
    # ------------------------------------------------------------------

    def register(
        self,
        order_id: str,
        tracking_number: str,
        carrier_id: str,
        metadata: Optional[Dict] = None,
    ) -> TrackingInfo:
        """운송장을 등록하고 TrackingInfo를 반환한다.

        Args:
            order_id: 풀필먼트 자동화 주문 ID
            tracking_number: 운송장 번호
            carrier_id: 택배사 ID
            metadata: 추가 메타데이터

        Returns:
            등록된 TrackingInfo
        """
        carrier = self._carriers.get(carrier_id)
        carrier_name = carrier.name if carrier else carrier_id

        info = TrackingInfo(
            order_id=order_id,
            tracking_number=tracking_number,
            carrier_id=carrier_id,
            carrier_name=carrier_name,
            status='registered',
            metadata=metadata or {},
        )
        self._tracking_records[tracking_number] = info
        logger.info(
            'Tracking registered: order=%s tracking=%s carrier=%s',
            order_id, tracking_number, carrier_id,
        )
        return info

    def register_from_order(self, order: FulfillmentOrder) -> Optional[TrackingInfo]:
        """FulfillmentOrder에서 운송장 정보를 자동 등록한다."""
        if not order.tracking_number or not order.carrier_id:
            logger.warning(
                'Cannot register tracking for order=%s: missing tracking_number or carrier_id',
                order.order_id,
            )
            return None
        info = self.register(
            order_id=order.order_id,
            tracking_number=order.tracking_number,
            carrier_id=order.carrier_id,
        )
        order.update_status(FulfillmentStatus.tracking_registered)
        return info

    # ------------------------------------------------------------------
    # 상태 동기화
    # ------------------------------------------------------------------

    def sync_status(self, tracking_number: str) -> TrackingInfo:
        """택배사 API를 통해 운송장 상태를 동기화한다."""
        info = self._tracking_records.get(tracking_number)
        if info is None:
            raise KeyError(f'운송장을 찾을 수 없습니다: {tracking_number}')

        carrier = self._carriers.get(info.carrier_id)
        if carrier is None:
            logger.warning('Unknown carrier_id=%s for tracking=%s', info.carrier_id, tracking_number)
            return info

        from datetime import datetime, timezone
        tracking_data = carrier.get_tracking(tracking_number)
        info.status = tracking_data.get('status', info.status)
        info.events = tracking_data.get('events', info.events)
        info.last_synced_at = datetime.now(timezone.utc).isoformat()
        logger.debug('Tracking synced: %s → %s', tracking_number, info.status)
        return info

    def sync_all(self) -> List[TrackingInfo]:
        """모든 운송장 상태를 동기화한다."""
        results: List[TrackingInfo] = []
        for tracking_number in list(self._tracking_records):
            try:
                results.append(self.sync_status(tracking_number))
            except Exception as exc:
                logger.warning('Sync failed for %s: %s', tracking_number, exc)
        return results

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------

    def get(self, tracking_number: str) -> Optional[TrackingInfo]:
        return self._tracking_records.get(tracking_number)

    def get_by_order(self, order_id: str) -> List[TrackingInfo]:
        return [r for r in self._tracking_records.values() if r.order_id == order_id]

    def list_all(self) -> List[TrackingInfo]:
        return list(self._tracking_records.values())

    # ------------------------------------------------------------------
    # 봇 레이어 알림
    # ------------------------------------------------------------------

    def notify_order_tracking(self, order_id: str, tracking_number: str, carrier_id: str) -> Dict:
        """주문 추적 정보를 봇 레이어에 알린다 (graceful degradation)."""
        payload: Dict = {
            'event': 'tracking_registered',
            'order_id': order_id,
            'tracking_number': tracking_number,
            'carrier_id': carrier_id,
        }
        try:
            from ..bot.dispatcher import BotDispatcher  # type: ignore[import-untyped]
            BotDispatcher().send(payload)
        except Exception as exc:
            logger.debug('Bot notification skipped: %s', exc)
        return payload
