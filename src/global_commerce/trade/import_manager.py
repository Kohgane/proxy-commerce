"""src/global_commerce/trade/import_manager.py — 수입 관리 (Phase 93)."""
from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 국가별 면세 한도 (USD)
_DUTY_FREE_THRESHOLD_USD: Dict[str, float] = {
    'US': 800.0,   # 2016년 이후 $800
    'CN': 50.0,    # 소액 면세 50위안 ≈ 7 USD, 실질적으로 엄격
    'JP': 10000.0, # 10,000엔 ≈ 66 USD
    'EU': 150.0,
    'KR': 150.0,   # 해외 직구 150 USD
    'DEFAULT': 150.0,
}

# HS Code 기반 관세율 (간략 mock)
_HS_DUTY_RATES: Dict[str, float] = {
    '8471': 0.0,   # 컴퓨터
    '8517': 0.0,   # 휴대폰
    '6109': 0.13,  # 티셔츠
    '6203': 0.13,  # 바지
    '6402': 0.13,  # 신발
    '9503': 0.08,  # 장난감
    '8525': 0.0,   # 카메라
    '3304': 0.08,  # 화장품
    '0901': 0.08,  # 커피
    'DEFAULT': 0.08,
}

# 부가세율
_VAT_RATE = 0.10


class ImportStatus(str, enum.Enum):
    PLACED = 'placed'
    PURCHASED = 'purchased'
    IN_TRANSIT = 'in_transit'
    CUSTOMS = 'customs'
    CLEARED = 'cleared'
    DELIVERED = 'delivered'
    CANCELLED = 'cancelled'


_VALID_TRANSITIONS: Dict[str, List[str]] = {
    ImportStatus.PLACED: [ImportStatus.PURCHASED, ImportStatus.CANCELLED],
    ImportStatus.PURCHASED: [ImportStatus.IN_TRANSIT, ImportStatus.CANCELLED],
    ImportStatus.IN_TRANSIT: [ImportStatus.CUSTOMS, ImportStatus.CANCELLED],
    ImportStatus.CUSTOMS: [ImportStatus.CLEARED, ImportStatus.CANCELLED],
    ImportStatus.CLEARED: [ImportStatus.DELIVERED],
    ImportStatus.DELIVERED: [],
    ImportStatus.CANCELLED: [],
}


@dataclass
class ImportOrder:
    """수입 주문."""
    order_id: str
    product_url: str
    source_country: str
    destination_country: str
    product_name: str
    quantity: int
    unit_price_usd: float
    hs_code: str
    status: ImportStatus = ImportStatus.PLACED
    customer_id: str = ''
    notes: str = ''
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total_price_usd(self) -> float:
        return round(self.unit_price_usd * self.quantity, 2)

    def to_dict(self) -> dict:
        return {
            'order_id': self.order_id,
            'product_url': self.product_url,
            'source_country': self.source_country,
            'destination_country': self.destination_country,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'unit_price_usd': self.unit_price_usd,
            'total_price_usd': self.total_price_usd,
            'hs_code': self.hs_code,
            'status': self.status.value,
            'customer_id': self.customer_id,
            'notes': self.notes,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class CustomsDutyCalculator:
    """관세/부가세 계산기 — HS Code 기반 관세율, 과세가격 계산, 면세 한도 체크."""

    def get_duty_rate(self, hs_code: str) -> float:
        """HS Code 기반 관세율 반환."""
        prefix4 = hs_code[:4] if hs_code else 'DEFAULT'
        return _HS_DUTY_RATES.get(prefix4, _HS_DUTY_RATES['DEFAULT'])

    def is_duty_free(self, total_price_usd: float, source_country: str) -> bool:
        """면세 한도 이하 여부 확인."""
        threshold = _DUTY_FREE_THRESHOLD_USD.get(source_country.upper(),
                                                  _DUTY_FREE_THRESHOLD_USD['DEFAULT'])
        return total_price_usd <= threshold

    def calculate(self, total_price_usd: float, hs_code: str,
                  source_country: str, usd_to_krw: float = 1350.0) -> dict:
        """관세 및 부가세 계산.

        Args:
            total_price_usd: 상품 총액 (USD)
            hs_code: HS 코드
            source_country: 원산지 국가 코드
            usd_to_krw: USD/KRW 환율

        Returns:
            계산 결과 딕셔너리
        """
        if self.is_duty_free(total_price_usd, source_country):
            return {
                'total_price_usd': total_price_usd,
                'duty_rate': 0.0,
                'customs_duty_krw': 0.0,
                'vat_krw': 0.0,
                'total_tax_krw': 0.0,
                'duty_free': True,
                'threshold_usd': _DUTY_FREE_THRESHOLD_USD.get(
                    source_country.upper(), _DUTY_FREE_THRESHOLD_USD['DEFAULT']),
            }

        total_krw = total_price_usd * usd_to_krw
        duty_rate = self.get_duty_rate(hs_code)
        customs_duty = round(total_krw * duty_rate, 0)
        vat_base = total_krw + customs_duty
        vat = round(vat_base * _VAT_RATE, 0)
        total_tax = customs_duty + vat

        return {
            'total_price_usd': total_price_usd,
            'total_price_krw': round(total_krw, 0),
            'duty_rate': duty_rate,
            'customs_duty_krw': customs_duty,
            'vat_rate': _VAT_RATE,
            'vat_krw': vat,
            'total_tax_krw': total_tax,
            'duty_free': False,
            'threshold_usd': _DUTY_FREE_THRESHOLD_USD.get(
                source_country.upper(), _DUTY_FREE_THRESHOLD_USD['DEFAULT']),
        }


class CustomsClearanceTracker:
    """통관 상태 추적."""

    def __init__(self):
        # {order_id: [event]}
        self._events: Dict[str, list] = {}

    def add_event(self, order_id: str, event_type: str, description: str = '') -> dict:
        """통관 이벤트 추가."""
        event = {
            'order_id': order_id,
            'event_type': event_type,
            'description': description,
            'timestamp': datetime.now().isoformat(),
        }
        if order_id not in self._events:
            self._events[order_id] = []
        self._events[order_id].append(event)
        return event

    def get_history(self, order_id: str) -> list:
        """통관 이력 조회."""
        return list(self._events.get(order_id, []))

    def get_latest(self, order_id: str) -> Optional[dict]:
        """최근 통관 이벤트 조회."""
        history = self.get_history(order_id)
        return history[-1] if history else None


class ImportManager:
    """수입 주문 관리 — 생성/조회/상태 관리."""

    def __init__(self):
        self._orders: Dict[str, ImportOrder] = {}
        self._duty_calc = CustomsDutyCalculator()
        self._customs_tracker = CustomsClearanceTracker()

    @property
    def duty_calculator(self) -> CustomsDutyCalculator:
        return self._duty_calc

    @property
    def customs_tracker(self) -> CustomsClearanceTracker:
        return self._customs_tracker

    def create(self, product_url: str, source_country: str,
               destination_country: str = 'KR', product_name: str = '',
               quantity: int = 1, unit_price_usd: float = 0.0,
               hs_code: str = 'DEFAULT', customer_id: str = '',
               notes: str = '') -> ImportOrder:
        """수입 주문 생성.

        Args:
            product_url: 상품 URL
            source_country: 출처 국가 코드
            destination_country: 목적지 국가 코드
            product_name: 상품명
            quantity: 수량
            unit_price_usd: 단가 (USD)
            hs_code: HS 코드
            customer_id: 고객 ID
            notes: 메모

        Returns:
            ImportOrder
        """
        order = ImportOrder(
            order_id=str(uuid.uuid4()),
            product_url=product_url,
            source_country=source_country.upper(),
            destination_country=destination_country.upper(),
            product_name=product_name,
            quantity=quantity,
            unit_price_usd=unit_price_usd,
            hs_code=hs_code,
            customer_id=customer_id,
            notes=notes,
        )
        self._orders[order.order_id] = order
        logger.info("수입 주문 생성: %s source=%s", order.order_id, source_country)
        return order

    def get(self, order_id: str) -> Optional[ImportOrder]:
        return self._orders.get(order_id)

    def transition(self, order_id: str, new_status: str) -> ImportOrder:
        """수입 주문 상태 전환.

        Args:
            order_id: 주문 ID
            new_status: 새 상태

        Returns:
            갱신된 ImportOrder
        """
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"수입 주문을 찾을 수 없습니다: {order_id}")

        try:
            new_status_enum = ImportStatus(new_status)
        except ValueError:
            raise ValueError(f"유효하지 않은 상태: {new_status}")

        allowed = _VALID_TRANSITIONS.get(order.status, [])
        if new_status_enum not in allowed:
            raise ValueError(
                f"허용되지 않은 상태 전환: {order.status.value} → {new_status}"
            )

        order.status = new_status_enum
        order.updated_at = datetime.now().isoformat()

        if new_status_enum == ImportStatus.CUSTOMS:
            self._customs_tracker.add_event(order_id, 'customs_arrived', '세관 도착')
        elif new_status_enum == ImportStatus.CLEARED:
            self._customs_tracker.add_event(order_id, 'customs_cleared', '통관 완료')

        logger.info("수입 주문 상태 변경: %s → %s", order_id, new_status)
        return order

    def list(self, status: Optional[str] = None,
             source_country: Optional[str] = None) -> List[ImportOrder]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status.value == status]
        if source_country:
            orders = [o for o in orders if o.source_country == source_country.upper()]
        return orders

    def calculate_customs(self, order_id: str, usd_to_krw: float = 1350.0) -> dict:
        """수입 주문의 관세 계산."""
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"수입 주문을 찾을 수 없습니다: {order_id}")
        return self._duty_calc.calculate(
            total_price_usd=order.total_price_usd,
            hs_code=order.hs_code,
            source_country=order.source_country,
            usd_to_krw=usd_to_krw,
        )
