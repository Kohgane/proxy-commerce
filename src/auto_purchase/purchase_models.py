"""src/auto_purchase/purchase_models.py — 자동 구매 데이터 모델 (Phase 96)."""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


class PurchaseStatus(str, enum.Enum):
    """구매 상태 열거형."""
    PENDING = 'pending'
    SOURCE_SELECTED = 'source_selected'
    PURCHASING = 'purchasing'
    PAYMENT_PROCESSING = 'payment_processing'
    CONFIRMED = 'confirmed'
    SHIPPED = 'shipped'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    ON_HOLD = 'on_hold'


class Priority(str, enum.Enum):
    """구매 우선순위."""
    URGENT = 'urgent'
    NORMAL = 'normal'
    LOW = 'low'


@dataclass
class PurchaseOrder:
    """자동 구매 주문 데이터 모델."""
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_marketplace: str = ''          # amazon_us, amazon_jp, taobao, alibaba
    source_product_id: str = ''           # ASIN / 상품 ID
    quantity: int = 1
    unit_price: float = 0.0
    currency: str = 'USD'
    status: PurchaseStatus = PurchaseStatus.PENDING
    priority: Priority = Priority.NORMAL
    customer_order_id: str = ''           # 원본 고객 주문 ID
    shipping_address: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tracking_number: str = ''
    confirmation_code: str = ''
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ''
    metadata: Dict = field(default_factory=dict)

    def update_status(self, new_status: PurchaseStatus, error: str = '') -> None:
        """상태를 업데이트한다."""
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        if error:
            self.error_message = error

    @property
    def total_price(self) -> float:
        return round(self.unit_price * self.quantity, 2)


@dataclass
class SourceOption:
    """소스 옵션 (구매 후보)."""
    marketplace: str = ''                 # amazon_us, amazon_jp, taobao, alibaba
    product_id: str = ''
    title: str = ''
    price: float = 0.0
    currency: str = 'USD'
    availability: bool = True
    stock_quantity: int = 0
    estimated_delivery_days: int = 0
    seller_rating: float = 0.0            # 0.0 ~ 5.0
    shipping_cost: float = 0.0
    url: str = ''
    moq: int = 1                          # 최소 주문 수량 (1688 등)

    @property
    def total_cost(self) -> float:
        return round(self.price + self.shipping_cost, 2)


@dataclass
class PurchaseResult:
    """구매 결과."""
    success: bool = False
    order_id: str = ''
    confirmation_code: str = ''
    estimated_delivery: Optional[datetime] = None
    actual_cost: float = 0.0
    currency: str = 'USD'
    error_message: str = ''
    marketplace: str = ''
    tracking_number: str = ''


@dataclass
class PurchaseMetrics:
    """구매 성과 메트릭."""
    total_orders: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    pending_orders: int = 0
    success_rate: float = 0.0
    avg_purchase_time_seconds: float = 0.0
    total_spend: float = 0.0
    currency: str = 'USD'
    daily_stats: Dict = field(default_factory=dict)
    marketplace_breakdown: Dict = field(default_factory=dict)

    def recalculate(self) -> None:
        """지표를 재계산한다."""
        total = self.successful_orders + self.failed_orders
        self.total_orders = total + self.pending_orders
        self.success_rate = (self.successful_orders / total) if total > 0 else 0.0


@dataclass
class PaymentRecord:
    """결제 내역."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ''
    method_id: str = ''
    amount: float = 0.0
    currency: str = 'USD'
    status: str = 'completed'             # completed, failed, refunded
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    receipt_url: str = ''
    metadata: Dict = field(default_factory=dict)
