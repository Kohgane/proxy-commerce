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
