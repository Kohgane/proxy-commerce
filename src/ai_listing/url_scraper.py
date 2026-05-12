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
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_SCRAPER_ENABLED = os.getenv("AI_LISTING_URL_SCRAPER_ENABLED", "1") == "1"
_TIMEOUT_SEC = int(os.getenv("AI_LISTING_URL_SCRAPER_TIMEOUT_SEC", "10"))
_USER_AGENT = os.getenv(
    "AI_LISTING_URL_SCRAPER_USER_AGENT",
    "ProxyCommerceBot/1.0 (+https://kohganepercentiii.com/privacy)",
)
_CACHE_TTL_SEC = int(os.getenv("AI_LISTING_CACHE_TTL_HOURS", "24")) * 3600

# 인메모리 캐시
_scraper_cache: Dict[str, Dict[str, Any]] = {}

# 가격 추출 정규식 (한국원/엔/달러)
_PRICE_RE = re.compile(
    r"(?:₩|￦|KRW|원|¥|JPY|엔|\$|USD)\s*([\d,]+)|"
    r"([\d,]+)\s*(?:원|₩|엔|¥)",
    re.IGNORECASE,
)

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
    }

    if not _SCRAPER_ENABLED:
        empty_result["_error"] = "scraper disabled"
        return empty_result

    if not url or not url.startswith(("http://", "https://")):
        empty_result["_error"] = "유효하지 않은 URL"
        return empty_result

    # SSRF 방지: 사설/내부 IP 주소 차단
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # 빈 호스트 차단
        if not hostname:
            empty_result["_error"] = "유효하지 않은 URL (호스트 없음)"
            return empty_result
        # localhost 및 내부 주소 차단
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
            "169.254.",  # link-local
            "fd",  # IPv6 unique local prefix
        )
        hostname_lower = hostname.lower()
        if any(
            hostname_lower == blocked or hostname_lower.startswith(blocked)
            for blocked in blocked_hosts
        ):
            empty_result["_error"] = f"내부 네트워크 URL 접근 차단: {hostname}"
            return empty_result
        # metadata URL 차단 (cloud provider metadata endpoints)
        if hostname_lower in ("metadata.google.internal", "169.254.169.254"):
            empty_result["_error"] = "메타데이터 URL 접근 차단"
            return empty_result
    except Exception:
        empty_result["_error"] = "URL 파싱 실패"
        return empty_result

    url_key = _url_hash(url)

    # 캐시 확인
    if not force_refresh and url_key in _scraper_cache:
        cached = _scraper_cache[url_key]
        if time.time() - cached.get("_cached_at", 0) < _CACHE_TTL_SEC:
            logger.debug("URL 스크래퍼 캐시 히트: %s", url_key[:8])
            return cached["result"]

    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        empty_result["_error"] = f"의존성 미설치: {exc}"
        return empty_result

    try:
        resp = requests.get(
            url,
            timeout=_TIMEOUT_SEC,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
            allow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
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

    # ── JSON-LD 추출 ──────────────────────────────────────────────────
    json_ld_items = _extract_json_ld(soup)
    product_schema = _find_product_schema(json_ld_items)

    price_candidates: List[int] = []
    brand_candidates: List[str] = []
    origin_country: Optional[str] = None

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

    # ── 이미지 목록 ───────────────────────────────────────────────────
    images: List[str] = []
    if og_image:
        images.append(og_image)

    base_domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    for img_tag in soup.find_all("img"):
        src = img_tag.get("src") or img_tag.get("data-src") or ""
        if not src:
            # srcset에서 첫 번째 URL 추출
            srcset = img_tag.get("srcset", "")
            if srcset:
                src = srcset.split(",")[0].strip().split(" ")[0]
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(base_domain, src)
            if src.startswith("http") and src not in images:
                images.append(src)
        if len(images) >= 10:
            break

    # ── 본문 텍스트 추출 ──────────────────────────────────────────────
    raw_text = _get_body_text(soup, max_chars=3000)

    # ── 텍스트 기반 후보 추출 ──────────────────────────────────────────
    combined_text = f"{title} {description} {raw_text}"

    if not price_candidates:
        price_candidates = _extract_prices_from_text(combined_text)

    material_candidates = _extract_candidates_from_text(combined_text, _MATERIAL_KEYWORDS)
    color_candidates = _extract_candidates_from_text(combined_text, _COLOR_KEYWORDS)
    size_candidates = _extract_sizes_from_text(combined_text)

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
        "_source_url": url,
        "_scraped": True,
        "_error": None,
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
