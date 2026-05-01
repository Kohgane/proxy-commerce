"""collectors/alo.py — ALO Yoga collector MVP.

Covers issue #87: parse title/price/images/options/url into the Product schema pipeline.

Usage (dry-run, no real HTTP):
    from collectors.alo import AloPipeline
    p = AloPipeline()
    product = p.run_one("https://www.aloyoga.com/products/some-slug")
"""
from __future__ import annotations

import re
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.error import URLError

from collectors.base import BaseCollectorPipeline

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ProxyCommerceBot/1.0; +https://github.com/Kohgane/proxy-commerce)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Regex helpers for minimal HTML parsing (no BeautifulSoup dependency required)
_PRICE_RE = re.compile(r'"price"\s*:\s*"?([\d.]+)"?')
_TITLE_RE = re.compile(r'<title[^>]*>([^<]+)</title>', re.IGNORECASE)
_OG_IMAGE_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', re.IGNORECASE)
_JSON_LD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)


def _extract_json_ld(html: str) -> Optional[Dict[str, Any]]:
    """Return the first Product-type JSON-LD block, or None."""
    import json

    for match in _JSON_LD_RE.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
        except (json.JSONDecodeError, ValueError):
            continue
    return None


class AloPipeline(BaseCollectorPipeline):
    """ALO Yoga product collector.

    ``source_id`` is expected to be a full product URL, e.g.:
    ``https://www.aloyoga.com/products/high-waist-airlift-legging``
    """

    source = "alo"

    def __init__(self, timeout: int = 15, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def fetch(self, source_id: str) -> str:
        """Download raw HTML from the product page URL."""
        req = urllib.request.Request(source_id, headers=_DEFAULT_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except URLError as exc:
            raise RuntimeError(f"[alo] HTTP error fetching {source_id}: {exc}") from exc

    def parse(self, raw: str) -> Dict[str, Any]:
        """Extract product fields from raw HTML.

        Tries JSON-LD first, falls back to regex.
        """
        result: Dict[str, Any] = {}

        ld = _extract_json_ld(raw)
        if ld:
            result["title"] = ld.get("name", "")
            offers = ld.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            result["price"] = str(offers.get("price", "0"))
            result["currency"] = offers.get("priceCurrency", "USD")
            result["images"] = [ld["image"]] if isinstance(ld.get("image"), str) else (ld.get("image") or [])
            result["description"] = ld.get("description")
            variants: List[Dict[str, Any]] = ld.get("hasVariant", [])
            options: Dict[str, List[str]] = {}
            for v in variants:
                for key in ("color", "size"):
                    val = v.get(key) or (v.get("additionalProperty") or [{}])[0].get("value")
                    if val:
                        options.setdefault(key, [])
                        if val not in options[key]:
                            options[key].append(val)
            result["options"] = options
            result["in_stock"] = str(offers.get("availability", "")).lower().endswith("instock")
        else:
            # Fallback regex path
            title_m = _TITLE_RE.search(raw)
            result["title"] = title_m.group(1).strip() if title_m else ""
            price_m = _PRICE_RE.search(raw)
            result["price"] = price_m.group(1) if price_m else "0"
            result["currency"] = "USD"
            result["images"] = _OG_IMAGE_RE.findall(raw)[:10]
            result["description"] = None
            result["options"] = {}
            result["in_stock"] = True

        return result

    def normalize(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Map parsed dict to Product field names."""
        options_raw: Dict[str, List[str]] = parsed.get("options") or {}
        options = [{"name": k, "values": v} for k, v in options_raw.items() if v]

        images = parsed.get("images") or []
        if not images:
            images = ["https://www.aloyoga.com/favicon.ico"]  # placeholder

        return {
            "source": self.source,
            "source_product_id": parsed.get("source_id", "alo-unknown"),
            "source_url": parsed.get("source_url", "https://www.aloyoga.com"),
            "brand": "ALO Yoga",
            "title": parsed.get("title", "").strip(),
            "description": parsed.get("description"),
            "currency": parsed.get("currency", "USD"),
            "cost_price": float(parsed.get("price", 0) or 0),
            "images": images,
            "options": options,
            "stock_status": "in_stock" if parsed.get("in_stock", True) else "out_of_stock",
        }

    def run_one(self, source_id: str) -> Any:
        """Override to inject source_url/source_id into parsed dict."""
        from collectors.base import _log_failed_item
        import logging
        logger = logging.getLogger(__name__)

        raw = None
        try:
            raw = self._run_stage("fetch", source_id, self.fetch, source_id, retryable=True)
        except Exception as exc:
            logger.error("[%s] fetch failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(source_id, "fetch", str(exc))
            return None

        parsed = None
        try:
            parsed = self._run_stage("parse", source_id, self.parse, raw)
            parsed["source_id"] = source_id.rstrip("/").split("/")[-1]
            parsed["source_url"] = source_id
        except Exception as exc:
            logger.error("[%s] parse failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(raw, "parse", str(exc))
            return None

        normalized = None
        try:
            normalized = self._run_stage("normalize", source_id, self.normalize, parsed)
        except Exception as exc:
            logger.error("[%s] normalize failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(parsed, "normalize", str(exc))
            return None

        from pydantic import ValidationError
        try:
            product = self._run_stage("validate", source_id, self.validate, normalized)
            return product
        except (ValidationError, TypeError) as exc:
            logger.error("[%s] validate failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(normalized, "validate", str(exc))
            return None
