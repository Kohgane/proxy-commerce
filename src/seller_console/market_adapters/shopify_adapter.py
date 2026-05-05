"""src/seller_console/market_adapters/shopify_adapter.py — Shopify 자체몰 어댑터 (Phase 130).

Admin API 2024-04 연동. 키 미설정 시 stub 모드.
ADAPTER_DRY_RUN=1 시 실 API 호출 차단.

환경변수:
  SHOPIFY_ACCESS_TOKEN  — Admin API 액세스 토큰
  SHOPIFY_SHOP          — 숍 도메인 (예: myshop.myshopify.com)
"""
from __future__ import annotations

import logging
import os
from typing import List

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)

_API_VERSION = "2024-04"


def _api_active() -> bool:
    return bool(os.getenv("SHOPIFY_ACCESS_TOKEN")) and bool(os.getenv("SHOPIFY_SHOP"))


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _base_url() -> str:
    shop = os.getenv("SHOPIFY_SHOP", "")
    return f"https://{shop}/admin/api/{_API_VERSION}"


class ShopifyAdapter(MarketAdapter):
    """Shopify Admin API 어댑터 (Phase 130).

    API 키 없으면 stub 모드, ADAPTER_DRY_RUN=1 이면 dry-run 모드.
    """

    marketplace = "shopify"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """Shopify 상품 목록 조회."""
        if not _api_active():
            logger.warning("Shopify API 키 미설정 — stub 모드")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — Shopify fetch_inventory dry-run")
            return []

        try:
            import requests
            token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
            resp = requests.get(
                f"{_base_url()}/products.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                params={"limit": 50, "status": "active"},
                timeout=10,
            )
            resp.raise_for_status()
            products = resp.json().get("products", [])
            items = []
            for p in products:
                variant = p.get("variants", [{}])[0]
                price_str = variant.get("price", "0") or "0"
                try:
                    price_krw = int(float(price_str))
                except (ValueError, TypeError):
                    price_krw = None
                items.append(MarketStatusItem(
                    marketplace="shopify",
                    product_id=str(p.get("id", "")),
                    state="active" if p.get("status") == "active" else "error",
                    sku=variant.get("sku") or None,
                    title=p.get("title"),
                    price_krw=price_krw,
                ))
            return items
        except Exception as exc:
            logger.warning("Shopify fetch_inventory 실패: %s", exc)
            return []

    def upload_product(self, product: dict) -> dict:
        """Shopify에 상품 등록.

        Args:
            product: 상품 데이터 dict (Shopify product 형식)

        Returns:
            등록 결과 dict
        """
        if not _api_active():
            return {"status": "stub", "detail": "SHOPIFY_ACCESS_TOKEN/SHOPIFY_SHOP 미설정"}

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1 — API 호출 차단"}

        try:
            import requests
            token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
            resp = requests.post(
                f"{_base_url()}/products.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"product": product},
                timeout=10,
            )
            resp.raise_for_status()
            return {"status": "ok", "data": resp.json()}
        except Exception as exc:
            logger.warning("Shopify upload_product 실패: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def health_check(self) -> dict:
        """Shopify API 상태 확인."""
        if not _api_active():
            return {
                "status": "missing",
                "detail": "SHOPIFY_ACCESS_TOKEN/SHOPIFY_SHOP 미설정",
                "hint": "https://partners.shopify.com 에서 Private App 생성",
            }

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1"}

        try:
            import requests
            token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
            resp = requests.get(
                f"{_base_url()}/shop.json",
                headers={"X-Shopify-Access-Token": token},
                timeout=5,
            )
            if resp.status_code == 200:
                return {"status": "ok", "detail": "Shopify API 연결 성공"}
            return {"status": "fail", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            logger.warning("Shopify health_check 실패: %s", exc)
            return {"status": "fail", "detail": str(exc)}
