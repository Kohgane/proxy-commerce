"""src/seller_console/market_adapters/coupang_adapter.py — 쿠팡 윙 어댑터 (Phase 128).

실 API 연동: 쿠팡 윙 OpenAPI HMAC-SHA256 서명.
환경변수 미설정 시 stub 모드 자동 폴백.
ADAPTER_DRY_RUN=1 시 실 API 호출 없이 dry-run 응답 반환.

환경변수:
  COUPANG_VENDOR_ID    — 쿠팡 벤더 ID
  COUPANG_ACCESS_KEY   — 액세스 키
  COUPANG_SECRET_KEY   — 시크릿 키
  ADAPTER_DRY_RUN      — 1 이면 실 API 호출 차단 (테스트용)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlencode

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api-gateway.coupang.com"


def _api_active() -> bool:
    return all(os.getenv(v) for v in ["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"])


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _hmac_sign(method: str, url_path: str, query: str = "") -> dict:
    """쿠팡 HMAC-SHA256 서명 헤더 생성.

    Returns:
        Authorization 헤더를 포함한 dict
    """
    access_key = os.getenv("COUPANG_ACCESS_KEY", "")
    secret_key = os.getenv("COUPANG_SECRET_KEY", "")

    dt = datetime.now(tz=timezone.utc)
    # 쿠팡 윙 OpenAPI 규격: 2자리 연도 (%y) 사용 (예: 261023T143512Z)
    # 참고: https://developers.coupang.com/doc/OpenAPI_v2_20230427.pdf
    datetime_str = dt.strftime("%y%m%dT%H%M%SZ")
    # HMAC 서명: 날짜시간 + HTTP메서드 + 경로 + 쿼리 (순서 고정)
    message = f"{datetime_str}{method}{url_path}{query}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    auth = (
        f"CEA algorithm=HmacSHA256, access-key={access_key}, "
        f"signed-date={datetime_str}, signature={signature}"
    )
    return {
        "Authorization": auth,
        "Content-Type": "application/json;charset=UTF-8",
    }


def _stub_response(action: str = "fetch_inventory") -> dict:
    return {
        "status": "stub",
        "action": action,
        "detail": "COUPANG_VENDOR_ID/ACCESS_KEY/SECRET_KEY 미설정 — stub 모드",
    }


def _dry_run_response(action: str = "upload_product") -> dict:
    return {
        "status": "dry_run",
        "action": action,
        "detail": "ADAPTER_DRY_RUN=1 — 실제 API 호출 차단됨",
    }


class CoupangAdapter(MarketAdapter):
    """쿠팡 윙 OpenAPI 어댑터 (Phase 128).

    API 키 없으면 stub 모드, ADAPTER_DRY_RUN=1 이면 dry-run 모드.
    """

    marketplace = "coupang"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """쿠팡 API에서 재고/상품 상태 조회."""
        if not _api_active():
            logger.warning("쿠팡 API 키 미설정 — stub 모드")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 쿠팡 fetch_inventory dry-run")
            return []

        vendor_id = os.getenv("COUPANG_VENDOR_ID", "")
        url_path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        try:
            import requests
            headers = _hmac_sign("GET", url_path)
            resp = requests.get(
                f"{_BASE_URL}{url_path}",
                headers=headers,
                params={"vendorId": vendor_id, "status": "APPROVED"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = []
            for p in data.get("data", []):
                items.append(MarketStatusItem(
                    marketplace="coupang",
                    product_id=str(p.get("sellerProductId", "")),
                    state="active" if p.get("statusName") == "승인완료" else "error",
                    sku=str(p.get("sellerProductCode", "")) or None,
                    title=p.get("sellerProductName"),
                    price_krw=int(p.get("salePrice", 0)) or None,
                ))
            return items
        except Exception as exc:
            logger.warning("쿠팡 fetch_inventory 실패: %s", exc)
            return []

    def upload_product(self, product: dict) -> dict:
        """쿠팡에 상품 등록.

        Args:
            product: 상품 데이터 dict

        Returns:
            등록 결과 dict
        """
        if not _api_active():
            return _stub_response("upload_product")

        if _dry_run():
            return _dry_run_response("upload_product")

        url_path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        try:
            import requests
            import json
            headers = _hmac_sign("POST", url_path)
            resp = requests.post(
                f"{_BASE_URL}{url_path}",
                headers=headers,
                json=product,
                timeout=10,
            )
            resp.raise_for_status()
            return {"status": "ok", "data": resp.json()}
        except Exception as exc:
            logger.warning("쿠팡 upload_product 실패: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def update_price(self, sku: str, new_price_krw: int) -> dict:
        """쿠팡 상품 가격 업데이트 (Phase 136).

        쿠팡 윙 OpenAPI:
            PUT /v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{vendorItemId}/prices

        SKU로 vendorItemId를 조회한 뒤 가격을 업데이트합니다.

        Args:
            sku: 상품 SKU
            new_price_krw: 새 판매가 (원)

        Returns:
            {"updated": True|False, "reason": str, ...}
        """
        if not _api_active():
            return {"updated": False, "reason": "missing_credentials"}

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 쿠팡 update_price 차단: %s → %d원", sku, new_price_krw)
            return {"updated": False, "_dry_run": True, "sku": sku, "price": new_price_krw}

        vendor_id = os.getenv("COUPANG_VENDOR_ID", "")
        # Step 1: SKU로 vendorItemId 조회
        vendor_item_id = self._find_vendor_item_id(sku, vendor_id)
        if not vendor_item_id:
            logger.warning("쿠팡 vendorItemId 조회 실패: sku=%s", sku)
            return {"updated": False, "reason": "vendor_item_not_found", "sku": sku}

        # Step 2: 가격 업데이트
        url_path = (
            f"/v2/providers/seller_api/apis/api/v1/marketplace/"
            f"seller-products/{vendor_item_id}/prices"
        )
        try:
            import requests
            headers = _hmac_sign("PUT", url_path)
            resp = requests.put(
                f"{_BASE_URL}{url_path}",
                headers=headers,
                json={"vendorItemId": vendor_item_id, "originalPrice": new_price_krw, "salePrice": new_price_krw},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                logger.info("쿠팡 가격 업데이트 성공: %s → %d원", sku, new_price_krw)
                return {"updated": True, "sku": sku, "price": new_price_krw, "marketplace_response": resp.json()}
            logger.warning("쿠팡 가격 업데이트 실패 HTTP %s: %s", resp.status_code, resp.text[:200])
            return {"updated": False, "reason": f"HTTP {resp.status_code}", "sku": sku}
        except Exception as exc:
            logger.warning("쿠팡 update_price 오류 (%s): %s", sku, exc)
            return {"updated": False, "reason": str(exc), "sku": sku}

    def _find_vendor_item_id(self, sku: str, vendor_id: str) -> Optional[str]:
        """SKU로 쿠팡 vendorItemId 조회."""
        url_path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        try:
            import requests
            headers = _hmac_sign("GET", url_path)
            resp = requests.get(
                f"{_BASE_URL}{url_path}",
                headers=headers,
                params={"vendorId": vendor_id, "sellerProductCode": sku},
                timeout=10,
            )
            if resp.status_code == 200:
                for product in resp.json().get("data", []):
                    for item in product.get("items", []):
                        if item.get("sellerProductItemCode") == sku or product.get("sellerProductCode") == sku:
                            return str(item.get("vendorItemId", ""))
        except Exception as exc:
            logger.warning("쿠팡 vendorItemId 조회 오류: %s", exc)
        return None

    def fetch_orders_unified(self, since=None, until=None) -> list:
        """쿠팡 주문 조회 → UnifiedOrder 목록.

        API 키 미설정 시 mock 3건 반환.
        """
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
            logger.warning("쿠팡 API 키 미설정 — mock 주문 3건 반환")
            now = datetime.utcnow()
            return [
                UnifiedOrder(
                    order_id="CP-MOCK-001",
                    marketplace="coupang",
                    status=OrderStatus.PAID,
                    placed_at=now - timedelta(hours=2),
                    paid_at=now - timedelta(hours=1),
                    buyer_name_masked=mask_name("홍길동"),
                    buyer_phone_masked=mask_phone("010-1234-5678"),
                    buyer_address_masked=mask_address("서울시 강남구 테헤란로 123 456호"),
                    total_krw=Decimal("39000"),
                    shipping_fee_krw=Decimal("3000"),
                    items=[OrderLineItem(sku="SKU-A", title="테스트 상품 A", qty=1, unit_price_krw=Decimal("36000"))],
                    notes="mock 데이터",
                ),
                UnifiedOrder(
                    order_id="CP-MOCK-002",
                    marketplace="coupang",
                    status=OrderStatus.PREPARING,
                    placed_at=now - timedelta(days=1),
                    paid_at=now - timedelta(days=1),
                    buyer_name_masked=mask_name("김철수"),
                    buyer_phone_masked=mask_phone("010-9876-5432"),
                    buyer_address_masked=mask_address("경기도 성남시 분당구 판교로 1 101호"),
                    total_krw=Decimal("78000"),
                    shipping_fee_krw=Decimal("0"),
                    items=[
                        OrderLineItem(sku="SKU-B", title="테스트 상품 B", qty=2, unit_price_krw=Decimal("39000")),
                    ],
                    notes="mock 데이터",
                ),
                UnifiedOrder(
                    order_id="CP-MOCK-003",
                    marketplace="coupang",
                    status=OrderStatus.SHIPPED,
                    placed_at=now - timedelta(days=3),
                    paid_at=now - timedelta(days=3),
                    buyer_name_masked=mask_name("이영희"),
                    buyer_phone_masked=mask_phone("010-5555-7777"),
                    buyer_address_masked=mask_address("부산시 해운대구 해운대로 99 202호"),
                    total_krw=Decimal("55000"),
                    shipping_fee_krw=Decimal("3000"),
                    items=[OrderLineItem(sku="SKU-C", title="테스트 상품 C", qty=1, unit_price_krw=Decimal("52000"))],
                    courier="CJ대한통운",
                    tracking_no="123456789012",
                    shipped_at=now - timedelta(days=2),
                    notes="mock 데이터",
                ),
            ]

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 쿠팡 fetch_orders_unified dry-run")
            return []

        # 실 API 연동: fetch_orders() 호출 후 정규화
        from datetime import datetime as _dt
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S") if since else "2024-01-01T00:00:00"
        raw_orders = self.fetch_orders(created_at_from=since_str)

        from src.seller_console.orders.models import (
            OrderLineItem,
            OrderStatus,
            UnifiedOrder,
            mask_address,
            mask_name,
            mask_phone,
        )
        from decimal import Decimal

        results = []
        for raw in raw_orders:
            try:
                order_id = str(raw.get("orderId", raw.get("orderSheetId", "")))
                status_raw = str(raw.get("orderStatus", "PAYMENTWAITING")).upper()
                _status_map = {
                    "PAYMENTWAITING": OrderStatus.NEW,
                    "PAYMENT_DONE": OrderStatus.PAID,
                    "INSTRUCT": OrderStatus.PREPARING,
                    "ACCEPT": OrderStatus.PREPARING,
                    "IN_TRANSIT": OrderStatus.SHIPPED,
                    "DELIVERED": OrderStatus.DELIVERED,
                    "CANCEL_DONE": OrderStatus.CANCELED,
                    "RETURN_DONE": OrderStatus.RETURNED,
                }
                status = _status_map.get(status_raw, OrderStatus.NEW)
                placed_str = raw.get("orderedAt") or raw.get("orderDate") or ""
                placed_at = None
                if placed_str:
                    try:
                        placed_at = datetime.strptime(placed_str[:19], "%Y-%m-%dT%H:%M:%S")
                    except Exception:
                        placed_at = datetime.utcnow()
                placed_at = placed_at or datetime.utcnow()

                items = []
                for item in raw.get("orderItems", raw.get("items", [])):
                    items.append(OrderLineItem(
                        sku=str(item.get("sellerProductItemCode", item.get("sku", ""))),
                        title=str(item.get("productName", item.get("itemName", ""))),
                        qty=int(item.get("shippingCount", item.get("qty", 1))),
                        unit_price_krw=Decimal(str(item.get("unitPrice", item.get("salePrice", 0)))),
                    ))

                results.append(UnifiedOrder(
                    order_id=order_id,
                    marketplace="coupang",
                    status=status,
                    placed_at=placed_at,
                    total_krw=Decimal(str(raw.get("totalPrice", 0))),
                    shipping_fee_krw=Decimal(str(raw.get("deliveryPrice", 0))),
                    items=items,
                    courier=raw.get("deliveryCompanyCode"),
                    tracking_no=raw.get("invoiceNumber"),
                    raw=raw,
                ))
            except Exception as exc:
                logger.warning("쿠팡 주문 정규화 실패: %s", exc)
                continue

        return results

    def update_tracking(self, order_id: str, shipment_box_id: str = None, courier: str = "", tracking_no: str = "") -> bool:
        """쿠팡 운송장 등록.

        ADAPTER_DRY_RUN=1 이면 로그만 기록 후 True 반환.
        """
        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 쿠팡 update_tracking 차단: %s", order_id)
            return True

        if not _api_active():
            logger.warning("쿠팡 API 키 미설정 — update_tracking 불가")
            return False

        vendor_id = os.getenv("COUPANG_VENDOR_ID", "")
        box_id = shipment_box_id or order_id
        url_path = f"/v2/providers/openapi/apis/api/v4/vendors/{vendor_id}/ordersheets/{box_id}/invoices"
        try:
            import requests
            import json
            headers = _hmac_sign("PUT", url_path)
            payload = {"courierCode": courier, "invoiceNumber": tracking_no}
            resp = requests.put(
                f"{_BASE_URL}{url_path}",
                headers=headers,
                json=payload,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                logger.info("쿠팡 운송장 등록 성공: %s", order_id)
                return True
            logger.warning("쿠팡 운송장 등록 실패 HTTP %s: %s", resp.status_code, resp.text)
            return False
        except Exception as exc:
            logger.warning("쿠팡 update_tracking 오류: %s", exc)
            return False

    def fetch_orders(self, created_at_from: Optional[str] = None) -> list:
        """쿠팡 주문 조회.

        Args:
            created_at_from: 조회 시작 시각 (ISO8601)

        Returns:
            주문 list
        """
        if not _api_active():
            logger.warning("쿠팡 API 키 미설정 — 주문 조회 stub")
            return []

        if _dry_run():
            return []

        vendor_id = os.getenv("COUPANG_VENDOR_ID", "")
        url_path = f"/v2/providers/openapi/apis/api/v4/vendors/{vendor_id}/ordersheets"
        try:
            import requests
            params = {"createdAtFrom": created_at_from or "2024-01-01T00:00:00"} if created_at_from else {}
            headers = _hmac_sign("GET", url_path, urlencode(params) if params else "")
            resp = requests.get(
                f"{_BASE_URL}{url_path}",
                headers=headers,
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as exc:
            logger.warning("쿠팡 fetch_orders 실패: %s", exc)
            return []

    def health_check(self) -> dict:
        """쿠팡 API 상태 확인."""
        if not _api_active():
            return {
                "status": "missing",
                "detail": "COUPANG_VENDOR_ID/ACCESS_KEY/SECRET_KEY 미설정",
                "hint": "https://wing.coupang.com 에서 API 키 발급",
            }

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1"}

        try:
            vendor_id = os.getenv("COUPANG_VENDOR_ID", "")
            url_path = f"/v2/providers/openapi/apis/api/v1/vendors/{vendor_id}"
            import requests
            headers = _hmac_sign("GET", url_path)
            resp = requests.get(f"{_BASE_URL}{url_path}", headers=headers, timeout=5)
            if resp.status_code == 200:
                return {"status": "ok", "detail": "쿠팡 API 연결 성공"}
            return {"status": "fail", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            logger.warning("쿠팡 health_check 실패: %s", exc)
            return {"status": "fail", "detail": str(exc)}
