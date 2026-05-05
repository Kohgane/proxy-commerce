"""src/seller_console/market_adapters/eleven_adapter.py — 11번가 어댑터 (Phase 128).

실 API 연동: 11번가 OpenAPI 단순 API key 헤더.
XML 응답 파싱.
환경변수 미설정 시 stub 모드 자동 폴백.
ADAPTER_DRY_RUN=1 시 실 API 호출 없이 dry-run 응답 반환.

환경변수:
  ELEVENST_API_KEY — 11번가 API 키
  ADAPTER_DRY_RUN  — 1 이면 실 API 호출 차단
"""
from __future__ import annotations

import logging
import os
from typing import List
from xml.etree import ElementTree

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.11st.co.kr/rest"


def _api_active() -> bool:
    return bool(os.getenv("ELEVENST_API_KEY"))


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _auth_headers() -> dict:
    return {"openapikey": os.getenv("ELEVENST_API_KEY", "")}


def _stub_response(action: str = "fetch_inventory") -> dict:
    return {
        "status": "stub",
        "action": action,
        "detail": "ELEVENST_API_KEY 미설정 — stub 모드",
    }


def _dry_run_response(action: str = "upload_product") -> dict:
    return {
        "status": "dry_run",
        "action": action,
        "detail": "ADAPTER_DRY_RUN=1 — 실제 API 호출 차단됨",
    }


def _parse_xml_products(xml_text: str) -> list:
    """11번가 XML 상품 목록 파싱."""
    items = []
    try:
        root = ElementTree.fromstring(xml_text)
        for product in root.findall(".//Product"):
            product_id = product.findtext("productCode") or product.findtext("prdCd") or ""
            title = product.findtext("productName") or product.findtext("prdNm") or ""
            price_text = product.findtext("sellprc") or product.findtext("price") or "0"
            status = product.findtext("productStatusCode") or "01"  # 01=판매중
            try:
                price_krw = int(float(price_text))
            except (ValueError, TypeError):
                price_krw = None
            items.append(MarketStatusItem(
                marketplace="11st",
                product_id=product_id,
                state="active" if status == "01" else "suspended",
                title=title,
                price_krw=price_krw,
            ))
    except ElementTree.ParseError as exc:
        logger.warning("11번가 XML 파싱 실패: %s", exc)
    return items


class ElevenAdapter(MarketAdapter):
    """11번가 OpenAPI 어댑터 (Phase 128)."""

    marketplace = "11st"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """11번가 API에서 상품 목록 조회."""
        if not _api_active():
            logger.warning("11번가 API 키 미설정 — stub 모드")
            return []

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — 11번가 fetch_inventory dry-run")
            return []

        try:
            import requests
            resp = requests.get(
                f"{_BASE_URL}/prodservices/product/productlist",
                headers=_auth_headers(),
                params={"sellerPrdCd": "", "prdStatusCd": "01", "pageNum": 1, "pageSize": 50},
                timeout=10,
            )
            resp.raise_for_status()
            return _parse_xml_products(resp.text)
        except Exception as exc:
            logger.warning("11번가 fetch_inventory 실패: %s", exc)
            return []

    def upload_product(self, product: dict) -> dict:
        """11번가에 상품 등록."""
        if not _api_active():
            return _stub_response("upload_product")

        if _dry_run():
            return _dry_run_response("upload_product")

        try:
            import requests
            import json
            resp = requests.post(
                f"{_BASE_URL}/prodservices/product",
                headers={**_auth_headers(), "Content-Type": "application/json"},
                json=product,
                timeout=10,
            )
            resp.raise_for_status()
            return {"status": "ok", "response": resp.text}
        except Exception as exc:
            logger.warning("11번가 upload_product 실패: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def health_check(self) -> dict:
        """11번가 API 상태 확인."""
        if not _api_active():
            return {
                "status": "missing",
                "detail": "ELEVENST_API_KEY 미설정",
                "hint": "https://soffice.11st.co.kr 에서 API 키 발급",
            }

        if _dry_run():
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1"}

        try:
            import requests
            resp = requests.get(
                f"{_BASE_URL}/prodservices/product/productlist",
                headers=_auth_headers(),
                params={"pageNum": 1, "pageSize": 1},
                timeout=5,
            )
            if resp.status_code == 200:
                return {"status": "ok", "detail": "11번가 API 연결 성공"}
            return {"status": "fail", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            logger.warning("11번가 health_check 실패: %s", exc)
            return {"status": "fail", "detail": str(exc)}
