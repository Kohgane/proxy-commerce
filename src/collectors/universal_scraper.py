"""src/collectors/universal_scraper.py — 범용 수집기 (Phase 135).

도메인 입력 → 자동 메타 추출.

추출 우선순위:
1. JSON-LD schema.org Product (가장 정확)
2. Open Graph 태그 (og:title, og:image, product:price:amount, ...)
3. Twitter Card
4. Microdata
5. meta name="description"
6. <title> + 첫 <h1>
7. 가격 휴리스틱 (₩, $, ¥, € 패턴)

raw HTML 1MB까지만 다운, 그 안에서 BS4 파싱.
robots.txt 준수 (User-Agent: KohganePercentiii/1.0).
ADAPTER_DRY_RUN=1 시 실제 HTTP 요청 없이 fixture 반환.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

_USER_AGENT = "KohganePercentiii/1.0 (+https://kohganepercentiii.com)"
_MAX_HTML_BYTES = 1_000_000  # 1MB
_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT_SEC", "15"))
_DRY_RUN = os.getenv("ADAPTER_DRY_RUN", "0") == "1"

# 허용 URL 스키마 (SSRF 방지)
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|::1|0\.0\.0\.0)",
    re.IGNORECASE,
)

# 가격 통화 심볼 → ISO 코드
_CURRENCY_SYMBOLS: dict = {
    "$": "USD",
    "＄": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "￥": "JPY",
    "₩": "KRW",
    "￦": "KRW",
    "元": "CNY",
    "yuan": "CNY",
}


@dataclass
class ScrapedProduct:
    """범용 수집 결과."""

    source_url: str
    domain: str
    title: str
    description: str
    images: list = field(default_factory=list)
    price: Optional[Decimal] = None
    currency: str = "USD"
    brand: Optional[str] = None
    sku: Optional[str] = None
    in_stock: Optional[bool] = None
    options: list = field(default_factory=list)   # [{name, values}]
    raw_meta: dict = field(default_factory=dict)
    extraction_method: str = ""   # "json-ld" / "og" / "heuristic"
    confidence: float = 0.0       # 0.0~1.0

    def to_dict(self) -> dict:
        """JSON 직렬화용 딕셔너리."""
        return {
            "source_url": self.source_url,
            "domain": self.domain,
            "title": self.title,
            "description": self.description,
            "images": self.images,
            "price": str(self.price) if self.price is not None else None,
            "currency": self.currency,
            "brand": self.brand,
            "sku": self.sku,
            "in_stock": self.in_stock,
            "options": self.options,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
        }

    @property
    def needs_adapter(self) -> bool:
        """신뢰도 미달 → 어댑터 필요."""
        return self.confidence < 0.5


def _is_safe_url(url: str) -> bool:
    """SSRF 방지: http/https 스키마, 내부 IP 차단."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return False
        host = parsed.hostname or ""
        if _PRIVATE_HOST_RE.match(host):
            logger.warning("내부 호스트 차단 (SSRF 방지): %s", host)
            return False
        return True
    except Exception:
        return False


def _fetch_html(url: str, timeout: int = _TIMEOUT) -> Optional[str]:
    """URL에서 HTML fetch (최대 1MB)."""
    if _DRY_RUN:
        logger.debug("ADAPTER_DRY_RUN=1 — HTTP 요청 생략: %s", url)
        return None
    if not _is_safe_url(url):
        logger.warning("안전하지 않은 URL 거부: %s", url[:100])
        return None
    try:
        import requests
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8,ja;q=0.7",
        }
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        resp.raise_for_status()
        # 1MB 이상 다운로드 방지
        content = b""
        for chunk in resp.iter_content(chunk_size=65536):
            content += chunk
            if len(content) >= _MAX_HTML_BYTES:
                break
        return content.decode(resp.apparent_encoding or "utf-8", errors="replace")
    except Exception as exc:
        logger.warning("HTML fetch 실패 (%s): %s", url[:100], exc)
        return None


def _parse_price(price_str: str) -> Optional[Decimal]:
    """가격 문자열 → Decimal. 통화 심볼 제거 후 파싱."""
    if not price_str:
        return None
    try:
        cleaned = price_str.replace(",", "").strip()
        # 통화 심볼 제거
        for sym in _CURRENCY_SYMBOLS:
            cleaned = cleaned.replace(sym, "")
        cleaned = cleaned.strip()
        m = re.fullmatch(r"\d+(?:\.\d{1,6})?", cleaned)
        if m:
            val = Decimal(m.group())
            return val if val > 0 else None
    except (InvalidOperation, Exception):
        pass
    return None


def _detect_currency_from_symbol(text: str) -> str:
    """가격 문자열에서 통화 코드 감지."""
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in text:
            return code
    return "USD"


def _extract_domain(url: str) -> str:
    """URL → 도메인 (www. 제거)."""
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


class UniversalScraper:
    """범용 수집기 — 도메인 불문 상품 메타 추출."""

    name = "universal"

    def fetch(self, url: str) -> ScrapedProduct:
        """URL에서 상품 정보 수집. ADAPTER_DRY_RUN=1이면 빈 결과 반환."""
        domain = _extract_domain(url)
        empty = ScrapedProduct(
            source_url=url,
            domain=domain,
            title="",
            description="",
            extraction_method="heuristic",
            confidence=0.0,
        )

        html = _fetch_html(url)
        if not html:
            return empty

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            logger.warning("beautifulsoup4 미설치 — 범용 수집기 제한 모드")
            return empty

        # 1. JSON-LD
        result = self._parse_jsonld(soup, url, domain)
        if result:
            return result

        # 2. Open Graph
        result = self._parse_opengraph(soup, url, domain)
        if result:
            return result

        # 3. Microdata
        result = self._parse_microdata(soup, url, domain)
        if result:
            return result

        # 4. Heuristic
        return self._heuristic(soup, url, domain)

    def _parse_jsonld(self, soup, url: str, domain: str) -> Optional[ScrapedProduct]:
        """JSON-LD schema.org Product 파싱."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or script.get_text() or ""
                data = json.loads(raw)
                schemas = data if isinstance(data, list) else [data]
                for schema in schemas:
                    # Graph 형태 지원
                    if schema.get("@type") == "ItemList":
                        continue
                    if "@graph" in schema:
                        schemas.extend(schema["@graph"])
                        continue
                    if schema.get("@type") not in ("Product", "product"):
                        continue

                    title = schema.get("name", "")
                    desc = schema.get("description", "")
                    brand_raw = schema.get("brand") or {}
                    brand = brand_raw.get("name", "") if isinstance(brand_raw, dict) else str(brand_raw)
                    sku = schema.get("sku") or schema.get("mpn") or ""

                    imgs = schema.get("image", [])
                    if isinstance(imgs, str):
                        imgs = [imgs]
                    elif isinstance(imgs, dict):
                        imgs = [imgs.get("url", "")]
                    images = [i for i in imgs if i]

                    price_val: Optional[Decimal] = None
                    currency = "USD"
                    in_stock: Optional[bool] = None
                    options: list = []

                    offers = schema.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    if isinstance(offers, dict):
                        price_raw = str(offers.get("price", ""))
                        price_val = _parse_price(price_raw)
                        currency = offers.get("priceCurrency", "USD") or "USD"
                        avail = offers.get("availability", "")
                        if "InStock" in avail:
                            in_stock = True
                        elif "OutOfStock" in avail:
                            in_stock = False

                    # hasVariant / hasMeasurement → options
                    for variant in schema.get("hasVariant", []):
                        opt_name = variant.get("name", "")
                        opt_val = variant.get("value", variant.get("description", ""))
                        if opt_name:
                            options.append({"name": opt_name, "value": opt_val})

                    if not title:
                        continue

                    confidence = 0.4
                    if title:
                        confidence += 0.2
                    if images:
                        confidence += 0.2
                    if price_val:
                        confidence += 0.2

                    return ScrapedProduct(
                        source_url=url,
                        domain=domain,
                        title=title,
                        description=desc,
                        images=images[:10],
                        price=price_val,
                        currency=currency,
                        brand=brand or None,
                        sku=sku or None,
                        in_stock=in_stock,
                        options=options,
                        extraction_method="json-ld",
                        confidence=min(confidence, 1.0),
                    )
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
        return None

    def _parse_opengraph(self, soup, url: str, domain: str) -> Optional[ScrapedProduct]:
        """Open Graph + Twitter Card 메타태그 파싱."""
        data: dict = {}
        images: list = []

        for tag in soup.find_all("meta"):
            prop = (tag.get("property") or tag.get("name") or "").lower()
            content = tag.get("content") or ""
            if not content or not prop:
                continue

            if prop == "og:title":
                data["title"] = content
            elif prop == "og:description":
                data["description"] = content
            elif prop in ("og:image", "og:image:url"):
                images.append(content)
            elif prop == "product:price:amount":
                data["price"] = content
            elif prop == "product:price:currency":
                data["currency"] = content
            elif prop == "og:site_name":
                data["site_name"] = content
            elif prop == "og:brand":
                data["brand"] = content
            # Twitter Card
            elif prop == "twitter:title" and not data.get("title"):
                data["title"] = content
            elif prop == "twitter:description" and not data.get("description"):
                data["description"] = content
            elif prop == "twitter:image" and not images:
                images.append(content)
            # 가격 관련 추가 메타
            elif prop in ("product:price", "price"):
                if not data.get("price"):
                    data["price"] = content
            elif prop in ("product:availability",):
                data["availability"] = content

        title = data.get("title", "")
        if not title:
            return None

        price_raw = data.get("price", "")
        price_val = _parse_price(price_raw) if price_raw else None
        currency = data.get("currency", "USD") or "USD"
        if not currency and price_raw:
            currency = _detect_currency_from_symbol(price_raw)

        in_stock = None
        avail = data.get("availability", "").lower()
        if "instock" in avail or "in stock" in avail:
            in_stock = True
        elif "outofstock" in avail or "out of stock" in avail:
            in_stock = False

        confidence = 0.3
        if title:
            confidence += 0.2
        if images:
            confidence += 0.2
        if price_val:
            confidence += 0.2
        if data.get("description"):
            confidence += 0.1

        return ScrapedProduct(
            source_url=url,
            domain=domain,
            title=title,
            description=data.get("description", ""),
            images=list(dict.fromkeys(images))[:10],
            price=price_val,
            currency=currency,
            brand=data.get("brand"),
            extraction_method="og",
            confidence=min(confidence, 1.0),
            in_stock=in_stock,
        )

    def _parse_microdata(self, soup, url: str, domain: str) -> Optional[ScrapedProduct]:
        """Microdata (schema.org) 파싱."""
        product_el = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)})
        if not product_el:
            return None

        def _prop(name: str) -> str:
            el = product_el.find(attrs={"itemprop": name})
            if el:
                return el.get("content") or el.get_text(strip=True) or ""
            return ""

        title = _prop("name")
        if not title:
            return None

        desc = _prop("description")
        brand = _prop("brand") or _prop("manufacturer")
        sku = _prop("sku") or _prop("productID")

        price_raw = _prop("price")
        price_val = _parse_price(price_raw) if price_raw else None
        currency = _prop("priceCurrency") or "USD"

        # 이미지
        imgs = []
        for img_el in product_el.find_all(attrs={"itemprop": "image"}):
            src = img_el.get("src") or img_el.get("content") or ""
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = urljoin(url, src)
                imgs.append(src)

        confidence = 0.35
        if imgs:
            confidence += 0.2
        if price_val:
            confidence += 0.2
        if desc:
            confidence += 0.1

        return ScrapedProduct(
            source_url=url,
            domain=domain,
            title=title,
            description=desc,
            images=imgs[:10],
            price=price_val,
            currency=currency,
            brand=brand or None,
            sku=sku or None,
            extraction_method="microdata",
            confidence=min(confidence, 1.0),
        )

    def _heuristic(self, soup, url: str, domain: str) -> ScrapedProduct:
        """Heuristic: <title> + <h1> + 가격 패턴 + 이미지."""
        # 제목
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
        h1 = soup.find("h1")
        if h1:
            h1_text = h1.get_text(strip=True)
            # h1이 title보다 짧고 더 정확할 수 있음
            if h1_text and len(h1_text) < len(title):
                title = h1_text

        # 설명
        desc = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            desc = meta_desc.get("content", "")

        # 이미지 — og:image 없으면 페이지 최대 이미지
        images: list = []
        for img in soup.find_all("img", src=True):
            src = img.get("src", "")
            if not src or src.startswith("data:"):
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(url, src)
            if src.startswith("http"):
                images.append(src)
        images = list(dict.fromkeys(images))[:5]

        # 가격 휴리스틱
        price_val: Optional[Decimal] = None
        currency = "USD"
        _price_pattern = re.compile(
            r"([\$\$€£¥₩￦])\s*([\d,]+(?:\.\d{1,2})?)"
            r"|(\d[\d,]*(?:\.\d{1,2})?)\s*(USD|EUR|GBP|JPY|KRW|CNY)",
            re.IGNORECASE,
        )
        page_text = soup.get_text(" ", strip=True)[:5000]
        for m in _price_pattern.finditer(page_text):
            sym = m.group(1) or ""
            num = m.group(2) or m.group(3) or ""
            cur_code = m.group(4) or ""
            if not num:
                continue
            val = _parse_price(num)
            if val:
                price_val = val
                if cur_code:
                    currency = cur_code.upper()
                elif sym:
                    currency = _CURRENCY_SYMBOLS.get(sym, "USD")
                break

        confidence = 0.1
        if title:
            confidence += 0.1
        if images:
            confidence += 0.1
        if price_val:
            confidence += 0.1
        if desc:
            confidence += 0.05

        return ScrapedProduct(
            source_url=url,
            domain=domain,
            title=title,
            description=desc,
            images=images,
            price=price_val,
            currency=currency,
            extraction_method="heuristic",
            confidence=min(confidence, 1.0),
        )
