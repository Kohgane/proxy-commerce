"""커머스 용어집 — 번역 시 용어 통일."""

import logging

logger = logging.getLogger(__name__)

_GLOSSARY = {
    'Free Shipping': '무료배송',
    'In Stock': '재고있음',
    'Out of Stock': '품절',
    'New Arrival': '신상품',
    'Best Seller': '베스트셀러',
    'Sale': '할인',
    'Discount': '할인',
    'Limited Edition': '한정판',
    'Pre-order': '사전예약',
    'Bundle': '묶음상품',
}


class CommerceGlossary:
    """커머스 용어집 적용."""

    def __init__(self, custom_terms: dict = None):
        self._terms = dict(_GLOSSARY)
        if custom_terms:
            self._terms.update(custom_terms)

    def apply(self, text: str) -> str:
        """텍스트에 용어집 적용."""
        result = text
        for eng, kor in self._terms.items():
            result = result.replace(eng, kor)
        return result

    def add_term(self, source: str, target: str) -> None:
        """용어 추가."""
        self._terms[source] = target

    def list_terms(self) -> dict:
        """현재 용어집 반환."""
        return dict(self._terms)
