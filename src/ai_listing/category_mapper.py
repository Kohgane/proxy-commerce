"""src/ai_listing/category_mapper.py — 마켓별 카테고리 매핑 (Phase 149).

Phase 143 auto_publish.py의 카테고리 맵을 확장한 전용 매핑 테이블.
"""
from __future__ import annotations

from typing import Dict, Optional


# ── 마켓별 카테고리 코드 매핑 ────────────────────────────────────────────────
# key: 범용 카테고리명 → value: 마켓 카테고리 코드

_COUPANG_CATEGORY_MAP: Dict[str, str] = {
    "전자기기": "56137",
    "스마트폰/태블릿": "56137",
    "뷰티": "56138",
    "화장품": "56138",
    "패션": "56139",
    "의류": "56139",
    "스포츠": "56140",
    "주방용품": "56141",
    "반려동물": "56142",
    "건강식품": "56143",
    "식품": "56143",
    "가구/인테리어": "56144",
    "가구": "56144",
    "완구": "56145",
    "도서": "56146",
    "default": "56137",
}

_SMARTSTORE_CATEGORY_MAP: Dict[str, str] = {
    "전자기기": "50000803",
    "스마트폰/태블릿": "50000803",
    "뷰티": "50000819",
    "화장품": "50000819",
    "패션": "50000816",
    "의류": "50000816",
    "스포츠": "50000812",
    "주방용품": "50000806",
    "반려동물": "50000827",
    "건강식품": "50000818",
    "식품": "50000818",
    "가구/인테리어": "50000804",
    "가구": "50000804",
    "완구": "50000830",
    "도서": "50000835",
    "default": "50000803",
}

_ELEVENST_CATEGORY_MAP: Dict[str, str] = {
    "전자기기": "1001",
    "스마트폰/태블릿": "1001",
    "뷰티": "1002",
    "화장품": "1002",
    "패션": "1003",
    "의류": "1003",
    "스포츠": "1004",
    "주방용품": "1005",
    "반려동물": "1006",
    "건강식품": "1007",
    "식품": "1007",
    "가구/인테리어": "1008",
    "가구": "1008",
    "완구": "1009",
    "도서": "1010",
    "default": "1001",
}

_GMARKET_CATEGORY_MAP: Dict[str, str] = {
    "전자기기": "60010001",
    "스마트폰/태블릿": "60010001",
    "뷰티": "60010002",
    "화장품": "60010002",
    "패션": "60010003",
    "의류": "60010003",
    "스포츠": "60010004",
    "주방용품": "60010005",
    "반려동물": "60010006",
    "건강식품": "60010007",
    "식품": "60010007",
    "가구/인테리어": "60010008",
    "가구": "60010008",
    "완구": "60010009",
    "도서": "60010010",
    "default": "60010001",
}

_MARKET_CATEGORY_MAPS: Dict[str, Dict[str, str]] = {
    "coupang": _COUPANG_CATEGORY_MAP,
    "smartstore": _SMARTSTORE_CATEGORY_MAP,
    "11st": _ELEVENST_CATEGORY_MAP,
    "gmarket": _GMARKET_CATEGORY_MAP,
}


def get_category_code(category: str, market: str) -> str:
    """범용 카테고리명 → 마켓 카테고리 코드 반환.

    Args:
        category: 범용 카테고리 (예: "패션", "뷰티")
        market:   대상 마켓 (coupang | smartstore | 11st | gmarket)

    Returns:
        마켓 카테고리 코드 (매핑 없으면 default)
    """
    market_map = _MARKET_CATEGORY_MAPS.get(market, {})
    code = market_map.get(category) or market_map.get("default", "")
    if not code:
        # 부분 일치 시도
        for key, val in market_map.items():
            if key != "default" and key in category:
                return val
    return code or market_map.get("default", "")


def map_categories_for_markets(
    category: str,
    markets: list,
) -> Dict[str, str]:
    """여러 마켓에 대한 카테고리 코드 일괄 반환."""
    return {market: get_category_code(category, market) for market in markets}


def get_supported_categories() -> list:
    """지원 카테고리 목록 반환 (coupang 기준)."""
    return [k for k in _COUPANG_CATEGORY_MAP if k != "default"]
