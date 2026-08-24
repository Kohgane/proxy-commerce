"""src/collectors/product_key.py — v42 1-3: 상품 고유키 정규화(중복 수집 방지).

같은 상품을 두 번 수집하면 목록에 두 건이 쌓인다. URL의 상품 고유 ID(도메인별 규칙)를
뽑아 정규화한 키로 '이미 수집한 상품'을 식별한다. 쿼리스트링(_oak_mp_inf 등 트래킹) 제거.

정직: 확실한 도메인 규칙만 하드코딩(Temu goods-id, 아마존 ASIN 등). 규칙 없으면 host+path 폴백.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# 도메인별 상품 ID 규칙: (host 정규식, 키 추출 함수(경로, 쿼리dict) -> str|None)
_AMAZON_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|gp/offer-listing)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
_TEMU_PATH_RE = re.compile(r"(?:^|/)g-(\d{6,})", re.I)          # /g-601150655669129.html
_ALI_RE = re.compile(r"/item/(?:[^/]*?)?(\d{6,})\.html", re.I)  # aliexpress /item/....html
_1688_RE = re.compile(r"/offer/(\d{6,})\.html", re.I)


def _host(netloc: str) -> str:
    h = (netloc or "").lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _query_id(query: str, keys) -> str | None:
    # 가벼운 쿼리 파서(순서 무관), 첫 매칭 key의 값 반환.
    parts = {}
    for kv in (query or "").split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            parts[k.lower()] = v
    for k in keys:
        if parts.get(k):
            return parts[k]
    return None


# 마켓 SKU로 쓸 수 있는 식별자 형태(영숫자 + . _ -, 3~64자). URL 파편(&, =, ?, /, 공백)은 여기서 걸린다.
_VENDOR_SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


def extract_asin(url: str) -> str:
    """아마존 URL → ASIN(10자). **로케일·경로·쿼리 무관**(amazon.de·`/-/en/`·긴 쿼리스트링 포함).

    카나리 8차 근원: `url[-40:]`로 잘라 쓰던 SKU가 쿼리 파편('…&ref_=pd_hp_…')이 되어 쿠팡이 거부.
    규칙은 기존 자산(`_AMAZON_RE`, /dp/·/gp/product/·/gp/aw/d/·/gp/offer-listing/)을 그대로 쓴다(발명 0).
    """
    if not url or not isinstance(url, str):
        return ""
    m = _AMAZON_RE.search(url)
    return m.group(1).upper() if m else ""


def vendor_sku(url: str) -> str:
    """URL → **마켓 등록용 판매자 SKU**(아마존 ASIN·Temu goods-id 등). 못 뽑으면 빈 문자열(정직).

    `normalize_product_key`의 도메인 규칙을 재사용하되, 폴백(host+path)은 SKU가 아니므로 채택하지
    않는다 — 쓰레기 값으로 카나리를 태우지 않기 위해 **빈값 → 호출부가 등록 중단**(택배사 교훈 동형).
    """
    if not url or not isinstance(url, str):
        return ""
    asin = extract_asin(url)
    if asin:
        return asin
    key = normalize_product_key(url)
    # 도메인 규칙이 잡힌 키만 채택(`host:kind:id` 형태). 폴백 키(host+path)는 ':' 규칙이 없다.
    if key.count(":") >= 2:
        ident = key.rsplit(":", 1)[-1]
        if is_valid_vendor_sku(ident):
            return ident
    return ""


def is_valid_vendor_sku(sku: str) -> bool:
    """마켓 SKU로 전송 가능한 식별자인지. URL 파편·공백·특수문자(&, =, ?, /)는 불가."""
    return bool(_VENDOR_SKU_RE.match(str(sku or "").strip()))


def normalize_product_key(url: str) -> str:
    """URL → 상품 고유키. 같은 상품이면 같은 키(쿼리 트래킹 무시)."""
    if not url or not isinstance(url, str):
        return ""
    try:
        u = urlparse(url.strip())
    except Exception:
        return (url or "").strip().lower()
    host = _host(u.netloc)
    path = u.path or ""
    query = u.query or ""

    # 아마존: ASIN(10자) — 마켓플레이스(host)별로 구분.
    if "amazon." in host:
        m = _AMAZON_RE.search(path) or _AMAZON_RE.search(url)
        if m:
            return f"{host}:asin:{m.group(1).upper()}"

    # Temu: goods-id (경로 g-<digits> 또는 쿼리 goods_id).
    if "temu." in host:
        m = _TEMU_PATH_RE.search(path)
        gid = m.group(1) if m else _query_id(query, ("goods_id", "goodsid"))
        if gid:
            return f"temu:goods:{gid}"

    # 타오바오/티몰/1688: 쿼리 id / offer 경로.
    if any(s in host for s in ("taobao.", "tmall.", "1688.")):
        m = _1688_RE.search(path)
        gid = m.group(1) if m else _query_id(query, ("id", "itemid", "offerid"))
        if gid:
            return f"{host}:item:{gid}"

    # 알리익스프레스: /item/<id>.html.
    if "aliexpress." in host:
        m = _ALI_RE.search(path)
        if m:
            return f"ali:item:{m.group(1)}"

    # 폴백: host + path(쿼리·프래그먼트 제거, 끝 슬래시 정규화). 트래킹 쿼리 무시로 중복 대부분 해소.
    p = re.sub(r"/+$", "", path) or "/"
    return f"{host}{p}".lower()
