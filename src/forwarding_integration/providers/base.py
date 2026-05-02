"""src/forwarding_integration/providers/base.py — ForwardingProvider ABC (Phase 83)."""
from __future__ import annotations

import abc
from typing import List

from ..models import (
    ConsolidationRequest,
    ForwardingPackage,
    ForwardingStatus,
    InboundRegistration,
    OutboundRequest,
)


class ForwardingProvider(abc.ABC):
    """배송대행 공급자 추상 기반 클래스."""

    @property
    @abc.abstractmethod
    def provider_id(self) -> str:
        """공급자 ID."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """공급자 이름."""

    @abc.abstractmethod
    def register_inbound(self, package: ForwardingPackage) -> InboundRegistration:
        """입고 등록."""

    @abc.abstractmethod
    def confirm_arrival(self, registration_id: str) -> InboundRegistration:
        """도착 확인."""

    @abc.abstractmethod
    def request_consolidation(
        self, package_ids: List[str], destination_country: str
    ) -> ConsolidationRequest:
        """합배송 요청."""

    @abc.abstractmethod
    def request_outbound(
        self,
        package_ids: List[str],
        destination_country: str,
        recipient_name: str,
        recipient_address: str,
    ) -> OutboundRequest:
        """출고 요청."""

    @abc.abstractmethod
    def track_package(self, package_id: str) -> ForwardingStatus:
        """패키지 추적."""
