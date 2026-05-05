"""src/shop/catalog.py — Sheets catalog 워크시트 → 자체몰 진열 상품 (Phase 131).

조건:
- marketplace == "kohganemultishop" 또는 "all"
- state == "active"
- price_krw > 0

5분 in-memory 캐시.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5분

# catalog 워크시트 필수 컬럼
CATALOG_HEADERS = [
    "sku",
    "title_ko",
    "title_en",
    "price_krw",
    "sale_price_krw",
    "marketplace",
    "state",
    "slug",
    "featured",
    "category",
    "thumbnail_url",
    "gallery_urls_json",
    "description_html_short",
    "description_html_long",
    "stock_qty",
    "shipping_fee_krw",
    "options_json",
]


def _slugify(text: str) -> str:
    """제목 → URL slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "product"


@dataclass
class ShopProduct:
    """B2C 진열 상품 도메인 모델."""

    slug: str
    sku: str
    title_ko: str
    price_krw: int
    sale_price_krw: Optional[int]
    thumbnail_url: str
    gallery_urls: List[str]
    short_desc: str
    long_desc_html: str
    options: List[dict]
    stock_qty: int
    shipping_fee_krw: int
    category: str
    featured: bool

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "sku": self.sku,
            "title_ko": self.title_ko,
            "price_krw": self.price_krw,
            "sale_price_krw": self.sale_price_krw,
            "thumbnail_url": self.thumbnail_url,
            "gallery_urls": self.gallery_urls,
            "short_desc": self.short_desc,
            "long_desc_html": self.long_desc_html,
            "options": self.options,
            "stock_qty": self.stock_qty,
            "shipping_fee_krw": self.shipping_fee_krw,
            "category": self.category,
            "featured": self.featured,
        }


def _parse_int(val, default: int = 0) -> int:
    try:
        return int(float(str(val))) if val not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def _parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("1", "true", "yes")


def _parse_json_list(val) -> list:
    if not val:
        return []
    try:
        parsed = json.loads(str(val))
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _row_to_product(row: dict) -> Optional[ShopProduct]:
    """Sheets row dict → ShopProduct. 조건 불충족 시 None."""
    marketplace = str(row.get("marketplace", "")).strip().lower()
    state = str(row.get("state", "")).strip().lower()
    price_krw = _parse_int(row.get("price_krw"), 0)

    if marketplace not in ("kohganemultishop", "all"):
        return None
    if state != "active":
        return None
    if price_krw <= 0:
        return None

    title_ko = str(row.get("title_ko", "")).strip() or str(row.get("title_en", "")).strip() or "상품"
    sku = str(row.get("sku", "")).strip() or ""
    slug = str(row.get("slug", "")).strip() or _slugify(title_ko)
    if not slug:
        slug = sku or "product"

    sale_raw = _parse_int(row.get("sale_price_krw"), 0)
    sale_price_krw = sale_raw if sale_raw > 0 and sale_raw < price_krw else None

    gallery_urls = _parse_json_list(row.get("gallery_urls_json"))
    options = _parse_json_list(row.get("options_json"))

    thumbnail = str(row.get("thumbnail_url", "")).strip()
    if not thumbnail and gallery_urls:
        thumbnail = gallery_urls[0]

    return ShopProduct(
        slug=slug,
        sku=sku,
        title_ko=title_ko,
        price_krw=price_krw,
        sale_price_krw=sale_price_krw,
        thumbnail_url=thumbnail,
        gallery_urls=gallery_urls,
        short_desc=str(row.get("description_html_short", "")).strip(),
        long_desc_html=str(row.get("description_html_long", "")).strip(),
        options=options,
        stock_qty=_parse_int(row.get("stock_qty"), 0),
        shipping_fee_krw=_parse_int(row.get("shipping_fee_krw"), 0),
        category=str(row.get("category", "기타")).strip() or "기타",
        featured=_parse_bool(row.get("featured", False)),
    )


class ShopCatalog:
    """Sheets catalog 워크시트 → B2C 진열 상품.

    5분 in-memory 캐시.
    """

    def __init__(self, sheet_id: Optional[str] = None):
        self._sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")
        self._cache: Optional[List[ShopProduct]] = None
        self._cache_at: float = 0.0

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def list_all(self, force: bool = False) -> List[ShopProduct]:
        """모든 진열 상품 반환 (캐시)."""
        if not force and self._cache is not None and (time.time() - self._cache_at) < _CACHE_TTL:
            return self._cache
        self._cache = self._fetch()
        self._cache_at = time.time()
        return self._cache

    def list_featured(self, limit: int = 8) -> List[ShopProduct]:
        """추천 상품 (featured=True) 목록."""
        featured = [p for p in self.list_all() if p.featured]
        return featured[:limit]

    def list_by_category(
        self, category: str, page: int = 1, per_page: int = 24
    ) -> Tuple[List[ShopProduct], int]:
        """카테고리별 상품 페이징. (items, total_count)"""
        if category and category != "전체":
            items = [p for p in self.list_all() if p.category == category]
        else:
            items = self.list_all()
        total = len(items)
        start = (page - 1) * per_page
        return items[start : start + per_page], total

    def search(self, q: str) -> List[ShopProduct]:
        """제목/설명 키워드 검색."""
        if not q:
            return self.list_all()
        q_lower = q.lower()
        return [
            p for p in self.list_all()
            if q_lower in p.title_ko.lower() or q_lower in p.short_desc.lower()
        ]

    def get_by_slug(self, slug: str) -> Optional[ShopProduct]:
        """슬러그로 상품 조회."""
        for p in self.list_all():
            if p.slug == slug:
                return p
        return None

    def get_categories(self) -> List[Dict]:
        """카테고리 목록 [{name, count}]."""
        cats: Dict[str, int] = {}
        for p in self.list_all():
            cats[p.category] = cats.get(p.category, 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])]

    def invalidate(self) -> None:
        """캐시 무효화."""
        self._cache = None
        self._cache_at = 0.0

    # ------------------------------------------------------------------
    # 내부: Sheets 로드
    # ------------------------------------------------------------------

    def _fetch(self) -> List[ShopProduct]:
        """Sheets catalog 워크시트에서 상품 로드."""
        if not self._sheet_id:
            logger.debug("GOOGLE_SHEET_ID 미설정 — 빈 카탈로그 반환")
            return []

        try:
            from src.utils.sheets import open_sheet_object, get_or_create_worksheet
            sh = open_sheet_object(self._sheet_id)

            # catalog 워크시트 자동 생성/부트스트랩
            try:
                ws = sh.worksheet("catalog")
            except Exception:
                try:
                    ws = sh.add_worksheet(title="catalog", rows=100, cols=len(CATALOG_HEADERS))
                    ws.update("A1", [CATALOG_HEADERS])
                    logger.info("catalog 워크시트 자동 생성 완료")
                except Exception as create_exc:
                    logger.warning("catalog 워크시트 생성 실패: %s", create_exc)
                return []

            records = ws.get_all_records()
            products = []
            for row in records:
                p = _row_to_product(row)
                if p is not None:
                    products.append(p)
            logger.info("ShopCatalog: %d개 상품 로드 완료", len(products))
            return products

        except Exception as exc:
            logger.warning("ShopCatalog._fetch 실패: %s", exc)
            return []


# 모듈 수준 싱글턴 (앱 내 공유)
_default_catalog: Optional[ShopCatalog] = None


def get_catalog() -> ShopCatalog:
    """기본 ShopCatalog 인스턴스 반환."""
    global _default_catalog
    if _default_catalog is None:
        _default_catalog = ShopCatalog()
    return _default_catalog
