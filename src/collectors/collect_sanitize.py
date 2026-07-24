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


# ── v83 STEP1: 도메인-통화 정합성(서버 세이프티) ──
#   클라이언트 통화 사다리(kgp-extractor._domainCurrency)의 서버 미러. 단일 통화 도메인만 등재(추측 금지).
#   라쿠텐 상품이 KRW로 들어오면(구글 번역 로케일 오판·구버전 확장) 가격을 **폐기**하고 사유를 남긴다 —
#   1/10 가격 오등록은 KRW<100 가드로 못 잡는다(7,480은 상식 범위라 통과해 버린다).
_DOMAIN_CURRENCY = [
    (re.compile(r"(^|\.)rakuten\.(co\.jp|com)$", re.I), "JPY"),
    (re.compile(r"(^|\.)yoshidakaban\.com$", re.I), "JPY"),
    (re.compile(r"yahoo\.co\.jp$", re.I), "JPY"),
    (re.compile(r"(^|\.)amazon\.co\.jp$", re.I), "JPY"),
    (re.compile(r"(^|\.)amazon\.co\.uk$", re.I), "GBP"),
    (re.compile(r"(^|\.)amazon\.(de|fr|it|es|nl|be|se|pl)$", re.I), "EUR"),
    (re.compile(r"(^|\.)amazon\.com$", re.I), "USD"),
    (re.compile(r"(^|\.)amazon\.ca$", re.I), "CAD"),
    (re.compile(r"(^|\.)amazon\.com\.au$", re.I), "AUD"),
    (re.compile(r"(^|\.)(taobao|tmall|1688)\.com$", re.I), "CNY"),
]


def domain_currency(url: Any) -> str:
    """URL 도메인이 **단일 통화**로 확정되는 소싱처면 그 통화, 아니면 ''(미확정 — 판정 위임)."""
    try:
        p = urlparse(str(url or ""))
        host = (p.hostname or "").lower()
        path = (p.path or "").lower()
    except Exception:
        return ""
    if not host:
        return ""
    for rx, cur in _DOMAIN_CURRENCY:
        if rx.search(host):
            return cur
    # 테무는 다국가 단일 도메인 — 국가 경로(/kr)가 명시된 경우만 확정.
    if re.search(r"(^|\.)temu\.com$", host, re.I):
        return "KRW" if re.match(r"^/kr(/|$)", path) else ""
    return ""


def check_currency_domain(url: Any, currency: Any) -> str:
    """도메인 기준 통화와 어긋나면 사람이 읽는 사유를, 정합/미확정이면 ''를 반환."""
    dom = domain_currency(url)
    cur = str(currency or "").strip().upper()
    if not dom or not cur or dom == cur:
        return ""
    return f"{dom} 표기 사이트인데 {cur}로 들어왔어요 — 통화 불일치로 가격을 보류했어요"


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


# ── v81 STEP5: 제목 새니타이저 서버 봉인 ──
#   클라이언트 _sanitizeTitle(kgp-extractor.js)를 포팅 + 법인 접미(& Co., Inc., Ltd., 株式会社…)까지 제거.
#   코어 폴백(북마클릿 og-meta)은 클라 새니타이저를 안 타므로, 서버 단일 지점(sanitize_payload)이 봉인한다.
#   증거: 'PORTER STROLL 2WAY BAG | YOSHIDA & Co.' 접미 재발 0.
_MARKET_PREFIX_RE = re.compile(r"^【\s*[^】]{0,24}(楽天|市場|store|shop|mall|ストア)[^】]{0,24}】\s*", re.I)
_SITE_PREFIX_RE = re.compile(r"^(amazon(\.[a-z.]+)?|楽天市場|rakuten|aliexpress|temu|qoo10)\s*[:：|｜\-–·]\s*", re.I)
# 사이트/브랜드명(클라 _SITE_BRAND_RE와 동일 집합).
_SITE_BRAND = (
    r"(amazon(\.[a-z.]+)?|aliexpress|rakuten|楽天市場|楽天|temu|qoo10|mercari|メルカリ|메루카리|"
    r"ヤフーショッピング|yahoo!?\s*(shopping|쇼핑)?|paypaymall|吉田カバン|요시다카반|요시다|yoshida(kaban)?|"
    r"iherb|dhgate|tmall|taobao|1688|shopee|ebay)"
)
# 법인 지정 접미(브랜드 뒤에 붙어 $ 앵커를 막던 원인 — & Co., Co., Ltd., Inc., 株式会社, 有限会社…).
_CORP_SUFFIX = r"(?:\s*[&＆]?\s*(?:co\.?(?:,?\s*ltd\.?)?|company|inc\.?|ltd\.?|corp\.?|gmbh|s\.?a\.?|株式会社|有限会社|カバン))*"
_TITLE_SUFFIX_RE = re.compile(
    r"\s*[|｜:：\-–·]\s*" + _SITE_BRAND + _CORP_SUFFIX + r"\s*$", re.I,
)


# v83 STEP3: 아마존 카테고리 사전(클라 _AMZ_CAT_TAIL_RE와 동일 집합) — 제목 꼬리 ' : Home & Kitchen' 절단용.
_AMZ_CATEGORIES = (
    r"Home\s*&\s*Kitchen|Kitchen\s*&\s*Dining|Electronics|Beauty\s*&\s*Personal\s*Care|"
    r"Health\s*&\s*Household|Clothing,?\s*Shoes\s*&\s*Jewelry|Sports\s*&\s*Outdoors|Toys\s*&\s*Games|"
    r"Tools\s*&\s*Home\s*Improvement|Office\s*Products|Pet\s*Supplies|Grocery\s*&\s*Gourmet\s*Food|Baby|"
    r"Automotive|Industrial\s*&\s*Scientific|Musical\s*Instruments|Video\s*Games|Books|Garden\s*&\s*Outdoor|"
    r"Patio,?\s*Lawn\s*&\s*Garden|Cell\s*Phones\s*&\s*Accessories|Computers\s*&\s*Accessories|"
    r"Arts,?\s*Crafts\s*&\s*Sewing|Appliances|Everything\s*Else"
)
_AMZ_CATEGORY_TAIL_RE = re.compile(r"\s*[:：]\s*(" + _AMZ_CATEGORIES + r")\s*$", re.I)


def _brand_from_host(url: str) -> str:
    try:
        from urllib.parse import urlparse as _up
        h = (_up(url).hostname or "").replace("www.", "", 1) if url else ""
    except Exception:
        return ""
    parts = [p for p in h.split(".") if p]
    if len(parts) < 2:
        sld = parts[0] if parts else ""
    else:
        sld = parts[-2]
        if sld in ("co", "com") and len(parts) >= 3:
            sld = parts[-3]
    return sld.lower() if len(sld) >= 4 else ""


def sanitize_title(title: Any, url: Any = "") -> str:
    """제목에서 마켓/사이트/브랜드(+법인 접미)·카테고리 꼬리를 제거. 실패해도 원문 보존(빈 결과 금지)."""
    s = re.sub(r"\s+", " ", str(title if title is not None else "")).strip()
    if not s:
        return ""
    # v83 STEP3: 아마존 카테고리 꼬리(' : Home & Kitchen') 절단 — 사전에 있는 카테고리명일 때만(임의 ':' 절단 금지).
    for _ in range(2):
        before = s
        s = _AMZ_CATEGORY_TAIL_RE.sub("", s).strip()
        if s == before:
            break
    s = _MARKET_PREFIX_RE.sub("", s)
    s = _SITE_PREFIX_RE.sub("", s)
    for _ in range(3):
        before = s
        s = _TITLE_SUFFIX_RE.sub("", s).strip()
        if s == before:
            break
    # 제네릭: 구분자 뒤 마지막 세그먼트가 도메인 브랜드명과 (영숫자 기준) 일치하면 제거.
    brand = _brand_from_host(str(url or ""))
    if brand:
        segs = re.split(r"\s*[|｜·]\s*", s)
        if len(segs) >= 2:
            last = re.sub(r"[^a-z0-9]", "", segs[-1], flags=re.I).lower()
            if last and (last == brand or last.startswith(brand) or brand.startswith(last)):
                segs.pop()
                s = " | ".join(segs)
    s = re.sub(r"\s+", " ", s).strip()
    return s or str(title).strip()   # 전부 지워졌으면(과도 제거) 원문 보존


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """저장 직전 단일 지점 검증 — 제목 새니타이즈 + 가격 폐기 규칙 + 이미지 필터를 payload에 in-place 적용."""
    # v81 STEP5: 제목 봉인 — 코어 폴백(북마클릿)도 여기서 브랜드/법인 접미 제거(클라 미경유 경로 커버).
    if payload.get("title") is not None:
        payload["title"] = sanitize_title(payload.get("title"), payload.get("url") or payload.get("source_url") or "")
    price, status, warns = sanitize_price(payload.get("price"), payload.get("currency"))
    # v83 STEP1: 도메인-통화 정합성 — 어긋나면 값 폐기 + 사유(정직). KRW<100 가드와 병렬(서로 다른 실패 유형).
    _cur_reason = check_currency_domain(payload.get("url") or payload.get("source_url") or "", payload.get("currency"))
    if _cur_reason:
        price, status = "", "needs_check"
        warns = list(warns) + [_cur_reason]
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
