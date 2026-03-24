"""src/seo/structured_data.py — Schema.org 구조화 데이터 생성기.

JSON-LD 형식의 Schema.org 구조화 데이터를 생성한다.

환경변수:
  SEO_ENABLED    — SEO 기능 활성화 여부 (기본 "0")
  SEO_SITE_NAME  — 사이트 이름 (기본 "Proxy Commerce")
  SEO_SITE_URL   — 사이트 URL (기본 "https://example.com")
"""

import os
from typing import Any, Dict, List

_ENABLED = os.getenv("SEO_ENABLED", "0") == "1"
_SITE_NAME = os.getenv("SEO_SITE_NAME", "Proxy Commerce")
_SITE_URL = os.getenv("SEO_SITE_URL", "https://example.com")


class StructuredDataGenerator:
    """Schema.org JSON-LD 구조화 데이터 생성기."""

    def is_enabled(self) -> bool:
        """SEO 기능 활성화 여부를 반환한다."""
        return os.getenv("SEO_ENABLED", "0") == "1"

    def generate_product_jsonld(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schema.org Product JSON-LD를 생성한다.

        Args:
            product_data: 제품 딕셔너리.

        Returns:
            JSON-LD 딕셔너리.
        """
        name = product_data.get("title_ko") or product_data.get("title_en", "")
        description = product_data.get("description", "")
        image = product_data.get("image_url", "")
        sku = product_data.get("sku", "")
        brand_name = product_data.get("brand", "")
        price = product_data.get("price_krw", 0)
        in_stock = product_data.get("in_stock", True)

        availability = (
            "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock"
        )

        return {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": name,
            "description": description,
            "image": image,
            "sku": sku,
            "brand": {
                "@type": "Brand",
                "name": brand_name,
            },
            "offers": {
                "@type": "Offer",
                "price": str(price),
                "priceCurrency": "KRW",
                "availability": availability,
            },
        }

    def generate_breadcrumb_jsonld(self, category_path: List[str]) -> Dict[str, Any]:
        """Schema.org BreadcrumbList JSON-LD를 생성한다.

        Args:
            category_path: 카테고리 경로 리스트 (예: ["홈", "의류", "상의"]).

        Returns:
            JSON-LD 딕셔너리.
        """
        site_url = os.getenv("SEO_SITE_URL", _SITE_URL)
        items = []
        for idx, name in enumerate(category_path, start=1):
            items.append({
                "@type": "ListItem",
                "position": idx,
                "name": name,
                "item": f"{site_url}/{name.lower().replace(' ', '-')}",
            })

        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": items,
        }

    def generate_organization_jsonld(self) -> Dict[str, Any]:
        """Schema.org Organization JSON-LD를 생성한다.

        Returns:
            JSON-LD 딕셔너리.
        """
        site_name = os.getenv("SEO_SITE_NAME", _SITE_NAME)
        site_url = os.getenv("SEO_SITE_URL", _SITE_URL)

        return {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": site_name,
            "url": site_url,
        }
