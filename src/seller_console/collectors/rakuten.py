"""src/seller_console/collectors/rakuten.py — 라쿠텐 수집기 (Phase 128).

Rakuten Ichiba Item Search API 사용 (RAKUTEN_APP_ID 활성 시).
미활성 시 OG 폴백.
"""
from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse, parse_qs

from .base import BaseCollector, CollectorResult
from .generic_og import GenericOgCollector

logger = logging.getLogger(__name__)

_RAKUTEN_SEARCH_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706"


def _rakuten_active() -> bool:
    """Rakuten App ID 설정 여부 확인."""
    return bool(os.getenv("RAKUTEN_APP_ID"))


def _extract_item_code(url: str) -> Optional[str]:
    """라쿠텐 URL에서 아이템 코드 추출.

    예: https://item.rakuten.co.jp/shop/item-code/
    """
    # item.rakuten.co.jp/{shop}/{item} 패턴
    m = re.search(r"item\.rakuten\.co\.jp/[^/]+/([^/?#]+)", url, re.IGNORECASE)
    return m.group(1) if m else None


def _fetch_rakuten_item(item_code: str) -> Optional[dict]:
    """Rakuten IchibaItem Search API 호출."""
    app_id = os.getenv("RAKUTEN_APP_ID", "")
    if not app_id:
        return None

    try:
        import requests
        params = {
            "applicationId": app_id,
            "keyword": item_code,
            "format": "json",
            "hits": 1,
        }
        resp = requests.get(_RAKUTEN_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("Items", [])
        if not items:
            return None
        item = items[0].get("Item", items[0])
        return {
            "title": item.get("itemName", ""),
            "description": item.get("itemCaption", ""),
            "price": item.get("itemPrice"),
            "currency": "JPY",
            "brand": item.get("shopName", ""),
            "images": [item.get("mediumImageUrls", [{}])[0].get("imageUrl", "")] if item.get("mediumImageUrls") else [],
            "sku": item.get("itemCode", ""),
            "category": item.get("genreName", ""),
        }
    except Exception as exc:
        logger.warning("Rakuten API 실패: %s", exc)
        return None


class RakutenCollector(BaseCollector):
    """라쿠텐 이치바 수집기 (Rakuten WS API → OG 폴백)."""

    name = "rakuten"

    def collect(self, url: str) -> CollectorResult:
        """라쿠텐 URL에서 상품 정보 수집."""
        item_code = _extract_item_code(url)

        # Rakuten API 시도
        if _rakuten_active() and item_code:
            data = _fetch_rakuten_item(item_code)
            if data:
                price = None
                if data.get("price"):
                    try:
                        price = Decimal(str(data["price"]))
                    except Exception:
                        pass
                return CollectorResult(
                    success=True,
                    url=url,
                    source="rakuten_api",
                    title=data.get("title"),
                    description=data.get("description"),
                    images=[img for img in data.get("images", []) if img],
                    price=price,
                    currency="JPY",
                    brand=data.get("brand"),
                    sku=data.get("sku"),
                    category=data.get("category"),
                )

        # OG 폴백
        result = GenericOgCollector().collect(url)
        result.source = "rakuten_og"

        warnings = list(result.warnings)
        if not _rakuten_active():
            warnings.append(
                "RAKUTEN_APP_ID 미설정 — OG 메타 폴백 사용. "
                "https://webservice.rakuten.co.jp 에서 App ID 발급 후 환경변수 등록하세요."
            )
        result.warnings = warnings

        if not result.currency:
            result.currency = "JPY"

        return result
