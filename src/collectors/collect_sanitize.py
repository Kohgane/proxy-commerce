"""collect_sanitize — 저장 직전 서버 단일 지점 검증(v55 STEP2).

모든 수집 경로(확장·북마클릿·수동)가 저장 전에 통과하는 sanity 게이트. 오너 확정 버그:
- '9 KRW' 저장 = sanity가 needs_check 표기만 하고 값을 안 지움 → **비상식 가격은 값을 폐기**(누락 처리).
- 갤러리 타 상품 오염 = 서버에서도 이미지 도메인·중복·비상품 URL 필터로 방어.

가짜 확정 금지: 통화 미상·KRW<100 등은 가격 필드를 비우고 price_status=needs_check + 정직 경고.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

# 통화별 비상식 하한(재고·리뷰·쿠폰 숫자 오인 저장 거부).
_MIN_PRICE = {"KRW": 100, "JPY": 10, "CNY": 1, "USD": 0.5, "EUR": 0.5, "GBP": 0.5, "TWD": 3, "HKD": 3}

# v72 STEP2: 가격 정규화 단일 관문 — 문자열 → 정규화 숫자 문자열. 저장 직전 여기만 통과한다.
#   ①머리·꼬리 비숫자 제거(통화기호·공백·문자) ②천단위 콤마 제거 ③소수점 1개만 검증 ④Decimal 확정.
#   "81800."(꼬리 점)·"1,234"(콤마)·"29.99"·"₩81,800"·"81800.00" 전부 계약. 실패 시 ("", False)(원문 보존은 호출측, 0.00 저장 금지).
_PRICE_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize_price(raw: Any) -> Tuple[str, bool]:
    """가격 문자열을 정규화된 숫자 문자열로. 반환 (정규화값, 성공여부). 실패 시 ('', False)."""
    s = "" if raw is None else str(raw).strip()
    if not s:
        return "", False
    m = _PRICE_NUM_RE.search(s)
    if not m:
        return "", False
    token = m.group(0).replace(",", "")   # 천단위 콤마 제거
    # 꼬리 점(소수부 숫자 없음)은 정규식이 이미 배제('\.\d+' 필수) → "81800." → "81800".
    if token in ("", ".") or token.count(".") > 1:
        return "", False
    try:
        d = Decimal(token)
    except (InvalidOperation, ValueError):
        return "", False
    if d <= 0:
        return "", False
    # 정규화 문자열: 유효 숫자 토큰 그대로(소수부 정보 보존, 꼬리 점·콤마·기호 제거됨).
    return token, True

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
    # v72 STEP2: 단일 정규화 관문 통과 — "81800."·"1,234"·"₩81,800" → 정규화. 실패/0 → 누락(0.00 저장 금지).
    norm, ok = normalize_price(price)
    if not ok:
        return "", "needs_check", warnings                         # 빈값/0/파싱실패 → 누락(원문은 호출측 extra에 보존)
    if not cur:
        return "", "needs_check", ["통화를 확인하지 못했어요"]      # 통화 미상 → 값 폐기(임의 확정 금지)
    v = float(norm)
    if cur in _MIN_PRICE and v < _MIN_PRICE[cur]:
        # ★ v55: 비상식 하한 미만이면 값을 **폐기**(9 저장 금지) + 정직 경고.
        return "", "needs_check", [f"가격이 비상식적으로 낮아요({cur} {v:g}) — 재고/쿠폰 숫자 오인으로 폐기"]
    return norm, "", warnings                                      # 정규화된 값 저장(꼬리 점·콤마 제거)


def renormalize_price_field(current: Any) -> Tuple[str, bool]:
    """v72 STEP2: 기저장 오염 가격 재정규화용. 현재 저장값을 정규화 관문에 다시 통과 →
    정규화 결과가 현재와 다르면 (정규화값, True), 아니면 (원값, False). 실패면 (원값, False)로 원문 보존."""
    cur = "" if current is None else str(current).strip()
    norm, ok = normalize_price(cur)
    if ok and norm != cur:
        return norm, True
    return cur, False


def canonical_price(*candidates) -> str:
    """v72b STEP1: 정본 가격 단일 소스 — 여러 후보(price → price_original → item.price) 중 첫 **정규화 성공값**.
    드로어·마진계산·마켓 등록이 모두 이 함수로 동일 값을 읽는다(이원화 제거). 실패면 '' (0.00 저장 금지)."""
    for c in candidates:
        norm, ok = normalize_price(c)
        if ok:
            return norm
    return ""


def renormalize_all(items_iter, update_fn) -> Dict[str, int]:
    """v72 STEP2: 기저장 오염 가격 재정규화 배치(주입식 — 스토어 비의존, 테스트 용이).

    items_iter: (item_id, current_price) 튜플 이터러블. update_fn(item_id, new_price): 실제 저장.
    반환 {scanned, changed}. 원문 보존(파싱 실패는 미변경)·0.00 저장 금지(빈값은 미변경)."""
    scanned = 0
    changed = 0
    for item_id, price in items_iter:
        scanned += 1
        new, ch = renormalize_price_field(price)
        if ch:
            update_fn(item_id, new)
            changed += 1
    return {"scanned": scanned, "changed": changed}


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
