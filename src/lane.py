"""src/lane.py — v18 PART A: 거래 방향 레인(수입형/수출형) 단일 소스.

레인이 앱 컨텍스트를 구성한다 — 소싱↔타깃 방향·기본 언어·통화·온보딩 카피.
가짜 분기 금지: 선택하면 실제 언어/통화/타깃 마켓 강조가 바뀐다.
- 수입형(Import, 해외→국내): 한국어·KRW, 타깃=쿠팡·스마트스토어·11번가.
- 수출형(Export, 국내→해외): 영어·USD, 타깃=Shopify·아마존US·쇼피·이베이.
외국 방문자(Accept-Language 비-ko)=수출/영어 기본, 한국=수입/한국어 기본. 둘 다 선택·기억·전환 가능.
"""
from __future__ import annotations

LANES = {
    "import": {
        "id": "import",
        "title_ko": "수입형", "title_en": "Import",
        "arrow_ko": "해외 → 국내", "arrow_en": "Overseas → Korea",
        "desc_ko": "타오바오·테무·아마존 등에서 소싱해 쿠팡·네이버·11번가 등 국내 마켓에 판매합니다.",
        "desc_en": "Source from Taobao/Temu/Amazon and sell on Coupang, Naver, 11st in Korea.",
        "lang": "ko", "currency": "KRW",
        "sourcing": "overseas",
        "target_markets": ["coupang", "smartstore", "elevenst"],
    },
    "export": {
        "id": "export",
        "title_ko": "수출형", "title_en": "Export",
        "arrow_ko": "국내 → 해외", "arrow_en": "Korea → Global",
        "desc_ko": "한국 상품을 소싱해 Shopify·아마존US·쇼피·이베이 등 글로벌 마켓에 판매합니다.",
        "desc_en": "Source Korean products and sell on Shopify, Amazon US, Shopee, eBay globally.",
        "lang": "en", "currency": "USD",
        "sourcing": "domestic",
        "target_markets": ["shopify", "amazon", "shopee", "ebay"],
    },
}
DEFAULT_LANE = "import"


def normalize_lane(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in LANES else ""


def default_lane_for(accept_language: str = "") -> str:
    """외국 방문자(Accept-Language 첫 언어 비-ko)=수출, 한국=수입."""
    al = (accept_language or "").strip().lower()
    if al and not al.startswith("ko"):
        return "export"
    return DEFAULT_LANE


def get_lane(cookie_lane: str = "", accept_language: str = "") -> str:
    """현재 레인 — 쿠키로 명시 선택했으면 그 값, 아니면 방문자 언어 기반 기본."""
    return normalize_lane(cookie_lane) or default_lane_for(accept_language)


def lane_info(lane_id: str) -> dict:
    return LANES.get(normalize_lane(lane_id) or DEFAULT_LANE)
