"""src/seller_console/market_adapters/woocommerce_adapter.py — WooCommerce 자체몰 어댑터 (Phase 130).

WooCommerce REST API v3 연동. Basic Auth (consumer_key + consumer_secret).
키 미설정 시 stub 모드.
ADAPTER_DRY_RUN=1 시 실 API 호출 차단.

환경변수 (복수 이름 지원):
  WC_KEY 또는 WOO_CK          — consumer_key
  WC_SECRET 또는 WOO_CS       — consumer_secret
  WC_URL 또는 WOO_BASE_URL    — WordPress 사이트 URL (예: https://myshop.com)
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)


def _get_env(*names: str) -> Optional[str]:
    """여러 이름 중 첫 번째로 설정된 환경변수 반환."""
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return None


def _api_active() -> bool:
    return bool(
        _get_env("WC_KEY", "WOO_CK")
        and _get_env("WC_SECRET", "WOO_CS")
        and _get_env("WC_URL", "WOO_BASE_URL")
    )


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _api_url() -> str:
    base = (_get_env("WC_URL", "WOO_BASE_URL") or "").rstrip("/")
    return f"{base}/wp-json/wc/v3"


def _auth() -> tuple:
    return (
        _get_env("WC_KEY", "WOO_CK") or "",
        _get_env("WC_SECRET", "WOO_CS") or "",
    )


class WooCommerceAdapter(MarketAdapter):
    """WooCommerce REST API v3 어댑터 (Phase 130).

    API 키 없으면 stub 모드, ADAPTER_DRY_RUN=1 이면 dry-run 모드.
    """

    marketplace = "woocommerce"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """WooCommerce 상품 목록 조회."""
        if not _api_active():
            logger.warning("WooCommerce API 키 미설정 — stub 모드")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — WooCommerce fetch_inventory dry-run")
            return []

        try:
            import requests
            resp = requests.get(
                f"{_api_url()}/products",
                auth=_auth(),
                params={"per_page": 50, "status": "publish"},
                timeout=10,
            )
            resp.raise_for_status()
            products = resp.json()
            items = []
            for p in products:
                price_str = p.get("regular_price", "0") or "0"
                try:
                    price_krw = int(float(price_str))
                except (ValueError, TypeError):
                    price_krw = None
                items.append(MarketStatusItem(
                    marketplace="woocommerce",
                    product_id=str(p.get("id", "")),
                    state="active" if p.get("status") == "publish" else "inactive",
                    sku=p.get("sku") or None,
                    title=p.get("name"),
                    price_krw=price_krw,
                ))
            return items
        except Exception as exc:
            logger.warning("WooCommerce fetch_inventory 실패: %s", exc)
            return []

    def upload_product(self, product: dict) -> dict:
        """WooCommerce에 상품 등록.

        Args:
            product: 상품 데이터 dict (WooCommerce product 형식)

        Returns:
            등록 결과 dict
        """
        if not _api_active():
            return {"status": "stub", "detail": "WC_KEY/WC_SECRET/WC_URL 미설정"}

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1 — API 호출 차단"}

        try:
            import requests
            resp = requests.post(
                f"{_api_url()}/products",
                auth=_auth(),
                json=product,
                timeout=10,
            )
            resp.raise_for_status()
            return {"status": "ok", "data": resp.json()}
        except Exception as exc:
            logger.warning("WooCommerce upload_product 실패: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def health_check(self) -> dict:
        """WooCommerce API 상태 확인."""
        if not _api_active():
            return {
                "status": "missing",
                "detail": "WC_KEY/WC_SECRET/WC_URL 미설정",
                "hint": "https://woocommerce.com/document/woocommerce-rest-api 에서 키 발급",
            }

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1"}

        try:
            import requests
            resp = requests.get(
                f"{_api_url()}/system_status",
                auth=_auth(),
                timeout=5,
            )
            if resp.status_code == 200:
                return {"status": "ok", "detail": "WooCommerce API 연결 성공"}
            return {"status": "fail", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            logger.warning("WooCommerce health_check 실패: %s", exc)
            return {"status": "fail", "detail": str(exc)}
