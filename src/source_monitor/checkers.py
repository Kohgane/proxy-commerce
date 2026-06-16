"""src/source_monitor/checkers.py — 소싱처 상품 상태 체커 (Phase 108 → 205 실연동).

SourceChecker ABC + 마켓플레이스별 구현체.
가짜 랜덤 가격 시뮬레이션을 제거하고, source_url에서 범용 스크래퍼로 실 가격/재고를
추출한다(키 불필요). 추출 실패·URL 없음·ADAPTER_DRY_RUN=1 시에는 가짜 변동 대신
'변화 없음'으로 처리해 거짓 알림을 만들지 않는다.
"""
from __future__ import annotations

import logging
import os
from abc import ABC
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
    """소싱처 상품 체커 기반 클래스.

    하위 클래스는 `marketplace`(raw_data 태그)와 선택적으로 `_meta_tags()`만 정의한다.
    실 가격/재고 추출은 공통 `check()`가 범용 스크래퍼로 수행한다.
    """

    marketplace: str = "custom"

    def check(self, product: SourceProduct) -> CheckResult:
        """source_url에서 실 가격/재고를 조회해 상태를 평가한다."""
        live = self._scrape_live(product)
        raw: dict = {"marketplace": self.marketplace}
        raw.update(self._meta_tags(product))

        if live and live.get("price") is not None:
            price = live["price"]
            in_stock = live.get("in_stock")
            if in_stock is None:
                stock = product.stock_status
            else:
                stock = StockStatus.in_stock if in_stock else StockStatus.out_of_stock
            raw["live"] = True
            if live.get("method"):
                raw["extraction_method"] = live["method"]
        else:
            # 실데이터 없음 → 가짜 변동 만들지 않고 현 상태 유지
            price = product.current_price
            stock = product.stock_status
            raw["live"] = False

        return self._build_result(
            product,
            is_alive=True,
            price=price,
            stock_status=stock,
            seller_active=True,
            raw_data=raw,
        )

    def _meta_tags(self, product: SourceProduct) -> dict:
        """마켓플레이스별 raw_data 식별자(자식이 오버라이드)."""
        return {}

    def _scrape_live(self, product: SourceProduct) -> Optional[dict]:
        """source_url에서 실 가격/재고 추출. 실패·URL없음·DRY_RUN 시 None."""
        url = (getattr(product, "source_url", "") or "").strip()
        if not url.startswith(("http://", "https://")):
            return None
        if os.getenv("ADAPTER_DRY_RUN") == "1":
            return None
        try:
            from src.collectors.universal_scraper import UniversalScraper

            sp = UniversalScraper().fetch(url)
            price = float(sp.price) if sp.price is not None else None
            if price is None and sp.in_stock is None:
                return None
            return {"price": price, "in_stock": sp.in_stock, "method": sp.extraction_method}
        except Exception as exc:
            logger.warning("소싱 실가격 조회 실패 (%s): %s", url[:80], exc)
            return None

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
    """Amazon US/JP 상품 상태 체크 (실 스크래핑)."""

    marketplace = "amazon"

    def _meta_tags(self, product: SourceProduct) -> dict:
        return {"asin": product.metadata.get("asin", "")}


class TaobaoSourceChecker(SourceChecker):
    """타오바오 상품 상태 체크 (실 스크래핑)."""

    marketplace = "taobao"

    def _meta_tags(self, product: SourceProduct) -> dict:
        return {"item_id": product.metadata.get("item_id", "")}


class Alibaba1688SourceChecker(SourceChecker):
    """1688 상품 상태 체크 (실 스크래핑)."""

    marketplace = "1688"

    def _meta_tags(self, product: SourceProduct) -> dict:
        return {"offer_id": product.metadata.get("offer_id", "")}


class CoupangSourceChecker(SourceChecker):
    """쿠팡 상품 상태 체크 (실 스크래핑)."""

    marketplace = "coupang"

    def _meta_tags(self, product: SourceProduct) -> dict:
        return {"item_id": product.metadata.get("item_id", "")}


class NaverSourceChecker(SourceChecker):
    """네이버 상품 상태 체크 (실 스크래핑)."""

    marketplace = "naver"

    def _meta_tags(self, product: SourceProduct) -> dict:
        return {"product_id": product.metadata.get("product_id", "")}


class CustomSourceChecker(SourceChecker):
    """커스텀 소싱처 상품 상태 체크 (실 스크래핑)."""

    marketplace = "custom"


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
