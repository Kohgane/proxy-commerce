"""src/forwarding_integration/forwarding_engine.py — 배송대행 통합 엔진 (Phase 83).

라이프사이클 오케스트레이션:
  - 해외 구매 주문에서 입고 등록 생성 (auto_purchase 연동)
  - 도착 이벤트 처리
  - 다중 패키지 합배송 요청
  - 출고 배송 요청
  - 상태 동기화 폴링
  - 국내 배송 핸드오프 (global_commerce/shipping 연동)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .models import (
    ConsolidationRequest,
    ForwardingPackage,
    ForwardingStatus,
    InboundRegistration,
    OutboundRequest,
)
from .provider_registry import ProviderRegistry, get_default_registry

logger = logging.getLogger(__name__)


class ForwardingEngine:
    """배송대행 통합 엔진.

    공급자 레지스트리를 통해 공급자별 배송대행 라이프사이클을 조율한다.
    """

    def __init__(self, registry: Optional[ProviderRegistry] = None) -> None:
        self._registry = registry or get_default_registry()
        self._packages: Dict[str, ForwardingPackage] = {}

    # ------------------------------------------------------------------
    # 패키지 관리
    # ------------------------------------------------------------------

    def create_package(
        self,
        purchase_order_id: str,
        product_name: str,
        provider: str,
        quantity: int = 1,
        weight_kg: float = 0.0,
        customer_order_id: str = '',
        origin_country: str = 'US',
        destination_country: str = 'KR',
    ) -> ForwardingPackage:
        """배송대행 패키지를 생성한다."""
        package = ForwardingPackage(
            purchase_order_id=purchase_order_id,
            customer_order_id=customer_order_id,
            product_name=product_name,
            quantity=quantity,
            weight_kg=weight_kg,
            provider=provider,
            origin_country=origin_country,
            destination_country=destination_country,
            status='pending',
        )
        self._packages[package.package_id] = package
        logger.info(
            'Package created: %s (provider=%s, po=%s)',
            package.package_id, provider, purchase_order_id,
        )
        return package

    def get_package(self, package_id: str) -> ForwardingPackage:
        """패키지를 조회한다."""
        package = self._packages.get(package_id)
        if package is None:
            raise KeyError(f'Package not found: {package_id}')
        return package

    def list_packages(self, status: str = '') -> List[ForwardingPackage]:
        """패키지 목록을 반환한다."""
        packages = list(self._packages.values())
        if status:
            packages = [p for p in packages if p.status == status]
        return packages

    # ------------------------------------------------------------------
    # 입고 등록 (auto_purchase 연동)
    # ------------------------------------------------------------------

    def register_inbound_from_purchase(
        self,
        purchase_order_id: str,
        product_name: str,
        provider: str,
        quantity: int = 1,
        weight_kg: float = 0.0,
        customer_order_id: str = '',
        origin_country: str = 'US',
        destination_country: str = 'KR',
    ) -> InboundRegistration:
        """해외 구매 주문 확인 후 입고 등록을 생성한다.

        auto_purchase 출력 (purchase_confirmed) → forwarding inbound register 연동.
        """
        package = self.create_package(
            purchase_order_id=purchase_order_id,
            product_name=product_name,
            provider=provider,
            quantity=quantity,
            weight_kg=weight_kg,
            customer_order_id=customer_order_id,
            origin_country=origin_country,
            destination_country=destination_country,
        )
        provider_obj = self._registry.get(provider)
        registration = provider_obj.register_inbound(package)
        package.status = 'inbound_registered'
        package.metadata['registration_id'] = registration.registration_id
        logger.info(
            'Inbound registered from purchase: reg=%s pkg=%s',
            registration.registration_id, package.package_id,
        )
        return registration

    # ------------------------------------------------------------------
    # 도착 확인
    # ------------------------------------------------------------------

    def confirm_arrival(
        self, package_id: str, registration_id: str
    ) -> InboundRegistration:
        """패키지 도착 이벤트를 처리한다."""
        package = self.get_package(package_id)
        provider_obj = self._registry.get(package.provider)
        registration = provider_obj.confirm_arrival(registration_id)
        package.status = 'arrived'
        logger.info('Arrival confirmed: pkg=%s reg=%s', package_id, registration_id)
        return registration

    # ------------------------------------------------------------------
    # 합배송 요청
    # ------------------------------------------------------------------

    def request_consolidation(
        self,
        package_ids: List[str],
        provider: str,
        destination_country: str = 'KR',
    ) -> ConsolidationRequest:
        """다중 패키지 합배송을 요청한다."""
        if not package_ids:
            raise ValueError('package_ids must not be empty')
        provider_obj = self._registry.get(provider)
        req = provider_obj.request_consolidation(package_ids, destination_country)
        # 패키지 상태 갱신
        for pid in package_ids:
            pkg = self._packages.get(pid)
            if pkg:
                pkg.status = 'consolidation_requested'
                pkg.metadata['consolidation_request_id'] = req.request_id
        logger.info('Consolidation requested: req=%s pkgs=%s', req.request_id, package_ids)
        return req

    # ------------------------------------------------------------------
    # 출고 요청
    # ------------------------------------------------------------------

    def request_outbound(
        self,
        package_ids: List[str],
        provider: str,
        destination_country: str,
        recipient_name: str,
        recipient_address: str,
    ) -> OutboundRequest:
        """출고 배송을 요청한다."""
        if not package_ids:
            raise ValueError('package_ids must not be empty')
        provider_obj = self._registry.get(provider)
        req = provider_obj.request_outbound(
            package_ids, destination_country, recipient_name, recipient_address
        )
        # 패키지 상태 및 트래킹 번호 갱신
        for pid in package_ids:
            pkg = self._packages.get(pid)
            if pkg:
                pkg.status = 'outbound_requested'
                pkg.tracking_number = req.tracking_number
                pkg.metadata['outbound_request_id'] = req.request_id

        # global_commerce/shipping 핸드오프 (downstream domestic)
        self._handoff_to_domestic_shipping(req)
        logger.info('Outbound requested: req=%s pkgs=%s trk=%s', req.request_id, package_ids, req.tracking_number)
        return req

    def _handoff_to_domestic_shipping(self, outbound_req: OutboundRequest) -> None:
        """국내 배송으로 핸드오프한다 (global_commerce/shipping 연동)."""
        try:
            from ..global_commerce.shipping.international_shipping_manager import (
                InternationalShippingManager,
            )
            mgr = InternationalShippingManager()
            mgr.register_shipment(
                tracking_number=outbound_req.tracking_number,
                origin_country='US',
                destination_country=outbound_req.destination_country,
                recipient_name=outbound_req.recipient_name,
                recipient_address=outbound_req.recipient_address,
            )
        except Exception as exc:  # pragma: no cover — graceful degradation
            logger.debug('Domestic shipping handoff skipped: %s', exc)

    # ------------------------------------------------------------------
    # 상태 동기화 폴링
    # ------------------------------------------------------------------

    def sync_status(self, package_id: str) -> ForwardingStatus:
        """공급자 API를 통해 패키지 상태를 동기화한다."""
        package = self.get_package(package_id)
        provider_obj = self._registry.get(package.provider)
        status = provider_obj.track_package(package_id)
        package.status = status.current_status
        if status.tracking_number:
            package.tracking_number = status.tracking_number
        logger.debug('Status synced: pkg=%s status=%s', package_id, status.current_status)
        return status

    def sync_all_statuses(self) -> List[ForwardingStatus]:
        """모든 패키지 상태를 동기화한다."""
        results = []
        for package_id in list(self._packages):
            try:
                results.append(self.sync_status(package_id))
            except Exception as exc:
                logger.warning('Status sync failed for %s: %s', package_id, exc)
        return results
