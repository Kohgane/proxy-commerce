"""src/global_commerce/trade/export_manager.py — 수출/구매대행 관리 (Phase 93)."""
from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ExportStatus(str, enum.Enum):
    ORDERED = 'ordered'
    COLLECTED = 'collected'
    QUALITY_CHECK = 'quality_check'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'
    CANCELLED = 'cancelled'


_VALID_TRANSITIONS: Dict[str, List[str]] = {
    ExportStatus.ORDERED: [ExportStatus.COLLECTED, ExportStatus.CANCELLED],
    ExportStatus.COLLECTED: [ExportStatus.QUALITY_CHECK, ExportStatus.CANCELLED],
    ExportStatus.QUALITY_CHECK: [ExportStatus.SHIPPED, ExportStatus.CANCELLED],
    ExportStatus.SHIPPED: [ExportStatus.DELIVERED],
    ExportStatus.DELIVERED: [],
    ExportStatus.CANCELLED: [],
}


@dataclass
class ExportOrder:
    """수출 주문."""
    order_id: str
    product_name: str
    source_country: str
    destination_country: str
    quantity: int
    unit_price_usd: float
    customer_name: str
    customer_address: str
    status: ExportStatus = ExportStatus.ORDERED
    tracking_number: str = ''
    notes: str = ''
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total_price_usd(self) -> float:
        return round(self.unit_price_usd * self.quantity, 2)

    def to_dict(self) -> dict:
        return {
            'order_id': self.order_id,
            'product_name': self.product_name,
            'source_country': self.source_country,
            'destination_country': self.destination_country,
            'quantity': self.quantity,
            'unit_price_usd': self.unit_price_usd,
            'total_price_usd': self.total_price_usd,
            'customer_name': self.customer_name,
            'customer_address': self.customer_address,
            'status': self.status.value,
            'tracking_number': self.tracking_number,
            'notes': self.notes,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class ExportManager:
    """수출/구매대행 주문 관리."""

    def __init__(self):
        self._orders: Dict[str, ExportOrder] = {}

    def create(self, product_name: str, source_country: str,
               destination_country: str, quantity: int = 1,
               unit_price_usd: float = 0.0, customer_name: str = '',
               customer_address: str = '', notes: str = '') -> ExportOrder:
        """수출 주문 생성.

        Args:
            product_name: 상품명
            source_country: 출발 국가 코드
            destination_country: 목적지 국가 코드
            quantity: 수량
            unit_price_usd: 단가 (USD)
            customer_name: 수취인 이름
            customer_address: 수취인 주소
            notes: 메모

        Returns:
            ExportOrder
        """
        order = ExportOrder(
            order_id=str(uuid.uuid4()),
            product_name=product_name,
            source_country=source_country.upper(),
            destination_country=destination_country.upper(),
            quantity=quantity,
            unit_price_usd=unit_price_usd,
            customer_name=customer_name,
            customer_address=customer_address,
            notes=notes,
        )
        self._orders[order.order_id] = order
        logger.info("수출 주문 생성: %s dest=%s", order.order_id, destination_country)
        return order

    def get(self, order_id: str) -> Optional[ExportOrder]:
        return self._orders.get(order_id)

    def transition(self, order_id: str, new_status: str,
                   tracking_number: str = '') -> ExportOrder:
        """수출 주문 상태 전환.

        Args:
            order_id: 주문 ID
            new_status: 새 상태
            tracking_number: 운송장 번호 (shipped 시 설정)

        Returns:
            갱신된 ExportOrder
        """
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"수출 주문을 찾을 수 없습니다: {order_id}")

        try:
            new_status_enum = ExportStatus(new_status)
        except ValueError:
            raise ValueError(f"유효하지 않은 상태: {new_status}")

        allowed = _VALID_TRANSITIONS.get(order.status, [])
        if new_status_enum not in allowed:
            raise ValueError(
                f"허용되지 않은 상태 전환: {order.status.value} → {new_status}"
            )

        order.status = new_status_enum
        order.updated_at = datetime.now().isoformat()
        if tracking_number:
            order.tracking_number = tracking_number

        logger.info("수출 주문 상태 변경: %s → %s", order_id, new_status)
        return order

    def generate_invoice(self, order_id: str) -> dict:
        """인보이스 생성 (mock).

        Args:
            order_id: 주문 ID

        Returns:
            인보이스 딕셔너리
        """
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"수출 주문을 찾을 수 없습니다: {order_id}")
        return {
            'invoice_number': f"INV-{order.order_id[:8].upper()}",
            'date': datetime.now().strftime('%Y-%m-%d'),
            'seller': {'name': 'Proxy Commerce', 'country': order.source_country},
            'buyer': {'name': order.customer_name, 'address': order.customer_address},
            'items': [{
                'description': order.product_name,
                'quantity': order.quantity,
                'unit_price_usd': order.unit_price_usd,
                'total_usd': order.total_price_usd,
            }],
            'total_usd': order.total_price_usd,
            'currency': 'USD',
            'incoterms': 'DAP',
        }

    def generate_packing_list(self, order_id: str) -> dict:
        """패킹리스트 생성 (mock).

        Args:
            order_id: 주문 ID

        Returns:
            패킹리스트 딕셔너리
        """
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"수출 주문을 찾을 수 없습니다: {order_id}")
        return {
            'packing_list_number': f"PL-{order.order_id[:8].upper()}",
            'date': datetime.now().strftime('%Y-%m-%d'),
            'order_id': order.order_id,
            'items': [{
                'description': order.product_name,
                'quantity': order.quantity,
                'weight_kg': 0.5 * order.quantity,  # mock weight
                'dimensions_cm': '30x20x10',
            }],
            'total_packages': 1,
            'total_weight_kg': 0.5 * order.quantity,
        }

    def list(self, status: Optional[str] = None,
             destination_country: Optional[str] = None) -> List[ExportOrder]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status.value == status]
        if destination_country:
            orders = [o for o in orders if o.destination_country == destination_country.upper()]
        return orders
