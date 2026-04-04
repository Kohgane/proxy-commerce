"""src/seo/sitemap_generator.py — XML Sitemap 자동 생성 (Phase 91).

상품/카테고리/정적 페이지 URL을 수집하여 XML sitemap을 생성한다.
대량 상품 시 sitemap index로 분할한다.

API 엔드포인트: GET /sitemap.xml
"""
from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# sitemap 당 최대 URL 수
MAX_URLS_PER_SITEMAP = 1000

_SITEMAP_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
_SITEMAP_NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def _url_entry(
    loc: str,
    lastmod: Optional[str] = None,
    changefreq: Optional[str] = None,
    priority: Optional[float] = None,
) -> str:
    """단일 URL 엔트리 XML 문자열을 생성한다."""
    parts = [f"  <url>\n    <loc>{loc}</loc>"]
    if lastmod:
        parts.append(f"    <lastmod>{lastmod}</lastmod>")
    if changefreq:
        parts.append(f"    <changefreq>{changefreq}</changefreq>")
    if priority is not None:
        parts.append(f"    <priority>{priority:.1f}</priority>")
    parts.append("  </url>")
    return "\n".join(parts)


class SitemapGenerator:
    """XML Sitemap 생성기."""

    def __init__(self, base_url: str = "https://example.com") -> None:
        self.base_url = base_url.rstrip("/")

    def _today(self) -> str:
        return date.today().isoformat()

    def _static_pages(self) -> List[Dict[str, Any]]:
        """정적 페이지 목록을 반환한다."""
        today = self._today()
        return [
            {"loc": self.base_url + "/", "changefreq": "daily", "priority": 1.0, "lastmod": today},
            {"loc": self.base_url + "/products", "changefreq": "daily", "priority": 0.9, "lastmod": today},
            {"loc": self.base_url + "/categories", "changefreq": "weekly", "priority": 0.8, "lastmod": today},
            {"loc": self.base_url + "/about", "changefreq": "monthly", "priority": 0.5, "lastmod": today},
            {"loc": self.base_url + "/contact", "changefreq": "monthly", "priority": 0.5, "lastmod": today},
        ]

    def _product_entries(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """상품 목록에서 sitemap 엔트리를 생성한다."""
        today = self._today()
        entries = []
        for p in products:
            sku = p.get("sku", "")
            slug = p.get("slug") or sku.lower().replace(" ", "-")
            loc = f"{self.base_url}/products/{slug}"
            entries.append({
                "loc": loc,
                "changefreq": "weekly",
                "priority": 0.8,
                "lastmod": p.get("updated_at", today)[:10] if p.get("updated_at") else today,
            })
        return entries

    def _category_entries(self, categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """카테고리 목록에서 sitemap 엔트리를 생성한다."""
        today = self._today()
        entries = []
        for c in categories:
            slug = c.get("slug") or str(c.get("id", "")).lower()
            loc = f"{self.base_url}/categories/{slug}"
            entries.append({
                "loc": loc,
                "changefreq": "weekly",
                "priority": 0.7,
                "lastmod": today,
            })
        return entries

    def _build_sitemap_xml(self, entries: List[Dict[str, Any]]) -> str:
        """URL 엔트리 목록으로 sitemap XML을 생성한다."""
        url_parts = []
        for e in entries:
            url_parts.append(_url_entry(
                loc=e["loc"],
                lastmod=e.get("lastmod"),
                changefreq=e.get("changefreq"),
                priority=e.get("priority"),
            ))
        body = "\n".join(url_parts)
        return f"{_SITEMAP_HEADER}\n<urlset {_SITEMAP_NS}>\n{body}\n</urlset>"

    def generate(
        self,
        products: Optional[List[Dict[str, Any]]] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """단일 sitemap XML 문자열을 생성한다.

        Args:
            products: 상품 목록
            categories: 카테고리 목록

        Returns:
            XML sitemap 문자열
        """
        entries = self._static_pages()
        if products:
            entries.extend(self._product_entries(products))
        if categories:
            entries.extend(self._category_entries(categories))
        # 최대 개수 제한
        entries = entries[:MAX_URLS_PER_SITEMAP]
        return self._build_sitemap_xml(entries)

    def generate_index(
        self,
        products: Optional[List[Dict[str, Any]]] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """대량 상품 시 sitemap index와 분할 sitemap들을 생성한다.

        Returns:
            {"index": str (index XML), "sitemaps": List[str] (개별 sitemap XML)}
        """
        all_entries = self._static_pages()
        if products:
            all_entries.extend(self._product_entries(products))
        if categories:
            all_entries.extend(self._category_entries(categories))

        total = len(all_entries)
        if total <= MAX_URLS_PER_SITEMAP:
            xml = self._build_sitemap_xml(all_entries)
            return {"index": None, "sitemaps": [xml]}

        num_sitemaps = math.ceil(total / MAX_URLS_PER_SITEMAP)
        sitemaps = []
        sitemap_locs = []
        today = self._today()

        for i in range(num_sitemaps):
            chunk = all_entries[i * MAX_URLS_PER_SITEMAP:(i + 1) * MAX_URLS_PER_SITEMAP]
            sitemaps.append(self._build_sitemap_xml(chunk))
            sitemap_locs.append({
                "loc": f"{self.base_url}/sitemap-{i + 1}.xml",
                "lastmod": today,
            })

        # index 생성
        sm_parts = []
        for sl in sitemap_locs:
            sm_parts.append(f"  <sitemap>\n    <loc>{sl['loc']}</loc>\n    <lastmod>{sl['lastmod']}</lastmod>\n  </sitemap>")
        index_body = "\n".join(sm_parts)
        index_ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
        index_xml = f'{_SITEMAP_HEADER}\n<sitemapindex {index_ns}>\n{index_body}\n</sitemapindex>'

        return {"index": index_xml, "sitemaps": sitemaps}
