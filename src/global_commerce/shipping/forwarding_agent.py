"""src/global_commerce/shipping/forwarding_agent.py — 배송대행지 인터페이스 (Phase 93)."""
from __future__ import annotations

import abc
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InboundItem:
    """입고 아이템."""
    item_id: str
    agent_id: str
    order_id: str
    product_name: str
    quantity: int
    weight_kg: float
    status: str = 'received'
    received_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'item_id': self.item_id,
            'agent_id': self.agent_id,
            'order_id': self.order_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'weight_kg': self.weight_kg,
            'status': self.status,
            'received_at': self.received_at,
        }


@dataclass
class ConsolidationRequest:
    """합배송 요청."""
    request_id: str
    agent_id: str
    item_ids: List[str]
    destination_country: str
    status: str = 'pending'
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'request_id': self.request_id,
            'agent_id': self.agent_id,
            'item_ids': self.item_ids,
            'destination_country': self.destination_country,
            'status': self.status,
            'created_at': self.created_at,
        }


@dataclass
class OutboundRequest:
    """출고 요청."""
    request_id: str
    agent_id: str
    item_ids: List[str]
    destination_country: str
    recipient_name: str
    recipient_address: str
    tracking_number: str = ''
    status: str = 'requested'
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'request_id': self.request_id,
            'agent_id': self.agent_id,
            'item_ids': self.item_ids,
            'destination_country': self.destination_country,
            'recipient_name': self.recipient_name,
            'recipient_address': self.recipient_address,
            'tracking_number': self.tracking_number,
            'status': self.status,
            'created_at': self.created_at,
        }


class ForwardingAgentABC(abc.ABC):
    """배송대행지 추상 클래스."""

    @property
    @abc.abstractmethod
    def agent_id(self) -> str:
        """배송대행지 ID."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """배송대행지 이름."""

    @abc.abstractmethod
    def confirm_inbound(self, order_id: str, product_name: str,
                        quantity: int, weight_kg: float) -> InboundItem:
        """입고 확인."""

    @abc.abstractmethod
    def request_consolidation(self, item_ids: List[str],
                              destination_country: str) -> ConsolidationRequest:
        """합배송 요청."""

    @abc.abstractmethod
    def request_outbound(self, item_ids: List[str], destination_country: str,
                         recipient_name: str, recipient_address: str) -> OutboundRequest:
        """출고 요청."""

    @abc.abstractmethod
    def get_status(self) -> dict:
        """배송대행지 상태 조회."""


class MoltailAgent(ForwardingAgentABC):
    """몰테일 배송대행지 Mock 구현."""

    _AGENT_ID = 'moltail'
    _NAME = '몰테일 (Moltail)'

    def __init__(self):
        self._items: Dict[str, InboundItem] = {}
        self._consolidations: Dict[str, ConsolidationRequest] = {}
        self._outbounds: Dict[str, OutboundRequest] = {}

    @property
    def agent_id(self) -> str:
        return self._AGENT_ID

    @property
    def name(self) -> str:
        return self._NAME

    def confirm_inbound(self, order_id: str, product_name: str,
                        quantity: int, weight_kg: float) -> InboundItem:
        item = InboundItem(
            item_id=f"MT-{uuid.uuid4().hex[:8].upper()}",
            agent_id=self._AGENT_ID,
            order_id=order_id,
            product_name=product_name,
            quantity=quantity,
            weight_kg=weight_kg,
        )
        self._items[item.item_id] = item
        logger.info("몰테일 입고 확인: %s order=%s", item.item_id, order_id)
        return item

    def request_consolidation(self, item_ids: List[str],
                              destination_country: str) -> ConsolidationRequest:
        req = ConsolidationRequest(
            request_id=f"MT-CON-{uuid.uuid4().hex[:8].upper()}",
            agent_id=self._AGENT_ID,
            item_ids=list(item_ids),
            destination_country=destination_country.upper(),
            status='pending',
        )
        self._consolidations[req.request_id] = req
        return req

    def request_outbound(self, item_ids: List[str], destination_country: str,
                         recipient_name: str, recipient_address: str) -> OutboundRequest:
        tracking = f"MT{uuid.uuid4().hex[:12].upper()}"
        req = OutboundRequest(
            request_id=f"MT-OUT-{uuid.uuid4().hex[:8].upper()}",
            agent_id=self._AGENT_ID,
            item_ids=list(item_ids),
            destination_country=destination_country.upper(),
            recipient_name=recipient_name,
            recipient_address=recipient_address,
            tracking_number=tracking,
            status='processing',
        )
        self._outbounds[req.request_id] = req
        return req

    def get_status(self) -> dict:
        return {
            'agent_id': self._AGENT_ID,
            'name': self._NAME,
            'status': 'operational',
            'inbound_count': len(self._items),
            'consolidation_count': len(self._consolidations),
            'outbound_count': len(self._outbounds),
        }

    def list_items(self) -> List[InboundItem]:
        return list(self._items.values())


class OhmyzipAgent(ForwardingAgentABC):
    """오마이집 배송대행지 Mock 구현."""

    _AGENT_ID = 'ohmyzip'
    _NAME = '오마이집 (Ohmyzip)'

    def __init__(self):
        self._items: Dict[str, InboundItem] = {}
        self._consolidations: Dict[str, ConsolidationRequest] = {}
        self._outbounds: Dict[str, OutboundRequest] = {}

    @property
    def agent_id(self) -> str:
        return self._AGENT_ID

    @property
    def name(self) -> str:
        return self._NAME

    def confirm_inbound(self, order_id: str, product_name: str,
                        quantity: int, weight_kg: float) -> InboundItem:
        item = InboundItem(
            item_id=f"OMZ-{uuid.uuid4().hex[:8].upper()}",
            agent_id=self._AGENT_ID,
            order_id=order_id,
            product_name=product_name,
            quantity=quantity,
            weight_kg=weight_kg,
        )
        self._items[item.item_id] = item
        return item

    def request_consolidation(self, item_ids: List[str],
                              destination_country: str) -> ConsolidationRequest:
        req = ConsolidationRequest(
            request_id=f"OMZ-CON-{uuid.uuid4().hex[:8].upper()}",
            agent_id=self._AGENT_ID,
            item_ids=list(item_ids),
            destination_country=destination_country.upper(),
            status='pending',
        )
        self._consolidations[req.request_id] = req
        return req

    def request_outbound(self, item_ids: List[str], destination_country: str,
                         recipient_name: str, recipient_address: str) -> OutboundRequest:
        tracking = f"OMZ{uuid.uuid4().hex[:12].upper()}"
        req = OutboundRequest(
            request_id=f"OMZ-OUT-{uuid.uuid4().hex[:8].upper()}",
            agent_id=self._AGENT_ID,
            item_ids=list(item_ids),
            destination_country=destination_country.upper(),
            recipient_name=recipient_name,
            recipient_address=recipient_address,
            tracking_number=tracking,
            status='processing',
        )
        self._outbounds[req.request_id] = req
        return req

    def get_status(self) -> dict:
        return {
            'agent_id': self._AGENT_ID,
            'name': self._NAME,
            'status': 'operational',
            'inbound_count': len(self._items),
            'consolidation_count': len(self._consolidations),
            'outbound_count': len(self._outbounds),
        }
