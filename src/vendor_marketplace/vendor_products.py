"""src/vendor_marketplace/vendor_products.py — 판매자 상품 관리 (Phase 98)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .vendor_models import VendorTier, TIER_PRODUCT_LIMITS

logger = logging.getLogger(__name__)

# 상품 심사 상태
PRODUCT_STATUSES = ['draft', 'pending_review', 'approved', 'listed', 'rejected', 'delisted']

# 금지어 목록 (mock)
_FORBIDDEN_WORDS = [
    '도박', '음란', '마약', '불법', '사기', '위조', '짝퉁', 'replica',
    'counterfeit', 'fake', 'illegal',
]

# 허용 카테고리
_ALLOWED_CATEGORIES = [
    'electronics', 'fashion', 'beauty', 'food', 'sports', 'toys',
    'home', 'book', 'auto', 'pet', 'health', 'baby', 'office', 'other',
]


class ProductApprovalService:
    """상품 등록 심사 — 금지어 필터, 카테고리 적합성, 가격 적정성."""

    MIN_PRICE = 100          # 최소 판매가 (원)
    MAX_PRICE = 100_000_000  # 최대 판매가 (원)

    def check(self, product: dict) -> dict:
        """상품 심사 실행. 결과: {'passed': bool, 'issues': list}."""
        issues = []

        # 금지어 필터
        text_fields = [
            product.get('name', ''),
            product.get('description', ''),
        ]
        for text in text_fields:
            for word in _FORBIDDEN_WORDS:
                if word.lower() in text.lower():
                    issues.append(f'금지어 포함: "{word}"')

        # 카테고리 적합성
        category = product.get('category', '')
        if category and category not in _ALLOWED_CATEGORIES:
            issues.append(f'허용되지 않은 카테고리: {category}')

        # 가격 적정성
        price = product.get('price', 0)
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = 0
        if price < self.MIN_PRICE:
            issues.append(f'판매가가 최솟값({self.MIN_PRICE}원) 미만')
        if price > self.MAX_PRICE:
            issues.append(f'판매가가 최댓값({self.MAX_PRICE:,}원) 초과')

        # 이미지 검증 (mock)
        images = product.get('images', [])
        if not images:
            issues.append('상품 이미지 없음')

        return {'passed': len(issues) == 0, 'issues': issues}


class VendorProductRestriction:
    """판매자 티어별 상품 등록 수 제한."""

    def get_limit(self, tier: str) -> Optional[int]:
        return TIER_PRODUCT_LIMITS.get(tier)

    def can_add_product(self, tier: str, current_count: int) -> bool:
        limit = self.get_limit(tier)
        if limit is None:
            return True  # enterprise = 무제한
        return current_count < limit


class VendorProductManager:
    """판매자별 상품 CRUD 및 승인 워크플로."""

    def __init__(self) -> None:
        self._products: Dict[str, dict] = {}              # product_id → product
        self._vendor_products: Dict[str, List[str]] = {}  # vendor_id → [product_id]
        self._approval = ProductApprovalService()
        self._restriction = VendorProductRestriction()

    # ── 상품 등록 ─────────────────────────────────────────────────────────

    def add_product(
        self,
        vendor_id: str,
        vendor_tier: str,
        name: str,
        price: float,
        category: str = 'other',
        description: str = '',
        images: Optional[List[str]] = None,
        stock: int = 0,
        metadata: Optional[dict] = None,
    ) -> dict:
        """상품 등록 (draft 상태로 시작)."""
        current_count = len(self._vendor_products.get(vendor_id, []))
        if not self._restriction.can_add_product(vendor_tier, current_count):
            limit = self._restriction.get_limit(vendor_tier)
            raise PermissionError(
                f'상품 등록 한도 초과 ({current_count}/{limit}): 티어 업그레이드 필요'
            )

        product_id = str(uuid.uuid4())
        product = {
            'product_id': product_id,
            'vendor_id': vendor_id,
            'name': name,
            'price': price,
            'category': category,
            'description': description,
            'images': images or [],
            'stock': stock,
            'status': 'draft',
            'approval_issues': [],
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'metadata': metadata or {},
        }
        self._products[product_id] = product
        self._vendor_products.setdefault(vendor_id, []).append(product_id)
        logger.info('상품 등록: %s (판매자: %s)', product_id, vendor_id)
        return product

    # ── 상품 수정 ─────────────────────────────────────────────────────────

    def update_product(self, vendor_id: str, product_id: str, **kwargs) -> dict:
        """상품 정보 수정."""
        product = self._get_or_raise(vendor_id, product_id)
        for key, value in kwargs.items():
            if key in product and key not in ('product_id', 'vendor_id', 'created_at'):
                product[key] = value
        product['updated_at'] = datetime.now(timezone.utc).isoformat()
        # 수정 시 draft로 되돌림 (재심사 필요)
        if product['status'] == 'listed':
            product['status'] = 'draft'
        return product

    # ── 상품 삭제 ─────────────────────────────────────────────────────────

    def delete_product(self, vendor_id: str, product_id: str) -> bool:
        """상품 삭제."""
        self._get_or_raise(vendor_id, product_id)
        del self._products[product_id]
        self._vendor_products[vendor_id].remove(product_id)
        return True

    # ── 심사 워크플로 ─────────────────────────────────────────────────────

    def submit_for_review(self, vendor_id: str, product_id: str) -> dict:
        """상품 심사 제출 (draft → pending_review)."""
        product = self._get_or_raise(vendor_id, product_id)
        if product['status'] not in ('draft', 'rejected'):
            raise ValueError(f'심사 제출 불가 상태: {product["status"]}')
        product['status'] = 'pending_review'
        product['updated_at'] = datetime.now(timezone.utc).isoformat()
        return product

    def approve_product(self, product_id: str) -> dict:
        """상품 승인 (pending_review → approved → listed)."""
        product = self._products.get(product_id)
        if product is None:
            raise KeyError(f'상품 없음: {product_id}')
        if product['status'] != 'pending_review':
            raise ValueError(f'승인 불가 상태: {product["status"]}')

        result = self._approval.check(product)
        if not result['passed']:
            product['status'] = 'rejected'
            product['approval_issues'] = result['issues']
            product['updated_at'] = datetime.now(timezone.utc).isoformat()
            return product

        product['status'] = 'listed'
        product['approval_issues'] = []
        product['updated_at'] = datetime.now(timezone.utc).isoformat()
        return product

    def reject_product(self, product_id: str, reason: str = '') -> dict:
        """상품 거절."""
        product = self._products.get(product_id)
        if product is None:
            raise KeyError(f'상품 없음: {product_id}')
        product['status'] = 'rejected'
        product['approval_issues'] = [reason] if reason else ['관리자 거절']
        product['updated_at'] = datetime.now(timezone.utc).isoformat()
        return product

    # ── 조회 ──────────────────────────────────────────────────────────────

    def get_product(self, product_id: str) -> Optional[dict]:
        return self._products.get(product_id)

    def list_vendor_products(
        self, vendor_id: str, status: Optional[str] = None
    ) -> List[dict]:
        product_ids = self._vendor_products.get(vendor_id, [])
        products = [self._products[pid] for pid in product_ids if pid in self._products]
        if status:
            products = [p for p in products if p['status'] == status]
        return products

    def _get_or_raise(self, vendor_id: str, product_id: str) -> dict:
        product = self._products.get(product_id)
        if product is None or product['vendor_id'] != vendor_id:
            raise KeyError(f'상품 없음 또는 권한 없음: {product_id}')
        return product


class VendorInventorySync:
    """판매자별 재고 관리 — 기존 InventorySyncManager 연동."""

    def __init__(self) -> None:
        self._stock: Dict[str, int] = {}   # product_id → stock_qty

    def set_stock(self, product_id: str, quantity: int) -> None:
        self._stock[product_id] = max(0, quantity)

    def adjust_stock(self, product_id: str, delta: int) -> int:
        current = self._stock.get(product_id, 0)
        new_qty = max(0, current + delta)
        self._stock[product_id] = new_qty
        return new_qty

    def get_stock(self, product_id: str) -> int:
        return self._stock.get(product_id, 0)

    def get_low_stock_alerts(self, threshold: int = 5) -> List[dict]:
        return [
            {'product_id': pid, 'stock': qty}
            for pid, qty in self._stock.items()
            if qty <= threshold
        ]

    def bulk_sync(self, stock_map: Dict[str, int]) -> None:
        for product_id, qty in stock_map.items():
            self.set_stock(product_id, qty)
