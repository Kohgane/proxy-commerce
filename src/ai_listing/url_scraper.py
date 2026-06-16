"""src/ai_listing/url_scraper.py — 상품 페이지 URL 스크래핑 (Phase 150).

입력: 상품 페이지 URL
동작:
  1. requests + BeautifulSoup으로 HTML 가져오기
  2. <title>, <meta name="description">, <meta property="og:*"> 추출
  3. <script type="application/ld+json"> (JSON-LD Product schema) 추출
  4. 본문 텍스트 (article, main, .product-detail 등) 추출
  5. 이미지 URL (og:image, srcset, gallery)
  6. 가격 후보 (정규식 + JSON-LD)
  7. 브랜드, 소재, 사이즈, 색상 후보 추출
출력: structured dict
캐시: URL 해시 24h
에러 핸들링: 실패해도 이미지 분석은 계속 진행

환경변수:
  AI_LISTING_URL_SCRAPER_ENABLED        1 = 활성화
  AI_LISTING_URL_SCRAPER_TIMEOUT_SEC    10 = 요청 타임아웃
  AI_LISTING_URL_SCRAPER_USER_AGENT     ProxyCommerceBot/1.0
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from src.ai_listing.jsonld_parser import (
    convert_to_krw,
    extract_material,
    extract_price_from_jsonld,
    extract_variants,
    normalize_jsonld,
)

logger = logging.getLogger(__name__)

_SCRAPER_ENABLED = os.getenv("AI_LISTING_URL_SCRAPER_ENABLED", "1") == "1"
_TIMEOUT_SEC = int(os.getenv("AI_LISTING_URL_SCRAPER_TIMEOUT_SEC", "10"))
_HEAD_GET_FALLBACK = os.getenv("AI_LISTING_URL_HEAD_CHECK_GET_FALLBACK", "1") == "1"
_USER_AGENT = os.getenv(
    "AI_LISTING_URL_SCRAPER_USER_AGENT",
    "ProxyCommerceBot/1.0 (+https://kohganepercentiii.com/privacy)",
)
# 접근성 프로브용 브라우저 UA — 봇 UA를 막는 사이트(yoshidakaban 등)에서
# HEAD가 403/406/500을 반환해도 수집기(universal_scraper)처럼 GET으로 확인.
_PROBE_USER_AGENT = os.getenv(
    "AI_LISTING_URL_PROBE_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
)
_PROBE_HEADERS = {
    "User-Agent": _PROBE_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8,ja;q=0.7",
}
_CACHE_TTL_SEC = int(os.getenv("AI_LISTING_CACHE_TTL_HOURS", "24")) * 3600

# 인메모리 캐시
_scraper_cache: Dict[str, Dict[str, Any]] = {}

# 가격 추출 정규식 (한국원/엔/달러)
_PRICE_RE = re.compile(
    r"(?:₩|￦|KRW|원|¥|JPY|엔|\$|USD)\s*([\d,]+)|"
    r"([\d,]+)\s*(?:원|₩|엔|¥)",
    re.IGNORECASE,
)
_KRW_PRICE_RE = re.compile(
    r"(?:₩|￦|KRW)\s*([\d,]+)|([\d,]+)\s*원",
    re.IGNORECASE,
)
_MAX_REASONABLE_PRICE_KRW = 100_000_000
_MAX_GALLERY_IMAGES = 30
_MAX_PRICE_BODY_FALLBACK_CHARS = 3000
_MAX_PRICE_TEXT_CHARS = 4000

# 소재 키워드
_MATERIAL_KEYWORDS = [
    "면", "cotton", "폴리에스터", "polyester", "울", "wool", "나일론", "nylon",
    "린넨", "linen", "실크", "silk", "가죽", "leather", "데님", "denim",
    "혼방", "blend", "스판덱스", "spandex", "아크릴", "acrylic",
    "레이온", "rayon", "모달", "modal", "비스코스", "viscose",
]

# 색상 키워드
_COLOR_KEYWORDS = [
    "블랙", "black", "화이트", "white", "그레이", "gray", "grey",
    "네이비", "navy", "블루", "blue", "레드", "red", "핑크", "pink",
    "옐로우", "yellow", "그린", "green", "베이지", "beige", "브라운", "brown",
    "퍼플", "purple", "오렌지", "orange", "카키", "khaki", "아이보리", "ivory",
    "민트", "mint", "라벤더", "lavender", "코랄", "coral",
]

# 사이즈 패턴
_SIZE_RE = re.compile(
    r"\b(?:XS|S|M|L|XL|XXL|XXXL|2XL|3XL|FREE|프리|소|중|대)\b|"
    r"\b(?:55|66|77|88|95|100|105|110)\b|"
    r"\b(?:\d{2,3}(?:\s*cm)?)\b",
    re.IGNORECASE,
)


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _validate_public_url(url: str) -> str | None:
    """URL 형식/SSRF 보호 검증. 통과 시 None, 실패 시 에러 문자열."""
    if not url or not url.startswith(("http://", "https://")):
        return "유효하지 않은 URL"

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            return "유효하지 않은 URL (호스트 없음)"
        blocked_hosts = (
            "localhost",
            "127.",
            "0.",
            "10.",
            "172.16.",
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
            "192.168.",
            "::1",
            "[::1]",
            "0.0.0.0",
            "169.254.",
            "fd",
        )
        hostname_lower = hostname.lower()
        if any(
            hostname_lower == blocked or hostname_lower.startswith(blocked)
            for blocked in blocked_hosts
        ):
            return f"내부 네트워크 URL 접근 차단: {hostname}"
        if hostname_lower in ("metadata.google.internal", "169.254.169.254"):
            return "메타데이터 URL 접근 차단"
    except Exception:
        return "URL 파싱 실패"
    return None


def head_check_url(url: str, timeout_sec: int | None = None) -> Dict[str, Any]:
    """URL HEAD 유효성 확인 (200 여부)."""
    err = _validate_public_url(url)
    if err:
        return {"ok": False, "status": None, "error": err}

    try:
        import requests
    except ImportError as exc:
        return {"ok": False, "status": None, "error": f"의존성 미설치: {exc}"}

    timeout = timeout_sec or _TIMEOUT_SEC
    # 2xx/3xx(최종 200) = 접근 가능. 봇 UA를 막는 사이트가 많아 수집기와 동일한
    # 브라우저 UA + Accept 헤더로 프로브하고, HEAD가 막히면 GET으로 재확인한다.
    head_status: Optional[int] = None
    try:
        resp = requests.head(
            url,
            timeout=timeout,
            headers=_PROBE_HEADERS,
            allow_redirects=True,
        )
        head_status = int(resp.status_code)
        if head_status < 400:
            return {"ok": True, "status": head_status, "error": None}
    except Exception:
        head_status = None

    # HEAD가 실패/4xx/5xx → 실제 수집과 동일한 GET으로 재확인(많은 사이트가 GET만 허용)
    if _HEAD_GET_FALLBACK:
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={**_PROBE_HEADERS, "Range": "bytes=0-2048"},
                allow_redirects=True,
                stream=True,
            )
            status = int(resp.status_code)
            resp.close()
            ok = status < 400
            return {"ok": ok, "status": status, "error": None if ok else f"HTTP {status}"}
        except Exception as exc:
            return {"ok": False, "status": head_status, "error": str(exc)}

    return {
        "ok": False,
        "status": head_status,
        "error": f"HTTP {head_status}" if head_status is not None else "연결 실패",
    }


def _extract_json_ld(soup: Any) -> List[Dict[str, Any]]:
    """JSON-LD 스크립트 태그에서 구조화 데이터 추출."""
    results: List[Dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return results


def _find_product_schema(json_ld_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """JSON-LD에서 Product 스키마 탐색."""
    for item in json_ld_items:
        type_val = item.get("@type", "")
        if isinstance(type_val, list):
            type_val = " ".join(type_val)
        if "Product" in str(type_val):
            return item
        # @graph 안에 Product가 있을 수 있음
        graph = item.get("@graph", [])
        for node in graph:
            node_type = node.get("@type", "")
            if "Product" in str(node_type):
                return node
    return None


def _extract_price_from_schema(product: Dict[str, Any]) -> List[int]:
    """Product 스키마에서 가격 추출."""
    prices: List[int] = []
    offers = product.get("offers") or product.get("Offers")
    if not offers:
        return prices
    if isinstance(offers, dict):
        offers = [offers]
    for offer in offers:
        price_val = offer.get("price") or offer.get("lowPrice") or offer.get("highPrice")
        if price_val is not None:
            try:
                prices.append(int(float(str(price_val).replace(",", ""))))
            except (ValueError, TypeError):
                pass
    return prices


def _extract_prices_from_text(text: str) -> List[int]:
    """텍스트에서 가격 후보 추출."""
    prices: List[int] = []
    for match in _PRICE_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            try:
                val = int(raw.replace(",", ""))
                if 100 <= val <= 100_000_000:  # 100원 ~ 1억원 범위
                    prices.append(val)
            except ValueError:
                pass
    return list(set(prices))


def _extract_krw_prices(text: str) -> List[int]:
    prices: List[int] = []
    for match in _KRW_PRICE_RE.finditer(text or ""):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        try:
            val = int(raw.replace(",", ""))
        except ValueError:
            continue
        if 100 <= val <= _MAX_REASONABLE_PRICE_KRW:
            prices.append(val)
    return sorted(set(prices))


def _to_absolute_url(raw: str, base_url: str) -> str:
    src = str(raw or "").strip()
    if not src:
        return ""
    if src.startswith("//"):
        return f"https:{src}"
    if src.startswith("/"):
        return urljoin(base_url, src)
    return src


def _pick_best_srcset_url(srcset: str) -> str:
    best_url = ""
    best_score = -1
    for part in (srcset or "").split(","):
        chunk = part.strip()
        if not chunk:
            continue
        bits = chunk.split()
        url = bits[0]
        descriptor = bits[1] if len(bits) > 1 else ""
        score = 0
        if descriptor.endswith("w"):
            try:
                score = int(descriptor[:-1])
            except ValueError:
                score = 0
        elif descriptor.endswith("x"):
            try:
                score = int(float(descriptor[:-1]) * 1000)
            except ValueError:
                score = 0
        if score >= best_score:
            best_url = url
            best_score = score
    return best_url


def _is_valid_image_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return False
    lowered = u.lower()
    if lowered.startswith(("http://localhost", "https://localhost")):
        return False
    if lowered.endswith((".js", ".css", ".svg")):
        return False
    return True


def _extract_image_urls(soup: Any, page_url: str, jsonld_urls: List[str], og_image: str) -> List[str]:
    base_domain = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    candidates: List[str] = []

    if og_image:
        candidates.append(_to_absolute_url(og_image, base_domain))
    candidates.extend([_to_absolute_url(i, base_domain) for i in (jsonld_urls or [])])

    for img_tag in soup.find_all("img"):
        for attr in ("data-zoom-image", "data-large-image", "data-src", "src"):
            raw = img_tag.get(attr)
            if raw:
                candidates.append(_to_absolute_url(raw, base_domain))
        for srcset_attr in ("data-srcset", "srcset"):
            best = _pick_best_srcset_url(str(img_tag.get(srcset_attr) or ""))
            if best:
                candidates.append(_to_absolute_url(best, base_domain))

    deduped: List[str] = []
    seen: Set[str] = set()
    for candidate in candidates:
        if not _is_valid_image_url(candidate):
            continue
        key = candidate.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped[:_MAX_GALLERY_IMAGES]


def _extract_price_text(soup: Any, title: str, description: str) -> str:
    chunks: List[str] = [title or "", description or ""]
    seeded_len = len(chunks)
    selectors = [
        '[class*="price"]',
        '[class*="cost"]',
        '[id*="price"]',
        '[id*="cost"]',
        '[data-price]',
        '[itemprop="price"]',
    ]
    for selector in selectors:
        for node in soup.select(selector):
            txt = node.get_text(separator=" ", strip=True)
            if txt:
                chunks.append(txt[:120])
    for meta in soup.find_all("meta"):
        prop = str(meta.get("property", "") or meta.get("name", "")).lower()
        if "price" in prop or "cost" in prop:
            content = str(meta.get("content", "")).strip()
            if content:
                chunks.append(content)
    if len(chunks) == seeded_len:
        body = soup.find("body")
        if body:
            chunks.append(body.get_text(separator=" ", strip=True)[:_MAX_PRICE_BODY_FALLBACK_CHARS])
    return " ".join(chunks)[:_MAX_PRICE_TEXT_CHARS]


def _extract_candidates_from_text(text: str, keywords: List[str]) -> List[str]:
    """텍스트에서 키워드 목록과 매칭되는 후보 추출."""
    found = []
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)
    return found


def _extract_sizes_from_text(text: str) -> List[str]:
    """텍스트에서 사이즈 후보 추출."""
    return list(set(_SIZE_RE.findall(text)))


def _get_body_text(soup: Any, max_chars: int = 3000) -> str:
    """본문 텍스트 추출 (article > main > .product-detail > body 순서)."""
    for selector in [
        "article",
        "main",
        '[class*="product-detail"]',
        '[class*="product_detail"]',
        '[class*="product-description"]',
        '[id*="product-detail"]',
        "section",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 100:
                return text[:max_chars]
    # fallback: 전체 body
    body = soup.find("body")
    if body:
        return body.get_text(separator=" ", strip=True)[:max_chars]
    return ""


def scrape_product_page(url: str, force_refresh: bool = False) -> Dict[str, Any]:
    """상품 페이지 URL 스크래핑.

    Args:
        url:           상품 페이지 URL
        force_refresh: True 시 캐시 무시

    Returns:
        {
          "title": str,
          "description": str,
          "price_candidates": [int],
          "brand_candidates": [str],
          "material_candidates": [str],
          "size_candidates": [str],
          "color_candidates": [str],
          "origin_country": str | None,
          "images": [str],
          "raw_text_truncated": str,
          "_source_url": str,
          "_scraped": bool,
          "_error": str | None,
        }
    """
    empty_result: Dict[str, Any] = {
        "title": "",
        "description": "",
        "price_candidates": [],
        "brand_candidates": [],
        "material_candidates": [],
        "size_candidates": [],
        "color_candidates": [],
        "origin_country": None,
        "images": [],
        "raw_text_truncated": "",
        "_source_url": url,
        "_scraped": False,
        "_error": None,
        "_http_status": None,
        "_response_size": 0,
        "_json_ld": [],
        "json_ld_normalized": {},
        "variants": [],
        "source_price": None,
        "source_price_krw": None,
        "fx_rate": None,
        "_og_tags": {},
        "_meta_description": "",
        "_cache_hit": False,
    }

    if not _SCRAPER_ENABLED:
        empty_result["_error"] = "scraper disabled"
        return empty_result

    err = _validate_public_url(url)
    if err:
        empty_result["_error"] = err
        return empty_result

    url_key = _url_hash(url)

    if force_refresh:
        _scraper_cache.pop(url_key, None)

    # 캐시 확인
    if not force_refresh and url_key in _scraper_cache:
        cached = _scraper_cache[url_key]
        if time.time() - cached.get("_cached_at", 0) < _CACHE_TTL_SEC:
            logger.debug("URL 스크래퍼 캐시 히트: %s", url_key[:8])
            return {**cached["result"], "_cache_hit": True}

    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        empty_result["_error"] = f"의존성 미설치: {exc}"
        return empty_result

    try:
        # 수집기(universal_scraper)와 동일한 브라우저 헤더 사용 — 봇 UA를 막는
        # 사이트(yoshidakaban 등)에서 500/403을 피하고 실제 수집과 동작을 일치시킨다.
        resp = requests.get(
            url,
            timeout=_TIMEOUT_SEC,
            headers=_PROBE_HEADERS,
            allow_redirects=True,
        )
        status_raw = getattr(resp, "status_code", 200)
        status_code = status_raw if isinstance(status_raw, int) else 200
        empty_result["_http_status"] = status_code
        if status_code != 200:
            empty_result["_error"] = f"HTTP {status_code}"
            return empty_result
        html = str(getattr(resp, "text", "") or "")
        content_bytes = getattr(resp, "content", b"")
        if not isinstance(content_bytes, (bytes, bytearray)):
            content_length = str(getattr(resp, "headers", {}).get("Content-Length", "") or "").strip()
            if content_length.isdigit():
                empty_result["_response_size"] = int(content_length)
            else:
                enc_raw = getattr(resp, "encoding", None)
                enc = enc_raw if isinstance(enc_raw, str) and enc_raw else "utf-8"
                content_bytes = html.encode(enc, errors="ignore")
                empty_result["_response_size"] = len(content_bytes)
        else:
            empty_result["_response_size"] = len(content_bytes)
    except Exception as exc:
        logger.warning("URL 스크래핑 실패 (%s): %s", url, exc)
        empty_result["_error"] = str(exc)
        return empty_result

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        logger.warning("HTML 파싱 실패 (%s): %s", url, exc)
        empty_result["_error"] = str(exc)
        return empty_result

    # ── 기본 메타 추출 ────────────────────────────────────────────────
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = (title_tag.get_text(strip=True) or "")[:200]

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = str(meta_desc.get("content", ""))[:500]

    # OG 태그
    og_title = ""
    og_desc = ""
    og_image = ""
    for meta in soup.find_all("meta"):
        prop = str(meta.get("property", "") or meta.get("name", ""))
        content = str(meta.get("content", ""))
        if prop == "og:title":
            og_title = content[:200]
        elif prop == "og:description":
            og_desc = content[:500]
        elif prop == "og:image":
            og_image = content

    if og_title:
        title = og_title
    if og_desc and not description:
        description = og_desc
    og_tags = {
        "title": og_title,
        "description": og_desc,
        "image": og_image,
    }

    # ── JSON-LD 추출 ──────────────────────────────────────────────────
    json_ld_items = _extract_json_ld(soup)
    product_schema = _find_product_schema(json_ld_items)
    json_ld_normalized = normalize_jsonld(json_ld_items)
    variants = extract_variants(json_ld_normalized.get("hasVariant", []))
    price_info = extract_price_from_jsonld(json_ld_normalized)

    price_candidates: List[int] = []
    brand_candidates: List[str] = []
    origin_country: Optional[str] = None
    source_price: Optional[Dict[str, Any]] = None
    source_price_raw: Optional[Dict[str, Any]] = None
    source_price_krw: Optional[int] = None
    source_market_price_krw: Optional[int] = None
    source_market_price_regular_krw: Optional[int] = None
    source_market_price_source: Optional[str] = None
    fx_rate = None

    if product_schema:
        # 제목 (스키마 우선)
        schema_name = str(product_schema.get("name", ""))
        if schema_name:
            title = schema_name[:200]

        # 설명
        schema_desc = str(product_schema.get("description", ""))
        if schema_desc and not description:
            description = schema_desc[:500]

        # 가격
        price_candidates = _extract_price_from_schema(product_schema)

        # 브랜드
        brand_obj = product_schema.get("brand")
        if isinstance(brand_obj, dict):
            brand_name = str(brand_obj.get("name", ""))
            if brand_name:
                brand_candidates.append(brand_name)
        elif isinstance(brand_obj, str) and brand_obj:
            brand_candidates.append(brand_obj)

        # 원산지
        country = product_schema.get("countryOfOrigin") or product_schema.get("country")
        if isinstance(country, dict):
            origin_country = str(country.get("name", "")) or None
        elif isinstance(country, str):
            origin_country = country or None

    if json_ld_normalized.get("name"):
        title = json_ld_normalized["name"][:200]
    if json_ld_normalized.get("description") and not description:
        description = str(json_ld_normalized["description"])[:500]
    brand_name = (json_ld_normalized.get("brand") or {}).get("name", "")
    if brand_name:
        brand_candidates = [brand_name] + [b for b in brand_candidates if b != brand_name]
    if price_info:
        try:
            converted = convert_to_krw(price_info["amount"], price_info["currency"])
            source_price_krw = converted["amount_krw"]
            fx_rate = converted["rate"]
            source_price = {
                "amount": str(price_info["amount"]),
                "currency": price_info["currency"],
                "amount_krw": source_price_krw,
                "rate": str(converted["rate"]),
                "source": price_info["source"],
            }
            source_price_raw = dict(source_price)
            price_candidates = [source_price_krw]
        except Exception:
            price_candidates = _extract_price_from_schema(product_schema) if product_schema else []

    # 페이지 표시 KRW 가격(세일/정가) 추출 우선
    display_krw_prices = _extract_krw_prices(_extract_price_text(soup, title, description))
    if display_krw_prices:
        source_market_price_krw = min(display_krw_prices)
        source_market_price_regular_krw = max(display_krw_prices)
        if source_market_price_regular_krw == source_market_price_krw:
            source_market_price_regular_krw = None
        source_market_price_source = "display.krw"
        if source_market_price_krw not in price_candidates:
            price_candidates.append(source_market_price_krw)
        if source_market_price_regular_krw and source_market_price_regular_krw not in price_candidates:
            price_candidates.append(source_market_price_regular_krw)

        # JSON-LD 통화와 페이지 표시 통화가 불일치하면 로컬 표시 KRW를 우선 사용
        if (
            source_price is None
            or str(source_price.get("currency", "")).upper() != "KRW"
        ):
            source_price_krw = source_market_price_krw
            fx_rate = 1
            source_price = {
                "amount": str(source_market_price_krw),
                "currency": "KRW",
                "amount_krw": source_market_price_krw,
                "rate": "1",
                "source": "display.krw",
            }

    # ── 이미지 목록 ───────────────────────────────────────────────────
    images = _extract_image_urls(
        soup=soup,
        page_url=url,
        jsonld_urls=json_ld_normalized.get("image_urls", []) or [],
        og_image=og_image,
    )

    # ── 본문 텍스트 추출 ──────────────────────────────────────────────
    raw_text = _get_body_text(soup, max_chars=3000)

    # ── 텍스트 기반 후보 추출 ──────────────────────────────────────────
    combined_text = f"{title} {description} {raw_text}"

    if not price_candidates:
        price_candidates = _extract_prices_from_text(combined_text)

    material_candidates = _extract_candidates_from_text(combined_text, _MATERIAL_KEYWORDS)
    color_candidates = _extract_candidates_from_text(combined_text, _COLOR_KEYWORDS)
    size_candidates = _extract_sizes_from_text(combined_text)
    material_from_desc = extract_material(json_ld_normalized.get("description", "") or description)
    if material_from_desc:
        material_candidates = [material_from_desc] + [m for m in material_candidates if m != material_from_desc]
    for variant in variants:
        color = str(variant.get("color") or "").strip()
        size = str(variant.get("size") or "").strip()
        if color and color not in color_candidates:
            color_candidates.append(color)
        if size and size not in size_candidates:
            size_candidates.append(size)

    # OG/meta에서 브랜드 힌트
    for meta in soup.find_all("meta"):
        prop = str(meta.get("property", "") or meta.get("name", ""))
        content = str(meta.get("content", ""))
        if prop in ("og:brand", "product:brand", "brand") and content:
            if content not in brand_candidates:
                brand_candidates.append(content)

    result: Dict[str, Any] = {
        "title": title,
        "description": description,
        "price_candidates": sorted(set(price_candidates)),
        "brand_candidates": brand_candidates[:5],
        "material_candidates": list(dict.fromkeys(material_candidates))[:10],
        "size_candidates": size_candidates[:20],
        "color_candidates": list(dict.fromkeys(color_candidates))[:15],
        "origin_country": origin_country,
        "images": images[:10],
        "raw_text_truncated": raw_text[:2000],
        "json_ld_normalized": json_ld_normalized,
        "variants": variants,
        "source_price": source_price,
        "source_price_raw": source_price_raw,
        "source_price_krw": source_price_krw,
        "source_market_price_krw": source_market_price_krw,
        "source_market_price_regular_krw": source_market_price_regular_krw,
        "source_market_price_source": source_market_price_source,
        "fx_rate": str(fx_rate) if fx_rate is not None else None,
        "_source_url": url,
        "_scraped": True,
        "_error": None,
        "_http_status": status_code,
        "_response_size": empty_result["_response_size"],
        "_json_ld": json_ld_items[:3],
        "_og_tags": og_tags,
        "_meta_description": description,
        "_cache_hit": False,
    }

    _scraper_cache[url_key] = {"result": result, "_cached_at": time.time()}
    logger.info(
        "URL 스크래핑 완료: %s | 가격후보 %d건, 이미지 %d건",
        url[:60],
        len(result["price_candidates"]),
        len(result["images"]),
    )
    return result


def scraper_cache_stats() -> Dict[str, Any]:
    """스크래퍼 캐시 통계."""
    now = time.time()
    total = len(_scraper_cache)
    active = sum(
        1
        for v in _scraper_cache.values()
        if now - v.get("_cached_at", 0) < _CACHE_TTL_SEC
    )
    return {"total": total, "active": active, "ttl_hours": _CACHE_TTL_SEC // 3600}
