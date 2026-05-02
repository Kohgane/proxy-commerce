"""src/forwarding_integration/providers/ihanex.py — IHanexProvider (Phase 83)."""
from __future__ import annotations

import logging
import uuid
from typing import Dict, List

from .base import ForwardingProvider
from ..models import (
    ConsolidationRequest,
    ForwardingPackage,
    ForwardingStatus,
    InboundRegistration,
    OutboundRequest,
)

logger = logging.getLogger(__name__)

_WAREHOUSE_US: Dict = {
    'name': '이하넥스 미국 창고',
    'address': '2400 Skyline Dr, Dallas, TX 75001, USA',
    'country': 'US',
}


class IHanexProvider(ForwardingProvider):
    """이하넥스 배송대행 공급자 Mock 구현."""

    _PROVIDER_ID = 'ihanex'
    _NAME = '이하넥스 (iHanex)'

    def __init__(self) -> None:
        self._registrations: Dict[str, InboundRegistration] = {}
        self._consolidations: Dict[str, ConsolidationRequest] = {}
        self._outbounds: Dict[str, OutboundRequest] = {}
        self._statuses: Dict[str, ForwardingStatus] = {}

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    @property
    def name(self) -> str:
        return self._NAME

    def register_inbound(self, package: ForwardingPackage) -> InboundRegistration:
        reg = InboundRegistration(
            package_id=package.package_id,
            provider=self._PROVIDER_ID,
            purchase_order_id=package.purchase_order_id,
            product_name=package.product_name,
            quantity=package.quantity,
            weight_kg=package.weight_kg,
            warehouse_address=_WAREHOUSE_US,
            status='registered',
        )
        self._registrations[reg.registration_id] = reg
        logger.info('iHanex 입고 등록: %s pkg=%s', reg.registration_id, package.package_id)
        return reg

    def confirm_arrival(self, registration_id: str) -> InboundRegistration:
        reg = self._registrations.get(registration_id)
        if reg is None:
            raise KeyError(f'Registration not found: {registration_id}')
        reg.status = 'arrived'
        logger.info('iHanex 도착 확인: %s', registration_id)
        return reg

    def request_consolidation(
        self, package_ids: List[str], destination_country: str
    ) -> ConsolidationRequest:
        req = ConsolidationRequest(
            package_ids=list(package_ids),
            provider=self._PROVIDER_ID,
            destination_country=destination_country.upper(),
            status='pending',
        )
        self._consolidations[req.request_id] = req
        return req

    def request_outbound(
        self,
        package_ids: List[str],
        destination_country: str,
        recipient_name: str,
        recipient_address: str,
    ) -> OutboundRequest:
        tracking = f"IH{uuid.uuid4().hex[:12].upper()}"
        req = OutboundRequest(
            package_ids=list(package_ids),
            provider=self._PROVIDER_ID,
            destination_country=destination_country.upper(),
            recipient_name=recipient_name,
            recipient_address=recipient_address,
            tracking_number=tracking,
            status='processing',
        )
        self._outbounds[req.request_id] = req
        return req

    def track_package(self, package_id: str) -> ForwardingStatus:
        status = self._statuses.get(package_id)
        if status is None:
            status = ForwardingStatus(
                package_id=package_id,
                current_status='in_transit',
                provider=self._PROVIDER_ID,
                tracking_number=f"IH{uuid.uuid4().hex[:12].upper()}",
                events=[{'event': 'in_transit', 'description': '배송 중'}],
            )
            self._statuses[package_id] = status
        return status
