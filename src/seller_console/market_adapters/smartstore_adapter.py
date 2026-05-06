"""src/seller_console/market_adapters/smartstore_adapter.py — 스마트스토어 어댑터 (Phase 128).

실 API 연동: 네이버 커머스 API OAuth 2.0 client_credentials.
환경변수 미설정 시 stub 모드 자동 폴백.
ADAPTER_DRY_RUN=1 시 실 API 호출 없이 dry-run 응답 반환.

환경변수:
  NAVER_COMMERCE_CLIENT_ID       — 네이버 커머스 API 클라이언트 ID
  NAVER_COMMERCE_CLIENT_SECRET   — 클라이언트 시크릿
  ADAPTER_DRY_RUN                — 1 이면 실 API 호출 차단 (테스트용)
"""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)

_NAVER_AUTH_URL = "https://api.commerce.naver.com/external/v1/oauth2/token"
_NAVER_BASE_URL = "https://api.commerce.naver.com"

# 토큰 캐시 (메모리)
_token_cache: dict = {}


def _api_active() -> bool:
    return all(os.getenv(v) for v in ["NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET"])


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _get_access_token() -> Optional[str]:
    """OAuth 2.0 client_credentials로 액세스 토큰 발급/갱신."""
    now = time.time()
    cached = _token_cache.get("smartstore")
    if cached and cached.get("expires_at", 0) > now + 60:
        return cached["access_token"]

    client_id = os.getenv("NAVER_COMMERCE_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_COMMERCE_CLIENT_SECRET", "")

    try:
        import requests
        resp = requests.post(
            _NAVER_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "type": "SELF",
            },
            timeout=10,
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data.get("access_token")
        expires_in = int(token_data.get("expires_in", 3600))
        _token_cache["smartstore"] = {
            "access_token": access_token,
            "expires_at": now + expires_in,
        }
        logger.info("스마트스토어 OAuth 토큰 발급 성공")
        return access_token
    except Exception as exc:
        logger.warning("스마트스토어 토큰 발급 실패: %s", exc)
        return None


def _stub_response(action: str = "fetch_inventory") -> dict:
    return {
        "status": "stub",
        "action": action,
        "detail": "NAVER_COMMERCE_CLIENT_ID/SECRET 미설정 — stub 모드",
    }


def _dry_run_response(action: str = "upload_product") -> dict:
    return {
        "status": "dry_run",
        "action": action,
        "detail": "ADAPTER_DRY_RUN=1 — 실제 API 호출 차단됨",
    }


class SmartStoreAdapter(MarketAdapter):
    """스마트스토어 네이버 커머스 API 어댑터 (Phase 128)."""

    marketplace = "smartstore"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """스마트스토어 API에서 상품 목록 조회."""
        if not _api_active():
            logger.warning("스마트스토어 API 키 미설정 — stub 모드")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 스마트스토어 fetch_inventory dry-run")
            return []

        token = _get_access_token()
        if not token:
            return []

        try:
            import requests
            resp = requests.get(
                f"{_NAVER_BASE_URL}/external/v2/products",
                headers={"Authorization": f"Bearer {token}"},
                params={"size": 50, "page": 1},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = []
            for p in data.get("contents", []):
                items.append(MarketStatusItem(
                    marketplace="smartstore",
                    product_id=str(p.get("originProductNo", "")),
                    state="active" if p.get("saleStatus") == "ON_SALE" else "suspended",
                    sku=str(p.get("channelProducts", [{}])[0].get("channelProductNo", "")) or None,
                    title=p.get("name"),
                    price_krw=int(p.get("salePrice", 0)) or None,
                ))
            return items
        except Exception as exc:
            logger.warning("스마트스토어 fetch_inventory 실패: %s", exc)
            return []

    def upload_product(self, product: dict) -> dict:
        """스마트스토어에 상품 등록."""
        if not _api_active():
            return _stub_response("upload_product")

        if _dry_run():
            return _dry_run_response("upload_product")

        token = _get_access_token()
        if not token:
            return {"status": "error", "detail": "토큰 발급 실패"}

        try:
            import requests
            resp = requests.post(
                f"{_NAVER_BASE_URL}/external/v2/products",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=product,
                timeout=10,
            )
            resp.raise_for_status()
            return {"status": "ok", "data": resp.json()}
        except Exception as exc:
            logger.warning("스마트스토어 upload_product 실패: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def update_price(self, sku: str, new_price_krw: int) -> dict:
        """스마트스토어 상품 가격 업데이트 (Phase 136).

        네이버 커머스 API:
            PUT /external/v2/products/{originProductNo}/sale-price

        Args:
            sku: 상품 SKU (originProductNo 또는 sellerProductId로 사용)
            new_price_krw: 새 판매가 (원)

        Returns:
            {"updated": True|False, "reason": str, ...}
        """
        if not _api_active():
            return {"updated": False, "reason": "missing_credentials"}

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 스마트스토어 update_price 차단: %s → %d원", sku, new_price_krw)
            return {"updated": False, "_dry_run": True, "sku": sku, "price": new_price_krw}

        token = _get_access_token()
        if not token:
            return {"updated": False, "reason": "token_error", "sku": sku}

        # originProductNo 조회
        origin_no = self._find_origin_product_no(sku, token)
        if not origin_no:
            logger.warning("스마트스토어 originProductNo 조회 실패: sku=%s", sku)
            return {"updated": False, "reason": "product_not_found", "sku": sku}

        try:
            import requests
            resp = requests.patch(
                f"{_NAVER_BASE_URL}/external/v2/products/{origin_no}/sale-price",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"salePrice": new_price_krw},
                timeout=10,
            )
            if resp.status_code in (200, 204):
                logger.info("스마트스토어 가격 업데이트 성공: %s → %d원", sku, new_price_krw)
                return {"updated": True, "sku": sku, "price": new_price_krw}
            logger.warning("스마트스토어 가격 업데이트 실패 HTTP %s: %s", resp.status_code, resp.text[:200])
            return {"updated": False, "reason": f"HTTP {resp.status_code}", "sku": sku}
        except Exception as exc:
            logger.warning("스마트스토어 update_price 오류 (%s): %s", sku, exc)
            return {"updated": False, "reason": str(exc), "sku": sku}

    def _find_origin_product_no(self, sku: str, token: str) -> Optional[str]:
        """SKU로 originProductNo 조회."""
        try:
            import requests
            resp = requests.get(
                f"{_NAVER_BASE_URL}/external/v2/products",
                headers={"Authorization": f"Bearer {token}"},
                params={"sellerCode": sku, "size": 1},
                timeout=10,
            )
            if resp.status_code == 200:
                contents = resp.json().get("contents", [])
                if contents:
                    return str(contents[0].get("originProductNo", ""))
        except Exception as exc:
            logger.warning("스마트스토어 originProductNo 조회 오류: %s", exc)
        return None

    def fetch_orders_unified(self, since=None, until=None) -> list:
        """스마트스토어 주문 조회 → UnifiedOrder 목록."""
        from src.seller_console.orders.models import (
            OrderLineItem,
            OrderStatus,
            UnifiedOrder,
            mask_address,
            mask_name,
            mask_phone,
        )
        from decimal import Decimal
        from datetime import datetime, timedelta

        if not _api_active():
            logger.warning("스마트스토어 API 키 미설정 — 빈 목록 반환")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 스마트스토어 fetch_orders_unified dry-run")
            return []

        token = _get_access_token()
        if not token:
            return []

        since_str = (since or datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

        try:
            import requests
            resp = requests.get(
                f"{_NAVER_BASE_URL}/external/v1/pay-order/seller/orders",
                headers={"Authorization": f"Bearer {token}"},
                params={"lastChangedFrom": since_str, "lastChangedType": "PAYED"},
                timeout=10,
            )
            resp.raise_for_status()
            raw_orders = resp.json().get("data", {}).get("contents", [])
        except Exception as exc:
            logger.warning("스마트스토어 fetch_orders_unified 실패: %s", exc)
            return []

        _status_map = {
            "PAYMENT_WAITING": OrderStatus.NEW,
            "PAYED": OrderStatus.PAID,
            "DELIVERING": OrderStatus.SHIPPED,
            "DELIVERED": OrderStatus.DELIVERED,
            "CANCELED": OrderStatus.CANCELED,
            "RETURNED": OrderStatus.RETURNED,
            "EXCHANGED": OrderStatus.EXCHANGED,
        }

        results = []
        for raw in raw_orders:
            try:
                order_id = str(raw.get("orderNo", ""))
                status = _status_map.get(str(raw.get("paymentStatus", "PAYED")), OrderStatus.PAID)
                placed_str = raw.get("orderDate") or raw.get("paymentDate") or ""
                try:
                    placed_at = datetime.strptime(placed_str[:19], "%Y-%m-%dT%H:%M:%S")
                except Exception:
                    placed_at = datetime.utcnow()

                items = []
                for prod in raw.get("productOrderList", []):
                    items.append(OrderLineItem(
                        sku=str(prod.get("productId", "")),
                        title=str(prod.get("productName", "")),
                        qty=int(prod.get("quantity", 1)),
                        unit_price_krw=Decimal(str(prod.get("unitPrice", 0))),
                    ))

                orderer = raw.get("orderer", {})
                delivery = raw.get("deliveryAddress", {})
                results.append(UnifiedOrder(
                    order_id=order_id,
                    marketplace="smartstore",
                    status=status,
                    placed_at=placed_at,
                    buyer_name_masked=mask_name(orderer.get("name", "")),
                    buyer_phone_masked=mask_phone(orderer.get("tel", "")),
                    buyer_address_masked=mask_address(delivery.get("addressDetail", "")),
                    total_krw=Decimal(str(raw.get("totalPaymentAmount", 0))),
                    shipping_fee_krw=Decimal(str(raw.get("deliveryFeeAmount", 0))),
                    items=items,
                    raw=raw,
                ))
            except Exception as exc:
                logger.warning("스마트스토어 주문 정규화 실패: %s", exc)
                continue

        return results

    def fetch_orders(self) -> list:
        """스마트스토어 주문 조회 (하위 호환)."""
        return self.fetch_orders_unified()

    def update_tracking(self, order_id: str, courier: str = "", tracking_no: str = "") -> bool:
        """스마트스토어 운송장 등록."""
        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 스마트스토어 update_tracking 차단: %s", order_id)
            return True

        if not _api_active():
            return False

        token = _get_access_token()
        if not token:
            return False

        try:
            import requests
            resp = requests.post(
                f"{_NAVER_BASE_URL}/external/v1/pay-order/seller/product-orders/dispatch",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "dispatchProductOrders": [
                        {
                            "productOrderId": order_id,
                            "deliveryMethod": "DELIVERY",
                            "deliveryCompanyCode": courier,
                            "trackingNumber": tracking_no,
                        }
                    ]
                },
                timeout=10,
            )
            if resp.status_code in (200, 201):
                return True
            logger.warning("스마트스토어 운송장 등록 실패 HTTP %s", resp.status_code)
            return False
        except Exception as exc:
            logger.warning("스마트스토어 update_tracking 오류: %s", exc)
            return False

    def health_check(self) -> dict:
        """스마트스토어 API 상태 확인."""
        if not _api_active():
            return {
                "status": "missing",
                "detail": "NAVER_COMMERCE_CLIENT_ID/SECRET 미설정",
                "hint": "https://commerce.naver.com 에서 API 키 발급",
            }

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1"}

        token = _get_access_token()
        if token:
            return {"status": "ok", "detail": "스마트스토어 OAuth 토큰 발급 성공"}
        return {"status": "fail", "detail": "토큰 발급 실패 — 클라이언트 ID/시크릿 확인 필요"}
