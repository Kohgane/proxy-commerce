"""collect_sanitize — 저장 직전 서버 단일 지점 검증(v55 STEP2).

모든 수집 경로(확장·북마클릿·수동)가 저장 전에 통과하는 sanity 게이트. 오너 확정 버그:
- '9 KRW' 저장 = sanity가 needs_check 표기만 하고 값을 안 지움 → **비상식 가격은 값을 폐기**(누락 처리).
- 갤러리 타 상품 오염 = 서버에서도 이미지 도메인·중복·비상품 URL 필터로 방어.

가짜 확정 금지: 통화 미상·KRW<100 등은 가격 필드를 비우고 price_status=needs_check + 정직 경고.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

# 통화별 비상식 하한(재고·리뷰·쿠폰 숫자 오인 저장 거부).
_MIN_PRICE = {"KRW": 100, "JPY": 10, "CNY": 1, "USD": 0.5, "EUR": 0.5, "GBP": 0.5, "TWD": 3, "HKD": 3}

# 비상품 이미지 URL 패턴(로고·아이콘·배너·스프라이트·플레이스홀더·픽셀).
_NON_PRODUCT_IMG = re.compile(
    r"(logo|sprite|icon|avatar|placeholder|loading|blank|pixel|spacer|1x1|banner|watermark|badge|flag|"
    r"btn[-_]|button|arrow|chevron|star[-_]|rating|coupon|thumb_up|footer|header[-_]|nav[-_])",
    re.I,
)


def _to_float(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return -1.0


def sanitize_price(price: Any, currency: Any) -> Tuple[str, str, List[str]]:
    """(price_str, price_status, warnings) 반환. 비상식/미상 → **값 폐기('')** + needs_check(가짜 확정 금지)."""
    warnings: List[str] = []
    cur = str(currency or "").strip().upper()
    p_raw = "" if price is None else str(price).strip()
    if p_raw in ("", "0", "0.0", "0.00"):
        return "", "needs_check", warnings                         # 빈값/0 → 누락
    if not cur:
        return "", "needs_check", ["통화를 확인하지 못했어요"]      # 통화 미상 → 값 폐기(임의 확정 금지)
    v = _to_float(p_raw)
    if v <= 0:
        return "", "needs_check", warnings
    if cur in _MIN_PRICE and v < _MIN_PRICE[cur]:
        # ★ v55: 비상식 하한 미만이면 값을 **폐기**(9 저장 금지) + 정직 경고.
        return "", "needs_check", [f"가격이 비상식적으로 낮아요({cur} {v:g}) — 재고/쿠폰 숫자 오인으로 폐기"]
    return p_raw, "", warnings


def is_product_image(src: str) -> bool:
    if not src or not isinstance(src, str):
        return False
    if src.startswith("data:"):
        return False
    if not re.match(r"^https?://", src):
        return False
    if _NON_PRODUCT_IMG.search(src):
        return False
    return True


def sanitize_images(images: Any, limit: int = 40) -> List[str]:
    """이미지 배열 → 도메인(http)·비상품 URL 제외 + 순서 보존 중복 제거."""
    out: List[str] = []
    seen = set()
    for src in (images or []):
        s = str(src or "").strip()
        if not is_product_image(s):
            continue
        # 쿼리 없는 기준으로 중복 판정(같은 이미지의 크기변형 쿼리 차이 방어는 보수적으로 전체 URL 기준 유지)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """저장 직전 단일 지점 검증 — 가격 폐기 규칙 + 이미지 필터를 payload에 in-place 적용."""
    price, status, warns = sanitize_price(payload.get("price"), payload.get("currency"))
    payload["price"] = price
    payload["price_status"] = status
    if warns:
        existing = list(payload.get("warnings") or [])
        for w in warns:
            if w not in existing:
                existing.append(w)
        payload["warnings"] = existing
    for k in ("images", "gallery_images"):
        if payload.get(k) is not None:
            payload[k] = sanitize_images(payload.get(k))
    if payload.get("detail_images") is not None:
        payload["detail_images"] = sanitize_images(payload.get("detail_images"))
    # 대표/썸네일이 필터로 사라졌으면 갤러리 첫 장으로 보정
    imgs = payload.get("images") or payload.get("gallery_images") or []
    if imgs and not is_product_image(str(payload.get("image") or "")):
        payload["image"] = imgs[0]
    if imgs and not is_product_image(str(payload.get("thumbnail") or "")):
        payload["thumbnail"] = imgs[0]
    return payload
