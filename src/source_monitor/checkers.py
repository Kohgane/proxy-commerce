"""src/source_monitor/checkers.py — 소싱처 상품 상태 체커 (Phase 108).

SourceChecker ABC + 마켓플레이스별 구현체 (모두 mock)
"""
from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from .engine import SourceProduct, SourceType, StockStatus

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    source_product_id: str
    checked_at: str
    is_alive: bool
    price: float
    stock_status: StockStatus
    seller_active: bool
    changes_detected: bool
    raw_data: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.checked_at:
            self.checked_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'source_product_id': self.source_product_id,
            'checked_at': self.checked_at,
            'is_alive': self.is_alive,
            'price': self.price,
            'stock_status': self.stock_status.value if hasattr(self.stock_status, 'value') else self.stock_status,
            'seller_active': self.seller_active,
            'changes_detected': self.changes_detected,
            'raw_data': self.raw_data,
        }


class SourceChecker(ABC):
    """소싱처 상품 체커 추상 기반 클래스."""

    @abstractmethod
    def check(self, product: SourceProduct) -> CheckResult:
        """상품 상태 체크."""

    def _build_result(
        self,
        product: SourceProduct,
        is_alive: bool = True,
        price: Optional[float] = None,
        stock_status: StockStatus = StockStatus.in_stock,
        seller_active: bool = True,
        raw_data: Optional[dict] = None,
    ) -> CheckResult:
        price = price if price is not None else product.current_price
        changes = price != product.current_price or stock_status != product.stock_status
        return CheckResult(
            source_product_id=product.source_product_id,
            checked_at=datetime.now(tz=timezone.utc).isoformat(),
            is_alive=is_alive,
            price=price,
            stock_status=stock_status,
            seller_active=seller_active,
            changes_detected=changes,
            raw_data=raw_data or {},
        )


class AmazonSourceChecker(SourceChecker):
    """Amazon US/JP 상품 상태 체크 mock."""

    def check(self, product: SourceProduct) -> CheckResult:
        logger.debug("Amazon 체크: %s", product.source_product_id)
        # mock: 가격 소폭 변동 시뮬레이션
        mock_price = round(product.current_price * random.uniform(0.98, 1.02), 2)
        mock_stock = random.choice([StockStatus.in_stock, StockStatus.in_stock, StockStatus.low_stock])
        return self._build_result(
            product,
            is_alive=True,
            price=mock_price,
            stock_status=mock_stock,
            seller_active=True,
            raw_data={'marketplace': 'amazon', 'asin': product.metadata.get('asin', '')},
        )


class TaobaoSourceChecker(SourceChecker):
    """타오바오 상품 상태 체크 mock."""

    def check(self, product: SourceProduct) -> CheckResult:
        logger.debug("타오바오 체크: %s", product.source_product_id)
        mock_price = round(product.current_price * random.uniform(0.97, 1.03), 2)
        return self._build_result(
            product,
            is_alive=True,
            price=mock_price,
            stock_status=StockStatus.in_stock,
            seller_active=True,
            raw_data={'marketplace': 'taobao', 'item_id': product.metadata.get('item_id', '')},
        )


class Alibaba1688SourceChecker(SourceChecker):
    """1688 상품 상태 체크 mock."""

    def check(self, product: SourceProduct) -> CheckResult:
        logger.debug("1688 체크: %s", product.source_product_id)
        mock_price = round(product.current_price * random.uniform(0.95, 1.05), 2)
        return self._build_result(
            product,
            is_alive=True,
            price=mock_price,
            stock_status=StockStatus.in_stock,
            seller_active=True,
            raw_data={'marketplace': '1688', 'offer_id': product.metadata.get('offer_id', '')},
        )


class CoupangSourceChecker(SourceChecker):
    """쿠팡 상품 상태 체크 mock."""

    def check(self, product: SourceProduct) -> CheckResult:
        logger.debug("쿠팡 체크: %s", product.source_product_id)
        mock_price = round(product.current_price * random.uniform(0.99, 1.01), 2)
        return self._build_result(
            product,
            is_alive=True,
            price=mock_price,
            stock_status=StockStatus.in_stock,
            seller_active=True,
            raw_data={'marketplace': 'coupang', 'item_id': product.metadata.get('item_id', '')},
        )


class NaverSourceChecker(SourceChecker):
    """네이버 상품 상태 체크 mock."""

    def check(self, product: SourceProduct) -> CheckResult:
        logger.debug("네이버 체크: %s", product.source_product_id)
        mock_price = round(product.current_price * random.uniform(0.99, 1.01), 2)
        return self._build_result(
            product,
            is_alive=True,
            price=mock_price,
            stock_status=StockStatus.in_stock,
            seller_active=True,
            raw_data={'marketplace': 'naver', 'product_id': product.metadata.get('product_id', '')},
        )


class CustomSourceChecker(SourceChecker):
    """커스텀 소싱처 상품 상태 체크 mock."""

    def check(self, product: SourceProduct) -> CheckResult:
        logger.debug("커스텀 소싱처 체크: %s", product.source_product_id)
        return self._build_result(
            product,
            is_alive=True,
            price=product.current_price,
            stock_status=StockStatus.in_stock,
            seller_active=True,
            raw_data={'marketplace': 'custom'},
        )


_CHECKER_MAP: Dict[SourceType, type] = {
    SourceType.amazon_us: AmazonSourceChecker,
    SourceType.amazon_jp: AmazonSourceChecker,
    SourceType.taobao: TaobaoSourceChecker,
    SourceType.alibaba_1688: Alibaba1688SourceChecker,
    SourceType.coupang: CoupangSourceChecker,
    SourceType.naver: NaverSourceChecker,
    SourceType.custom: CustomSourceChecker,
}


def get_checker(source_type: SourceType) -> SourceChecker:
    """소싱처 유형에 맞는 체커 반환."""
    checker_cls = _CHECKER_MAP.get(source_type, CustomSourceChecker)
    return checker_cls()
