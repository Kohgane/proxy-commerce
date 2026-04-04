"""src/auto_purchase/import_automation.py — 수입/구매대행 자동 처리 (Phase 96)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ImportOrderRequest:
    """수입 주문 요청 모델."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_order_id: str = ''
    product_url: str = ''
    product_id: str = ''
    marketplace: str = ''
    quantity: int = 1
    unit_price: float = 0.0
    currency: str = 'USD'
    destination_country: str = 'KR'
    shipping_address: Dict = field(default_factory=dict)
    hs_code: str = ''
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = 'pending'
    metadata: Dict = field(default_factory=dict)


@dataclass
class ProxyBuyRequest:
    """구매대행 요청 모델."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ''
    product_url: str = ''
    product_name: str = ''
    marketplace: str = ''
    quantity: int = 1
    estimated_price: float = 0.0
    currency: str = 'USD'
    shipping_address: Dict = field(default_factory=dict)
    notes: str = ''
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = 'received'
    metadata: Dict = field(default_factory=dict)


class ImportAutomation:
    """수입 자동화 플로우.

    고객 주문 접수 → 해외 자동 구매 → 배송대행지 입고 → 관세 계산 → 국내 배송 전체 플로우.

    기존 연동:
      - src/global_commerce/trade/ImportManager
      - src/global_commerce/shipping/ForwardingAgent
    """

    def __init__(self, purchase_engine=None) -> None:
        self._engine = purchase_engine
        self._requests: Dict[str, ImportOrderRequest] = {}
        self._forwarding_address = {
            'name': 'AutoForwarder KR',
            'address': '경기도 파주시 배송대행지로 123',
            'zipcode': '10881',
            'country': 'KR',
        }

    def create_import_order(
        self,
        customer_order_id: str,
        product_id: str,
        marketplace: str,
        quantity: int = 1,
        unit_price: float = 0.0,
        currency: str = 'USD',
        hs_code: str = '',
        destination_country: str = 'KR',
        shipping_address: Dict = None,
    ) -> ImportOrderRequest:
        """수입 주문을 생성하고 자동 구매 플로우를 시작한다."""
        request = ImportOrderRequest(
            customer_order_id=customer_order_id,
            product_id=product_id,
            marketplace=marketplace,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            hs_code=hs_code,
            destination_country=destination_country,
            shipping_address=shipping_address or {},
        )
        self._requests[request.request_id] = request

        # 관세 계산
        duty_info = self._calculate_customs(unit_price, quantity, currency, destination_country, hs_code)
        request.metadata['duty_info'] = duty_info

        # 자동 구매 트리거
        if self._engine:
            purchase_order = self._engine.submit_order(
                source_product_id=product_id,
                marketplace=marketplace,
                quantity=quantity,
                unit_price=unit_price,
                currency=currency,
                customer_order_id=customer_order_id,
                shipping_address=self._forwarding_address,
            )
            request.metadata['purchase_order_id'] = purchase_order.order_id
            request.status = 'purchasing'
        else:
            request.status = 'queued'

        logger.info(
            'Import order created: %s (marketplace: %s, qty: %d)',
            request.request_id, marketplace, quantity,
        )
        return request

    def _calculate_customs(
        self,
        unit_price: float,
        quantity: int,
        currency: str,
        destination_country: str,
        hs_code: str,
    ) -> Dict:
        """관세를 계산한다 (ImportManager 연동)."""
        try:
            from ..global_commerce.trade.import_manager import CustomsDutyCalculator
            calc = CustomsDutyCalculator()
            # USD 기준으로 환산 (간단 mock)
            price_usd = unit_price * quantity
            if currency == 'JPY':
                price_usd /= 150.0
            elif currency == 'CNY':
                price_usd /= 7.2
            return calc.calculate(
                declared_value_usd=price_usd,
                hs_code=hs_code or 'DEFAULT',
                destination_country=destination_country,
            )
        except Exception as exc:
            logger.debug('Customs calculation fallback: %s', exc)
            return {'duty_rate': 0.08, 'vat_rate': 0.10, 'estimated_total_usd': unit_price * quantity * 1.18}

    def get_import_order(self, request_id: str) -> Optional[ImportOrderRequest]:
        return self._requests.get(request_id)

    def list_import_orders(self, status: str = '') -> List[ImportOrderRequest]:
        orders = list(self._requests.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return orders

    def update_forwarding_received(self, request_id: str, tracking_number: str) -> bool:
        """배송대행지 입고 처리."""
        request = self._requests.get(request_id)
        if not request:
            return False
        request.status = 'forwarding_received'
        request.metadata['tracking_number'] = tracking_number
        request.metadata['forwarding_received_at'] = datetime.now(timezone.utc).isoformat()
        logger.info('Forwarding received: %s (tracking: %s)', request_id, tracking_number)
        return True


class ProxyBuyAutomation:
    """구매대행 자동 처리 플로우.

    고객 요청 → 해외 구매 → 검수 → 발송 플로우.
    """

    def __init__(self, purchase_engine=None) -> None:
        self._engine = purchase_engine
        self._requests: Dict[str, ProxyBuyRequest] = {}

    def create_proxy_request(
        self,
        customer_id: str,
        product_url: str,
        product_name: str,
        marketplace: str,
        quantity: int = 1,
        estimated_price: float = 0.0,
        currency: str = 'USD',
        shipping_address: Dict = None,
        notes: str = '',
    ) -> ProxyBuyRequest:
        """구매대행 요청을 생성한다."""
        request = ProxyBuyRequest(
            customer_id=customer_id,
            product_url=product_url,
            product_name=product_name,
            marketplace=marketplace,
            quantity=quantity,
            estimated_price=estimated_price,
            currency=currency,
            shipping_address=shipping_address or {},
            notes=notes,
        )
        self._requests[request.request_id] = request

        # 자동 구매 트리거 (URL에서 상품 ID 추출 시뮬레이션)
        product_id = self._extract_product_id(product_url, marketplace)
        if self._engine and product_id:
            purchase_order = self._engine.submit_order(
                source_product_id=product_id,
                marketplace=marketplace,
                quantity=quantity,
                unit_price=estimated_price,
                currency=currency,
                customer_order_id=customer_id,
            )
            request.metadata = {'purchase_order_id': purchase_order.order_id}
            request.status = 'purchasing'
        else:
            request.status = 'pending_review'

        logger.info(
            'Proxy buy request: %s (customer: %s, marketplace: %s)',
            request.request_id, customer_id, marketplace,
        )
        return request

    def _extract_product_id(self, url: str, marketplace: str) -> str:
        """URL에서 상품 ID를 추출한다 (mock)."""
        # Amazon: /dp/ASIN
        if 'amazon' in url:
            parts = url.split('/dp/')
            if len(parts) > 1:
                return parts[1].split('/')[0].split('?')[0]
        # 타오바오: id=XXXXX
        if 'taobao' in url:
            for part in url.split('&'):
                if 'id=' in part:
                    return 'TB' + part.split('id=')[-1].strip()
        # 1688: offer/XXXXX.html
        if '1688' in url:
            for part in url.split('/'):
                if '.html' in part:
                    return '1688-' + part.replace('.html', '')
        return ''

    def update_inspection_result(self, request_id: str, passed: bool, notes: str = '') -> bool:
        """검수 결과를 업데이트한다."""
        request = self._requests.get(request_id)
        if not request:
            return False
        request.status = 'inspection_passed' if passed else 'inspection_failed'
        request.metadata['inspection_notes'] = notes
        return True

    def get_request(self, request_id: str) -> Optional[ProxyBuyRequest]:
        return self._requests.get(request_id)

    def list_requests(self, status: str = '', customer_id: str = '') -> List[ProxyBuyRequest]:
        requests = list(self._requests.values())
        if status:
            requests = [r for r in requests if r.status == status]
        if customer_id:
            requests = [r for r in requests if r.customer_id == customer_id]
        return requests
