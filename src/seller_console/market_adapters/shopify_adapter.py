"""src/seller_console/market_adapters/shopify_adapter.py — Shopify 자체몰 어댑터 (Phase 130, 주문수집·배송추적 Phase 206).

키 미설정 시 stub 모드. ADAPTER_DRY_RUN=1 시 실 API 호출 차단.

주문수집/배송추적은 검증된 토큰 발급(client_credentials → shpat_)과 GraphQL Admin API를
재사용한다(`src/markets/adapters/shopify.py`). 신규 개발자대시보드 앱은 REST가 막혀 GraphQL만 동작.

환경변수:
  SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET — client_credentials 발급(권장, 주문/배송에 사용)
  SHOPIFY_AUTO_TOKEN    — Admin API 앱 자동화 토큰(레거시 인벤토리/업로드 경로)
  SHOPIFY_ACCESS_TOKEN  — 하위호환 토큰
  SHOPIFY_SHOP          — 숍 도메인 (예: myshop.myshopify.com)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)

def _access_token() -> str:
    return (os.getenv("SHOPIFY_AUTO_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_TOKEN") or "").strip()


def _api_active() -> bool:
    return bool(_access_token()) and bool(os.getenv("SHOPIFY_SHOP"))


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _base_url() -> str:
    shop = os.getenv("SHOPIFY_SHOP", "")
    api_version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    return f"https://{shop}/admin/api/{api_version}"


def _mask_name(name: str) -> str:
    """이름 마스킹 (첫 글자만 공개)."""
    if not name:
        return ""
    return name[0] + "*" * max(len(name) - 1, 0)


def _mask_phone(phone: str) -> str:
    """전화번호 마스킹 (뒤 4자리 마스킹)."""
    if not phone:
        return ""
    if len(phone) > 4:
        return phone[:-4] + "****"
    return "****"


def _gid_tail(gid: str) -> str:
    """gid://shopify/Order/12345 → '12345'."""
    return str(gid or "").rsplit("/", 1)[-1]


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
            token = _access_token()
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
            return {"status": "stub", "detail": "SHOPIFY_AUTO_TOKEN/SHOPIFY_SHOP 미설정"}

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1 — API 호출 차단"}

        try:
            import requests
            token = _access_token()
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

    # ------------------------------------------------------------------
    # 주문수집 · 배송추적 (Phase 206) — GraphQL Admin API + client_credentials
    # ------------------------------------------------------------------
    def _market(self):
        """검증된 토큰 발급·GraphQL 실행을 담당하는 markets 어댑터 인스턴스."""
        if getattr(self, "_market_adapter", None) is None:
            from src.markets.adapters.shopify import ShopifyAdapter as _MarketShopify
            self._market_adapter = _MarketShopify()
        return self._market_adapter

    def _orders_configured(self) -> bool:
        """주문/배송용 자격증명 존재 여부(client_credentials 또는 직접 토큰)."""
        try:
            return bool(self._market().is_configured())
        except Exception:
            return False

    def fetch_orders(self, since: Optional[datetime] = None) -> list:
        """Shopify 주문 목록 조회 (GraphQL, 커서 페이지네이션).

        Args:
            since: 이 시각 이후 생성 주문만 조회 (None이면 마켓 기본)

        Returns:
            통합 주문 dict 리스트 (자격증명 미설정·dry-run·실패 시 빈 리스트)
        """
        if not self._orders_configured():
            logger.warning("Shopify 자격증명 미설정 — fetch_orders stub")
            return []
        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — Shopify fetch_orders dry-run")
            return []

        search = ""
        if since is not None:
            try:
                search = f"created_at:>={since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            except Exception:
                search = ""

        query = """
        query($q: String, $after: String) {
          orders(first: 50, after: $after, query: $q, sortKey: CREATED_AT) {
            edges {
              node {
                id name createdAt processedAt cancelledAt
                displayFinancialStatus displayFulfillmentStatus
                totalPriceSet { shopMoney { amount currencyCode } }
                totalShippingPriceSet { shopMoney { amount } }
                customer { firstName lastName }
                shippingAddress { phone city }
                lineItems(first: 50) {
                  edges { node { sku title quantity originalUnitPriceSet { shopMoney { amount } } } }
                }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        orders: list = []
        after: Optional[str] = None
        try:
            for _ in range(20):  # 최대 1000건 안전 캡
                resp = self._market().graphql(query, {"q": search or None, "after": after})
                if not (200 <= resp.status_code < 300):
                    logger.warning("Shopify fetch_orders HTTP %s", resp.status_code)
                    break
                body = resp.json() if callable(getattr(resp, "json", None)) else {}
                if body.get("errors"):
                    logger.warning("Shopify fetch_orders GraphQL 오류: %s", body["errors"])
                    break
                conn = ((body.get("data") or {}).get("orders") or {})
                for edge in conn.get("edges") or []:
                    node = edge.get("node") or {}
                    orders.append(self._shopify_order_to_unified(node))
                page = conn.get("pageInfo") or {}
                if not page.get("hasNextPage"):
                    break
                after = page.get("endCursor")
                if not after:
                    break
            return orders
        except Exception as exc:
            logger.warning("Shopify fetch_orders 실패: %s", exc)
            return orders

    def fetch_orders_unified(self, since=None, until=None) -> list:
        """OrderSyncService 호환 메서드 — fetch_orders() 위임."""
        return self.fetch_orders(since=since)

    def _shopify_order_to_unified(self, node: dict) -> dict:
        """Shopify GraphQL 주문 노드 → 통합 주문 dict 변환."""
        total = (((node.get("totalPriceSet") or {}).get("shopMoney")) or {})
        shipping = (((node.get("totalShippingPriceSet") or {}).get("shopMoney")) or {})
        customer = node.get("customer") or {}
        full_name = ((customer.get("firstName") or "") + (customer.get("lastName") or "")).strip()
        ship_addr = node.get("shippingAddress") or {}

        items = []
        for edge in ((node.get("lineItems") or {}).get("edges") or []):
            li = edge.get("node") or {}
            unit = (((li.get("originalUnitPriceSet") or {}).get("shopMoney")) or {})
            items.append({
                "sku": li.get("sku") or "",
                "title": li.get("title", ""),
                "qty": li.get("quantity", 1),
                "unit_price_krw": unit.get("amount") if unit.get("amount") is not None else "0",
            })

        return {
            "order_id": _gid_tail(node.get("id", "")),
            "marketplace": "shopify",
            "status": self._map_order_status(
                str(node.get("displayFinancialStatus") or ""),
                str(node.get("displayFulfillmentStatus") or ""),
                bool(node.get("cancelledAt")),
            ),
            "placed_at": node.get("createdAt", ""),
            "paid_at": node.get("processedAt", "") or "",
            "buyer_name_masked": _mask_name(full_name),
            "buyer_phone_masked": _mask_phone(ship_addr.get("phone", "") or ""),
            "buyer_address_masked": ship_addr.get("city", "") or "",
            "total_krw": total.get("amount", "0") if total.get("amount") is not None else "0",
            "shipping_fee_krw": shipping.get("amount", "0") if shipping.get("amount") is not None else "0",
            "order_name": node.get("name", ""),
            "currency": total.get("currencyCode", "") or "",
            "items": items,
            "raw": node,
        }

    def _map_order_status(self, financial: str, fulfillment: str, cancelled: bool) -> str:
        """Shopify 재무/배송 상태 → 통합 상태 매핑."""
        if cancelled:
            return "canceled"
        fin = (financial or "").upper()
        ful = (fulfillment or "").upper()
        if fin in ("REFUNDED", "PARTIALLY_REFUNDED"):
            return "returned"
        if ful == "FULFILLED":
            return "delivered"
        if fin == "PAID":
            return "paid"
        return "new"

    def update_tracking(self, order_id: str, courier: str = "", tracking_no: str = "") -> bool:
        """Shopify 주문에 운송장 등록 (GraphQL fulfillmentCreateV2).

        주문의 open fulfillmentOrder를 조회해 운송장 정보로 이행(fulfillment) 생성.
        실패·오류 시 False(거짓 성공 보고 금지). dry-run/미설정 시 안전 처리.
        """
        if not self._orders_configured():
            logger.warning("Shopify 자격증명 미설정 — update_tracking stub")
            return False
        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — Shopify update_tracking dry-run (%s)", order_id)
            return True

        gid = order_id if str(order_id).startswith("gid://") else f"gid://shopify/Order/{order_id}"
        try:
            fo_query = """
            query($id: ID!) {
              order(id: $id) {
                fulfillmentOrders(first: 10) { edges { node { id status } } }
              }
            }
            """
            resp = self._market().graphql(fo_query, {"id": gid})
            if not (200 <= resp.status_code < 300):
                logger.warning("Shopify fulfillmentOrders HTTP %s", resp.status_code)
                return False
            body = resp.json() if callable(getattr(resp, "json", None)) else {}
            if body.get("errors"):
                logger.warning("Shopify fulfillmentOrders 오류: %s", body["errors"])
                return False
            order = ((body.get("data") or {}).get("order") or {})
            fo_ids = []
            for edge in ((order.get("fulfillmentOrders") or {}).get("edges") or []):
                fnode = edge.get("node") or {}
                status = str(fnode.get("status") or "").upper()
                if fnode.get("id") and status not in ("CLOSED", "CANCELLED"):
                    fo_ids.append(fnode["id"])
            if not fo_ids:
                logger.warning("Shopify 이행 가능한 fulfillmentOrder 없음: order=%s", order_id)
                return False

            mutation = """
            mutation($fulfillment: FulfillmentV2Input!) {
              fulfillmentCreateV2(fulfillment: $fulfillment) {
                fulfillment { id status }
                userErrors { field message }
              }
            }
            """
            tracking_info: dict = {}
            if tracking_no:
                tracking_info["number"] = tracking_no
            if courier:
                tracking_info["company"] = courier
            variables = {
                "fulfillment": {
                    "lineItemsByFulfillmentOrder": [{"fulfillmentOrderId": fid} for fid in fo_ids],
                    "trackingInfo": tracking_info,
                    "notifyCustomer": False,
                }
            }
            resp2 = self._market().graphql(mutation, variables)
            if not (200 <= resp2.status_code < 300):
                logger.warning("Shopify fulfillmentCreateV2 HTTP %s", resp2.status_code)
                return False
            body2 = resp2.json() if callable(getattr(resp2, "json", None)) else {}
            if body2.get("errors"):
                logger.warning("Shopify fulfillmentCreateV2 GraphQL 오류: %s", body2["errors"])
                return False
            result = (((body2.get("data") or {}).get("fulfillmentCreateV2")) or {})
            user_errors = result.get("userErrors") or []
            if user_errors:
                logger.warning("Shopify 운송장 등록 userErrors: %s", user_errors)
                return False
            if result.get("fulfillment"):
                logger.info("Shopify 운송장 등록 완료: order=%s, %s/%s", order_id, courier, tracking_no)
                return True
            return False
        except Exception as exc:
            logger.warning("Shopify update_tracking 실패: %s", exc)
            return False

    def health_check(self) -> dict:
        """Shopify API 상태 확인."""
        if not _api_active():
            return {
                "status": "missing",
                "detail": "SHOPIFY_AUTO_TOKEN/SHOPIFY_SHOP 미설정",
                "hint": "https://partners.shopify.com 에서 Private App 생성",
            }

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1"}

        try:
            import requests
            token = _access_token()
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
