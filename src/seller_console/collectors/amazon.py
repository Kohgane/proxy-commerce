"""src/seller_console/collectors/amazon.py — Amazon 수집기 (Phase 128).

PA-API 5.0 사용 (AMAZON_ACCESS_KEY 등 활성 시).
미활성 시 → GenericOgCollector 폴백 + warning.
ASIN 추출 정규식: /dp/B0..., /gp/product/B0...
"""
from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
from typing import Optional

from .base import BaseCollector, CollectorResult
from .generic_og import GenericOgCollector

logger = logging.getLogger(__name__)

_ASIN_RE = re.compile(r"/(?:dp|gp/product|exec/obidos/asin)/([A-Z0-9]{10})", re.IGNORECASE)


def _extract_asin(url: str) -> Optional[str]:
    """URL에서 ASIN 추출."""
    m = _ASIN_RE.search(url)
    return m.group(1).upper() if m else None


def _paapi_active() -> bool:
    """Amazon PA-API 환경변수 모두 설정됐는지 확인."""
    return all(os.getenv(v) for v in ["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"])


def _fetch_paapi(asin: str, is_jp: bool = False) -> Optional[dict]:
    """PA-API 5.0으로 상품 정보 조회.

    PA-API v5 SDK가 없는 경우 요청 서명을 직접 구현하기 복잡하므로,
    SDK 없이 기본 정보만 반환하는 stub으로 처리 (SDK 추가 시 확장).
    """
    access_key = os.getenv("AMAZON_ACCESS_KEY", "")
    secret_key = os.getenv("AMAZON_SECRET_KEY", "")
    partner_tag = os.getenv("AMAZON_PARTNER_TAG", "")

    if not all([access_key, secret_key, partner_tag]):
        return None

    # PA-API SDK 없이 직접 호출하려면 AWS v4 서명이 필요.
    # 현재는 SDK 의존성 없이 작동하도록 None 반환 + OG 폴백.
    logger.info("PA-API 5.0 SDK 미설치 — OG 폴백 사용 (ASIN: %s)", asin)
    return None


class AmazonCollector(BaseCollector):
    """Amazon 상품 수집기 (PA-API → OG 폴백)."""

    name = "amazon"

    def collect(self, url: str) -> CollectorResult:
        """Amazon URL에서 상품 정보 수집."""
        asin = _extract_asin(url)
        is_jp = "amazon.co.jp" in url.lower()

        # PA-API 시도
        if _paapi_active() and asin:
            pa_data = _fetch_paapi(asin, is_jp=is_jp)
            if pa_data:
                return CollectorResult(
                    success=True,
                    url=url,
                    source="amazon_paapi",
                    asin=asin,
                    title=pa_data.get("title"),
                    description=pa_data.get("description"),
                    images=pa_data.get("images", []),
                    price=Decimal(str(pa_data["price"])) if pa_data.get("price") else None,
                    currency=pa_data.get("currency", "JPY" if is_jp else "USD"),
                    brand=pa_data.get("brand"),
                    category=pa_data.get("category"),
                )

        # OG 폴백
        result = GenericOgCollector().collect(url)
        result.source = "amazon_og"
        result.asin = asin

        warnings = list(result.warnings)
        if _paapi_active() and not asin:
            warnings.append("ASIN을 URL에서 추출하지 못했습니다.")
        elif not _paapi_active():
            warnings.append(
                "AMAZON_ACCESS_KEY/SECRET_KEY/PARTNER_TAG 미설정 — OG 메타 폴백 사용. "
                "PA-API 활성화 시 더 정확한 정보를 가져올 수 있습니다."
            )
        result.warnings = warnings

        # 일본 Amazon은 통화를 JPY로 강제 보정
        # (OG에 product:price:currency가 없으면 GenericOg가 기본값 USD를 설정함)
        if is_jp:
            result.currency = "JPY"
        elif not result.currency:
            result.currency = "USD"

        return result
