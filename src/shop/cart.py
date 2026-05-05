"""src/shop/cart.py — 세션 기반 카트 (Phase 131).

- Flask session (server-side + cookie) 기반
- 비로그인 게스트 체크아웃 지원
- add / update / remove / clear / summary
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_SESSION_KEY = "shop_cart"
_FREE_SHIPPING_THRESHOLD_KRW = 50_000  # 이 금액 이상 주문 시 배송비 무료


def _get_session():
    """Flask session 반환 (graceful import)."""
    try:
        from flask import session
        return session
    except RuntimeError:
        return {}


class Cart:
    """세션 기반 장바구니."""

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # 내부: 세션 읽기/쓰기
    # ------------------------------------------------------------------

    def _read(self) -> Dict:
        """세션에서 카트 데이터 읽기."""
        sess = _get_session()
        data = sess.get(_SESSION_KEY)
        if not isinstance(data, dict):
            return {}
        return data

    def _write(self, data: dict) -> None:
        """세션에 카트 데이터 쓰기."""
        try:
            from flask import session
            session[_SESSION_KEY] = data
            session.modified = True
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def add(self, slug: str, qty: int = 1, options: Optional[Dict] = None) -> None:
        """상품 추가. 이미 있으면 수량 증가."""
        if qty <= 0:
            return
        data = self._read()
        key = self._item_key(slug, options or {})
        if key in data:
            data[key]["qty"] = data[key].get("qty", 0) + qty
        else:
            data[key] = {"slug": slug, "qty": qty, "options": options or {}}
        self._write(data)

    def update(self, slug: str, qty: int, options: Optional[Dict] = None) -> None:
        """수량 업데이트. qty <= 0 이면 제거."""
        data = self._read()
        key = self._item_key(slug, options or {})
        if qty <= 0:
            data.pop(key, None)
        else:
            if key in data:
                data[key]["qty"] = qty
            else:
                data[key] = {"slug": slug, "qty": qty, "options": options or {}}
        self._write(data)

    def remove(self, slug: str, options: Optional[Dict] = None) -> None:
        """상품 제거."""
        data = self._read()
        key = self._item_key(slug, options or {})
        data.pop(key, None)
        self._write(data)

    def clear(self) -> None:
        """카트 비우기."""
        self._write({})

    def items(self) -> List[Dict]:
        """카트 아이템 목록 + 상품 정보 병합."""
        data = self._read()
        if not data:
            return []

        try:
            from .catalog import get_catalog
            catalog = get_catalog()
        except Exception:
            catalog = None

        result = []
        for _key, item in data.items():
            slug = item.get("slug", "")
            qty = item.get("qty", 1)
            options = item.get("options", {})

            product_info: Dict = {"slug": slug, "title_ko": slug, "price_krw": 0, "thumbnail_url": "", "shipping_fee_krw": 0}
            if catalog:
                p = catalog.get_by_slug(slug)
                if p:
                    product_info = {
                        "slug": p.slug,
                        "title_ko": p.title_ko,
                        "price_krw": p.sale_price_krw if p.sale_price_krw else p.price_krw,
                        "thumbnail_url": p.thumbnail_url,
                        "shipping_fee_krw": p.shipping_fee_krw,
                        "stock_qty": p.stock_qty,
                    }

            result.append({
                **product_info,
                "qty": qty,
                "options": options,
                "line_total": product_info.get("price_krw", 0) * qty,
            })
        return result

    def count(self) -> int:
        """카트 총 수량."""
        data = self._read()
        return sum(item.get("qty", 0) for item in data.values())

    def summary(self) -> Dict:
        """카트 합계 계산.

        Returns:
            {
              "items": [...],
              "subtotal_krw": int,
              "shipping_fee_krw": int,
              "total_krw": int,
              "item_count": int,
            }
        """
        cart_items = self.items()
        subtotal = sum(i.get("line_total", 0) for i in cart_items)
        # 배송비: 가장 높은 배송비 단일 적용 (아이템별 합산 X)
        shipping_fees = [i.get("shipping_fee_krw", 0) for i in cart_items if i.get("shipping_fee_krw", 0) > 0]
        shipping_fee = max(shipping_fees) if shipping_fees else 0
        # 무료 배송 임계값 이상이면 배송비 무료
        if subtotal >= _FREE_SHIPPING_THRESHOLD_KRW:
            shipping_fee = 0

        return {
            "items": cart_items,
            "subtotal_krw": subtotal,
            "shipping_fee_krw": shipping_fee,
            "total_krw": subtotal + shipping_fee,
            "item_count": self.count(),
        }

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _item_key(slug: str, options: dict) -> str:
        """슬러그 + 옵션 조합 키."""
        if not options:
            return slug
        opts_str = ",".join(f"{k}={v}" for k, v in sorted(options.items()))
        return f"{slug}|{opts_str}"


def get_cart() -> Cart:
    """현재 요청의 Cart 인스턴스 반환."""
    return Cart()
