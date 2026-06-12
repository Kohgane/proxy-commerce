"""채널 업로드 브리지 공통 헬퍼.

UploadDispatcher의 `product_data`(ProductDraft 계열 dict)를
`src.uploaders.*Uploader.prepare_product()`가 기대하는 collected 형식으로 변환하고,
자격증명 확인 → prepare → upload → 결과 정규화를 공통 수행한다.

honest-UI 원칙:
- 자격증명 미설정 → ChannelCredentialsMissing (디스패처가 token_missing으로 표기)
- API 실패 / 원화 판매가 0 → ChannelUploadError (디스패처가 api_error로 표기)
- 성공 → {"product_id": ..., "url": ...}

실 API 호출은 자격증명이 있을 때만 발생하며, 라이브 검증은 운영 환경에서 수행한다.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ChannelCredentialsMissing(RuntimeError):
    """채널 API 자격증명(환경변수) 미설정."""


class ChannelUploadError(RuntimeError):
    """채널 API 업로드 실패 또는 업로드 불가(원화가 0 등)."""


def _first_positive_number(*values: Any) -> float | None:
    """주어진 값들 중 처음으로 양수로 해석되는 값을 반환."""
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def to_collected(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """디스패처 product_data → uploaders.prepare_product()용 collected 형식.

    원화 판매가는 sell_price_krw → recommended_price(_krw) → price_krw →
    (통화가 KRW일 때) price 순으로 가장 먼저 양수인 값을 채택한다.
    """
    pd = product_data or {}
    currency = str(pd.get("currency") or "").upper()
    price_if_krw = pd.get("price") if currency == "KRW" else None

    sell_price_krw = _first_positive_number(
        pd.get("sell_price_krw"),
        pd.get("recommended_price_krw"),
        pd.get("recommended_price"),
        pd.get("price_krw"),
        price_if_krw,
    )
    cost_price_krw = _first_positive_number(pd.get("price_krw"), sell_price_krw) or 0

    options = pd.get("options")
    tags = pd.get("keywords")
    if not isinstance(tags, list):
        tags = pd.get("tags") if isinstance(pd.get("tags"), list) else []

    return {
        "sku": str(pd.get("sku") or pd.get("asin") or "").strip(),
        "title_ko": str(pd.get("title_ko") or pd.get("title") or "").strip(),
        "title_original": str(pd.get("title_en") or pd.get("title") or "").strip(),
        "sell_price_krw": int(round(sell_price_krw)) if sell_price_krw else 0,
        "price_krw": int(round(cost_price_krw)),
        "category_code": str(pd.get("category_code") or pd.get("category") or "GEN").strip() or "GEN",
        "description_html": str(pd.get("description_html") or pd.get("description") or "").strip(),
        "images": pd.get("images") if isinstance(pd.get("images"), list) else [],
        "brand": str(pd.get("brand") or "").strip(),
        "weight_kg": pd.get("weight_kg"),
        "options": options if isinstance(options, (dict, list)) else {},
        "tags": tags,
    }


def run_upload(
    uploader: Any,
    product_data: Dict[str, Any],
    *,
    required_envs: List[str],
    market_label: str,
) -> Dict[str, Any]:
    """공통 업로드 실행 — 자격증명 확인 → 변환 → 업로드 → 결과 정규화.

    Returns:
        {"product_id": str|None, "url": str|None}
    Raises:
        ChannelCredentialsMissing: 필수 환경변수 미설정
        ChannelUploadError: 원화 판매가 0 또는 API 실패
    """
    missing = [key for key in required_envs if not os.getenv(key)]
    if missing:
        raise ChannelCredentialsMissing(
            f"{market_label} 자격증명 미설정: {', '.join(missing)}"
        )

    collected = to_collected(product_data)
    if collected["sell_price_krw"] <= 0:
        raise ChannelUploadError(
            f"{market_label} 업로드 불가: 원화 판매가(sell_price_krw)가 0입니다."
        )

    prepared = uploader.prepare_product(collected)
    resp = uploader.upload_product(prepared)

    if not isinstance(resp, dict) or not resp.get("success"):
        error = resp.get("error") if isinstance(resp, dict) else "알 수 없는 오류"
        raise ChannelUploadError(f"{market_label} 업로드 실패: {error}")

    return {
        "product_id": str(resp.get("product_id") or "").strip() or None,
        "url": str(resp.get("url") or "").strip() or None,
    }
