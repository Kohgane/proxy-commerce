"""src/seller_console/market_adapters/woocommerce_adapter.py — WooCommerce 자체몰 어댑터 (Phase 130 stub → Phase 132 본 구현).

kohganemultishop.org (외부 WordPress/WooCommerce 자체몰) 실연동.
WooCommerce REST API v3 + Basic Auth (consumer_key:consumer_secret over HTTPS).
키 미설정 시 stub 모드.
ADAPTER_DRY_RUN=1 시 실 API 호출 차단.

환경변수 (복수 이름 지원):
  WC_KEY 또는 WOO_CK          — consumer_key
  WC_SECRET 또는 WOO_CS       — consumer_secret
  WC_URL 또는 WOO_BASE_URL    — WordPress 사이트 URL (예: https://kohganemultishop.org)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
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


def _mask_name(name: str) -> str:
    """이름 마스킹 (첫 글자만 공개)."""
    if not name:
        return ""
    return name[0] + "*" * max(len(name) - 1, 1)


def _mask_phone(phone: str) -> str:
    """전화번호 마스킹 (뒤 4자리 마스킹)."""
    if not phone:
        return ""
    if len(phone) > 4:
        return phone[:-4] + "****"
    return "****"


class WooCommerceAdapter(MarketAdapter):
    """WooCommerce REST API v3 어댑터 — kohganemultishop.org 실연동 (Phase 132).

    API 키 없으면 stub 모드, ADAPTER_DRY_RUN=1 이면 dry-run 모드.
    """

    marketplace = "woocommerce"
    display_name = "코가네멀티샵 (WooCommerce)"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """WooCommerce 상품 목록 조회. 페이지네이션 자동 처리."""
        if not _api_active():
            logger.warning("WooCommerce API 키 미설정 — stub 모드")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — WooCommerce fetch_inventory dry-run")
            return []

        try:
            import requests
            items = []
            page = 1
            while True:
                resp = requests.get(
                    f"{_api_url()}/products",
                    auth=_auth(),
                    params={"per_page": 100, "status": "publish", "page": page},
                    timeout=15,
                )
                resp.raise_for_status()
                products = resp.json()
                if not products:
                    break
                for p in products:
                    price_str = p.get("price") or p.get("regular_price", "0") or "0"
                    try:
                        price_krw = int(float(price_str))
                    except (ValueError, TypeError):
                        price_krw = None
                    items.append(MarketStatusItem(
                        marketplace="woocommerce",
                        product_id=str(p.get("id", "")),
                        state=self._map_product_state(p),
                        sku=p.get("sku") or None,
                        title=p.get("name"),
                        price_krw=price_krw,
                    ))
                if len(products) < 100:
                    break
                page += 1
            return items
        except Exception as exc:
            logger.warning("WooCommerce fetch_inventory 실패: %s", exc)
            return []

    def _map_product_state(self, product: dict) -> str:
        """WooCommerce 상품 상태 → MarketStatusItem state 매핑."""
        if product.get("status") != "publish":
            return "suspended"
        if product.get("stock_status") == "outofstock":
            return "out_of_stock"
        return "active"

    def fetch_orders(self, since: Optional[datetime] = None) -> list:
        """WooCommerce 주문 목록 조회. 페이지네이션 자동 처리.

        Args:
            since: 이 시각 이후 주문만 조회 (None이면 최근 전체)

        Returns:
            주문 dict 리스트 (WooCommerce raw + marketplace 필드 추가)
        """
        if not _api_active():
            logger.warning("WooCommerce API 키 미설정 — fetch_orders stub")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — WooCommerce fetch_orders dry-run")
            return []

        try:
            import requests
            orders = []
            page = 1
            params: dict = {"per_page": 100}
            if since:
                params["after"] = since.isoformat()
            while True:
                params["page"] = page
                resp = requests.get(
                    f"{_api_url()}/orders",
                    auth=_auth(),
                    params=params,
                    timeout=15,
                )
                resp.raise_for_status()
                batch = resp.json()
                if not batch:
                    break
                for woo in batch:
                    orders.append(self._woo_order_to_unified(woo))
                if len(batch) < 100:
                    break
                page += 1
            return orders
        except Exception as exc:
            logger.warning("WooCommerce fetch_orders 실패: %s", exc)
            return []

    def fetch_orders_unified(self, since=None, until=None) -> list:
        """OrderSyncService 호환 메서드 — fetch_orders() 위임."""
        return self.fetch_orders(since=since)

    def _woo_order_to_unified(self, woo: dict) -> dict:
        """WooCommerce 주문 dict → 통합 주문 dict 변환."""
        billing = woo.get("billing") or {}
        first_name = billing.get("first_name", "")
        last_name = billing.get("last_name", "")
        full_name = (first_name + last_name).strip() or billing.get("company", "")

        date_created = woo.get("date_created_gmt") or woo.get("date_created", "")
        date_paid = woo.get("date_paid_gmt") or woo.get("date_paid") or ""

        items = []
        for li in (woo.get("line_items") or []):
            items.append({
                "sku": li.get("sku") or str(li.get("product_id", "")),
                "title": li.get("name", ""),
                "qty": li.get("quantity", 1),
                "unit_price_krw": li.get("price") or li.get("subtotal") or "0",
            })

        return {
            "order_id": str(woo.get("id", "")),
            "marketplace": "woocommerce",
            "status": self._map_order_status(woo.get("status", "")),
            "placed_at": date_created,
            "paid_at": date_paid,
            "buyer_name_masked": _mask_name(full_name),
            "buyer_phone_masked": _mask_phone(billing.get("phone", "")),
            "buyer_address_masked": billing.get("city", ""),
            "total_krw": woo.get("total", "0"),
            "shipping_fee_krw": woo.get("shipping_total", "0"),
            "items": items,
            "raw": woo,
        }

    def _map_order_status(self, woo_status: str) -> str:
        """WooCommerce 주문 상태 → 통합 상태 매핑."""
        return {
            "pending": "new",
            "processing": "paid",
            "on-hold": "new",
            "completed": "delivered",
            "cancelled": "canceled",
            "refunded": "returned",
            "failed": "canceled",
        }.get(woo_status, "new")

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
                timeout=15,
            )
            resp.raise_for_status()
            return {"status": "ok", "data": resp.json()}
        except Exception as exc:
            logger.warning("WooCommerce upload_product 실패: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def update_tracking(self, order_id: str, courier: str = "", tracking_no: str = "") -> bool:
        """운송장 번호를 WooCommerce 주문 노트로 기록.

        WooCommerce는 기본적으로 운송장 메타가 없음 → order note로 기록.
        Advanced Shipment Tracking 플러그인 활성 시 별도 엔드포인트 사용 가능.
        """
        if not _api_active():
            logger.warning("WooCommerce API 키 미설정 — update_tracking stub")
            return False

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — WooCommerce update_tracking dry-run")
            return True

        try:
            import requests
            note = f"[퍼센티] 운송장 등록: {courier} / {tracking_no}"
            resp = requests.post(
                f"{_api_url()}/orders/{order_id}/notes",
                auth=_auth(),
                json={"note": note, "customer_note": False},
                timeout=15,
            )
            resp.raise_for_status()
            logger.info("WooCommerce 운송장 등록 완료: order=%s, %s/%s", order_id, courier, tracking_no)
            return True
        except Exception as exc:
            logger.warning("WooCommerce update_tracking 실패: %s", exc)
            return False

    def health_check(self) -> dict:
        """WooCommerce API 상태 확인."""
        if not _api_active():
            return {
                "status": "missing",
                "name": "woocommerce",
                "hint": "WC_URL, WC_KEY, WC_SECRET 환경변수 등록 필요",
                "detail": "kohganemultishop.org → WP 관리자 → WooCommerce → 설정 → API → 키 생성 (Read/Write)",
            }

        if _dry_run():
            return {"status": "dry_run", "name": "woocommerce", "detail": "ADAPTER_DRY_RUN=1"}

        try:
            import requests
            resp = requests.get(
                f"{_api_url()}/products",
                auth=_auth(),
                params={"per_page": 1},
                timeout=5,
            )
            if resp.status_code == 200:
                base_url = _get_env("WC_URL", "WOO_BASE_URL") or ""
                return {
                    "status": "ok",
                    "name": "woocommerce",
                    "base_url": base_url,
                    "detail": "WooCommerce REST API 정상",
                }
            return {"status": "fail", "name": "woocommerce", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            logger.warning("WooCommerce health_check 실패: %s", exc)
            return {"status": "fail", "name": "woocommerce", "detail": str(exc)}
