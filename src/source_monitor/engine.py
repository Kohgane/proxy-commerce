"""src/source_monitor/engine.py — 소싱처 모니터링 엔진 (Phase 108).

SourceMonitorEngine: 소싱처 등록 → 주기적 상태 체크 → 변동 감지 → 자동 대응 → 알림 → 이력 관리
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    amazon_us = 'amazon_us'
    amazon_jp = 'amazon_jp'
    taobao = 'taobao'
    alibaba_1688 = 'alibaba_1688'
    coupang = 'coupang'
    naver = 'naver'
    custom = 'custom'


class SourceStatus(str, Enum):
    active = 'active'
    price_changed = 'price_changed'
    out_of_stock = 'out_of_stock'
    listing_removed = 'listing_removed'
    seller_inactive = 'seller_inactive'
    restricted = 'restricted'
    unknown = 'unknown'


class StockStatus(str, Enum):
    in_stock = 'in_stock'
    low_stock = 'low_stock'
    out_of_stock = 'out_of_stock'
    preorder = 'preorder'
    discontinued = 'discontinued'


@dataclass
class SourceProduct:
    source_product_id: str
    source_type: SourceType
    source_url: str
    seller_id: str
    seller_name: str
    my_product_id: str
    title: str
    current_price: float
    original_price: float
    currency: str = 'KRW'
    stock_status: StockStatus = StockStatus.in_stock
    is_alive: bool = True
    last_checked_at: Optional[str] = None
    check_interval_minutes: int = 120
    consecutive_failures: int = 0
    status: SourceStatus = SourceStatus.active
    registered_at: str = ''
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'source_product_id': self.source_product_id,
            'source_type': self.source_type.value if hasattr(self.source_type, 'value') else self.source_type,
            'source_url': self.source_url,
            'seller_id': self.seller_id,
            'seller_name': self.seller_name,
            'my_product_id': self.my_product_id,
            'title': self.title,
            'current_price': self.current_price,
            'original_price': self.original_price,
            'currency': self.currency,
            'stock_status': self.stock_status.value if hasattr(self.stock_status, 'value') else self.stock_status,
            'is_alive': self.is_alive,
            'last_checked_at': self.last_checked_at,
            'check_interval_minutes': self.check_interval_minutes,
            'consecutive_failures': self.consecutive_failures,
            'status': self.status.value if hasattr(self.status, 'value') else self.status,
            'registered_at': self.registered_at,
            'metadata': self.metadata,
        }


class SourceMonitorEngine:
    """소싱처 모니터링 오케스트레이터."""

    def __init__(self):
        self._products: Dict[str, SourceProduct] = {}

    # ── 등록 / 조회 / 수정 / 삭제 ─────────────────────────────────────────

    def register_product(self, data: dict) -> SourceProduct:
        """소싱처 상품 등록."""
        sp_id = data.get('source_product_id') or str(uuid.uuid4())
        source_type_raw = data.get('source_type', 'custom')
        try:
            st = SourceType(source_type_raw)
        except ValueError:
            st = SourceType.custom

        product = SourceProduct(
            source_product_id=sp_id,
            source_type=st,
            source_url=data.get('source_url', ''),
            seller_id=data.get('seller_id', ''),
            seller_name=data.get('seller_name', ''),
            my_product_id=data.get('my_product_id', ''),
            title=data.get('title', ''),
            current_price=float(data.get('current_price', 0)),
            original_price=float(data.get('original_price', 0)),
            currency=data.get('currency', 'KRW'),
            stock_status=StockStatus(data.get('stock_status', 'in_stock'))
            if data.get('stock_status') in [s.value for s in StockStatus]
            else StockStatus.in_stock,
            check_interval_minutes=int(data.get('check_interval_minutes', 120)),
            metadata=data.get('metadata', {}),
        )
        self._products[sp_id] = product
        logger.info("소싱처 상품 등록: %s (%s)", sp_id, product.title)
        return product

    def get_product(self, source_product_id: str) -> Optional[SourceProduct]:
        return self._products.get(source_product_id)

    def update_product(self, source_product_id: str, data: dict) -> Optional[SourceProduct]:
        product = self._products.get(source_product_id)
        if not product:
            return None
        for key, value in data.items():
            if hasattr(product, key):
                setattr(product, key, value)
        return product

    def delete_product(self, source_product_id: str) -> bool:
        if source_product_id in self._products:
            del self._products[source_product_id]
            return True
        return False

    def list_products(self, status: Optional[str] = None) -> List[SourceProduct]:
        products = list(self._products.values())
        if status:
            products = [p for p in products if p.status.value == status or p.status == status]
        return products

    # ── 체크 오케스트레이션 ───────────────────────────────────────────────

    def run_check(self, source_product_id: str) -> dict:
        """단일 상품 즉시 체크."""
        from .checkers import get_checker
        from .change_detector import ChangeDetector
        from .auto_deactivation import AutoDeactivationService

        product = self._products.get(source_product_id)
        if not product:
            return {'error': 'product not found'}

        checker = get_checker(product.source_type)
        result = checker.check(product)

        # 변동 감지
        detector = ChangeDetector()
        events = detector.detect(product, result)

        # 자동 대응
        deactivation_svc = AutoDeactivationService()
        actions_taken = []
        for event in events:
            action = deactivation_svc.process_event(event, product)
            if action:
                actions_taken.append(action)

        # 상태 업데이트
        product.last_checked_at = result.checked_at
        if result.is_alive:
            product.consecutive_failures = 0
            product.is_alive = True
            product.current_price = result.price
            product.stock_status = result.stock_status
        else:
            product.consecutive_failures += 1
            if product.consecutive_failures >= 3:
                product.is_alive = False
                product.status = SourceStatus.listing_removed

        return {
            'source_product_id': source_product_id,
            'check_result': result.to_dict(),
            'events': [e.to_dict() for e in events],
            'actions_taken': actions_taken,
        }

    def get_summary(self) -> dict:
        """전체 소싱처 현황 요약."""
        products = list(self._products.values())
        total = len(products)
        active = sum(1 for p in products if p.status == SourceStatus.active)
        problem = sum(1 for p in products if p.status not in (SourceStatus.active, SourceStatus.unknown))
        inactive = sum(1 for p in products if not p.is_alive)
        return {
            'total': total,
            'active': active,
            'problem': problem,
            'inactive': inactive,
            'by_source_type': self._count_by_source_type(products),
        }

    def _count_by_source_type(self, products: List[SourceProduct]) -> dict:
        counts: Dict[str, int] = {}
        for p in products:
            key = p.source_type.value if hasattr(p.source_type, 'value') else str(p.source_type)
            counts[key] = counts.get(key, 0) + 1
        return counts
