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

_USER_AGENT = os.getenv(
    "SCRAPER_USER_AGENT", "KohganePercentiii/1.0 (+https://kohganepercentiii.com)"
)
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


# 상품 이미지가 아닌 것으로 보이는 URL 패턴(로고/아이콘/배너/플래그/추적픽셀/문서아이콘 등)
# v11 P0: 무관 이미지(태극기 flags·openingemail·supplier-public-tag·*.slim.png·pdf/doc·화살표 등) 제외.
_NON_PRODUCT_IMG_RE = re.compile(
    r"(logo|sprite|icon|favicon|avatar|placeholder|loading|blank|pixel|spinner|"
    r"banner|badge|button|arrow|chevron|caret|star_|rating|flags?|emoji|"
    r"openingemail|supplier-public-tag|public-tag|\.slim\.|tracking|beacon|"
    r"watermark|qr[-_]?code|coupon|thumb_nav|nav_|/pdf|pdf[-_]|\.pdf|"
    r"\.doc|doc[-_]icon|/doc/|/document/|1x1|transparent\.|spacer)",
    re.IGNORECASE,
)


def is_product_image(url: str) -> bool:
    """상품 이미지로 보이는 URL인가? (data:/빈값/블랙리스트 패턴 제외)"""
    s = (url or "").strip()
    if not s or s.startswith("data:"):
        return False
    if not s.startswith("http") and not s.startswith("//"):
        return False
    return not _NON_PRODUCT_IMG_RE.search(s)


def filter_product_images(urls) -> list:
    """이미지 URL 목록에서 무관 이미지를 제거하고 순서 유지·중복 제거(첫 번째=대표)."""
    out, seen = [], set()
    for u in (urls or []):
        s = str(u or "").strip()
        if not s or s in seen or not is_product_image(s):
            continue
        seen.add(s)
        out.append(s)
    return out


# v16 P0: og:description 등에 들어오는 '사이트 공통 마케팅 필러'(상품 설명 아님) 탐지.
# Temu/알리/쇼핑몰 공통 카피를 실제 상품 설명으로 저장/번역하지 않기 위함. 보수적(알려진 카피만).
_FILLER_DESC_RE = re.compile(
    r"("
    r"절약을\s*시작|쇼핑하여\s*절약|에서\s*쇼핑하여|최저가로\s*쇼핑|지금\s*쇼핑하세요|"
    r"여기를\s*눌러|링크를\s*확인하세요|"
    r"smarter\s+shopping,?\s*better\s+living|"
    r"start\s+saving|save\s+big\b|shop\b.{0,30}\band\s+save\b|"
    r"free\s+shipping\s+on\s+(all\s+)?orders|"
    r"latest\s+.{0,24}(styles|trends|fashion).{0,24}(best|low(est)?)\s+price|"
    r"discover\s+(quality|amazing)\s+products\s+at"
    r")",
    re.IGNORECASE,
)


def is_filler_description(text: str, url: str = "") -> bool:
    """상품 설명이 아니라 사이트 공통 마케팅 필러인가? (알려진 카피만 — 보수적, 오탐 최소화)"""
    t = (text or "").strip()
    if not t:
        return False
    return bool(_FILLER_DESC_RE.search(t))


# v39 D: 치환 실패 플레이스홀더 토큰 — 소스 사이트가 미치환한 템플릿 변수가 제목/상세에 그대로 노출되는 것 방지.
#   예: "{REGION_NAME - Temu Republic of Korea}", "{site_name}", "{{title}}", "%PRODUCT_NAME%".
#   보수적: CAPS 식별자(REGION_NAME 등) 또는 명백한 템플릿 토큰만 제거 — 정상 텍스트 오탐 최소.
_PLACEHOLDER_RE = re.compile(
    r"\{\{[^{}]*\}\}"                       # {{ ... }} 이중 중괄호 템플릿
    r"|\{[^{}]*[A-Z][A-Z0-9_]{2,}[^{}]*\}"  # { ... CAPS_TOKEN ... } (REGION_NAME 등 포함)
    r"|%[A-Z][A-Z0-9_]{2,}%"               # %PRODUCT_NAME% 류
    r"|\$\{[^{}]*\}"                        # ${...}
)


def strip_placeholder_tokens(text: str) -> str:
    """사용자 노출 제목/상세에서 치환 실패 플레이스홀더 토큰을 제거(가짜값 대체 금지 — 그냥 빼고 공백 정리)."""
    t = text or ""
    if not t or ("{" not in t and "%" not in t):
        return t
    t = _PLACEHOLDER_RE.sub(" ", t)
    # 토큰 제거 후 남은 군더더기 정리: 연속 공백·고립 구분자(- · | ,) 다듬기.
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"^[\s\-·|,]+|[\s\-·|,]+$", "", t)
    return t.strip()


def extract_reviews(html: str, limit: int = 20) -> list:
    """페이지 HTML에서 해당 상품 리뷰(별점·본문·작성자)를 best-effort 추출. JSON-LD Product.review 우선.

    없으면 빈 리스트(가짜 리뷰 생성 금지). 추천/연관 상품 리뷰 혼입을 줄이기 위해 JSON-LD를 우선한다.
    """
    reviews: list = []
    if not html:
        return reviews
    try:
        import json as _json
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                obj = _json.loads(sc.string or sc.get_text() or "")
            except Exception:
                continue
            nodes = obj if isinstance(obj, list) else [obj]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                revs = node.get("review") or node.get("reviews")
                if isinstance(revs, dict):
                    revs = [revs]
                if not isinstance(revs, list):
                    continue
                for r in revs:
                    if not isinstance(r, dict):
                        continue
                    body = str(r.get("reviewBody") or r.get("description") or "").strip()
                    rating = None
                    rr = r.get("reviewRating") or {}
                    if isinstance(rr, dict):
                        try:
                            rating = float(rr.get("ratingValue"))
                        except (TypeError, ValueError):
                            rating = None
                    author = r.get("author")
                    if isinstance(author, dict):
                        author = author.get("name", "")
                    if body or rating is not None:
                        reviews.append({"body": body[:500], "rating": rating,
                                        "author": str(author or "")[:60]})
                    if len(reviews) >= limit:
                        return reviews
    except Exception:
        return reviews
    return reviews


# v16 P0: '현재 상품(PDD)'이 아닌 영역 — 추천/연관/함께 본/스폰서/랭킹/최근 본/푸터 등.
# 이런 컨테이너 안의 이미지·가격은 '다른 상품' 것이므로 수집에서 제외해 혼입을 막는다(class/id 의미 기반).
_NON_PRODUCT_REGION_RE = re.compile(
    r"(recommend|related|similar|also[-_ ]?(bought|viewed|like)|you[-_ ]?may|"
    r"frequently[-_ ]?bought|sponsored|advert|promotion|ranking|best[-_ ]?seller|"
    r"recently[-_ ]?viewed|history|carousel|slider|cross[-_ ]?sell|up[-_ ]?sell|"
    r"comparison|footer|site[-_ ]?footer|navbar|header[-_ ]?nav|breadcrumb|"
    r"more[-_ ]?to[-_ ]?explore|other[-_ ]?products|popular|trending|"
    # v33: 리뷰/문의/댓글 영역의 썸네일도 '상품 이미지' 아님 → 제외
    r"review|comment|reply|\bqna\b|q[-_ ]?and[-_ ]?a|feedback|testimonial)",
    re.IGNORECASE,
)

# v33: 상품 상세(PDP) 메인 컨테이너 후보 — 여기로 이미지 수집 스코프를 좁혀 '엉뚱한' 이미지 차단.
_PRODUCT_SCOPE_SELECTORS = (
    '[itemtype*="Product"]', '[itemtype*="product"]',
    '#productDetail', '#product-detail', '#productInfo', '#goods_detail',
    '.product-detail', '.product-info', '.product-gallery', '.product-images',
    '.goods-detail', '.goodsDetail', '.pdp', '.detail-gallery',
    '[class*="product-detail"]', '[class*="productDetail"]', '[class*="goodsView"]',
)


def _find_product_scope(soup):
    """상품 상세 메인 컨테이너를 찾으면 그걸 반환(이미지 수집 스코프 한정), 못 찾으면 soup 전체.

    보수적: 컨테이너가 비-상품 영역이 아니고 이미지를 2장 이상 가질 때만 스코프로 채택
    (recall 손실 방지 — 명확할 때만 좁힌다).
    """
    for sel in _PRODUCT_SCOPE_SELECTORS:
        try:
            el = soup.select_one(sel)
        except Exception:
            el = None
        if el is None:
            continue
        try:
            if _in_non_product_region(el, max_depth=4):
                continue
            if len(el.find_all("img")) >= 2:
                return el
        except Exception:
            continue
    return soup


def _in_non_product_region(node, max_depth: int = 8) -> bool:
    """노드의 조상 중 추천/연관/푸터 등 '다른 상품' 영역이 있으면 True (최대 max_depth 단계)."""
    cur = getattr(node, "parent", None)
    depth = 0
    while cur is not None and depth < max_depth:
        try:
            tokens = " ".join(
                (cur.get("class") or []) + [cur.get("id") or "", cur.get("data-section") or ""]
            )
        except Exception:
            tokens = ""
        if tokens and _NON_PRODUCT_REGION_RE.search(tokens):
            return True
        cur = getattr(cur, "parent", None)
        depth += 1
    return False


def _collect_dom_images(soup, base_url: str) -> list:
    """페이지 DOM에서 상품 이미지를 최대한 수집한다.

    - src + lazy-load 속성(data-src/data-original/data-lazy/data-srcset) + srcset(최대 해상도)
    - data: URI, 로고/아이콘/배너/플레이스홀더/플래그/추적픽셀/문서 패턴 제외
    - width/height 속성이 명시돼 있고 작으면(아이콘/픽셀) 제외
    - v16: 추천/연관/함께 본/스폰서/푸터 등 '다른 상품' 영역의 이미지는 제외(PDD 스코프, 혼입 방지)
    - 상대경로 절대화, 순서 유지 중복 제거
    """
    out: list = []
    seen = set()
    scope = _find_product_scope(soup)   # v33: PDP 컨테이너로 스코프 한정(엉뚱 이미지 차단)

    def _abs(s: str) -> str:
        s = (s or "").strip()
        if not s or s.startswith("data:"):
            return ""
        if s.startswith("//"):
            s = "https:" + s
        elif s.startswith("/"):
            s = urljoin(base_url, s)
        return s if s.startswith("http") else ""

    def _from_srcset(val: str) -> str:
        # "url1 320w, url2 800w" → 가장 큰 후보(마지막) URL
        best = ""
        for part in (val or "").split(","):
            cand = part.strip().split(" ")[0].strip()
            if cand:
                best = cand
        return best

    def _too_small(img) -> bool:
        # width/height 속성이 명시돼 있고 둘 중 하나가 작으면 아이콘/픽셀로 보고 제외.
        for attr in ("width", "height"):
            v = (img.get(attr) or "").strip().replace("px", "")
            try:
                if v and float(v) < 100:
                    return True
            except (TypeError, ValueError):
                pass
        return False

    for img in scope.find_all("img"):
        cand = ""
        for attr in ("src", "data-src", "data-original", "data-lazy",
                     "data-lazy-src", "data-image", "data-zoom-image"):
            v = img.get(attr)
            if v:
                cand = v
                break
        if not cand:
            ss = img.get("srcset") or img.get("data-srcset")
            if ss:
                cand = _from_srcset(ss)
        url = _abs(cand)
        if not url or url in seen:
            continue
        if _NON_PRODUCT_IMG_RE.search(url):
            continue
        if _too_small(img):
            continue
        if _in_non_product_region(img):    # v16: 추천/연관/푸터 영역의 다른 상품 이미지 제외
            continue
        seen.add(url)
        out.append(url)

    # <source srcset> (picture 요소) 도 수집 — 동일 PDP 스코프
    for src in scope.find_all("source"):
        ss = src.get("srcset") or src.get("data-srcset")
        url = _abs(_from_srcset(ss)) if ss else ""
        if url and url not in seen and not _NON_PRODUCT_IMG_RE.search(url):
            seen.add(url)
            out.append(url)

    return out


# 옵션 그룹 라벨로 인정할 키워드(한/영) — 색상·사이즈·수량·규격·스타일·변형 등.
_OPTION_LABEL_RE = re.compile(
    r"(색상|컬러|색깔|사이즈|크기|치수|규격|용량|수량|개수|스타일|종류|타입|모델|구성|"
    r"옵션|선택|color|colour|size|quantity|qty|variant|variation|style|type|model|spec)",
    re.IGNORECASE,
)
# 옵션 값으로 보기 어려운 잡텍스트(가격/안내문 등) — 너무 길거나 가격 문자열은 제외.
_OPTION_VALUE_BAD_RE = re.compile(r"(원|₩|\$|¥|€|£|장바구니|구매|cart|add to|배송|리뷰|review)", re.IGNORECASE)


def _collect_dom_options(soup) -> list:
    """렌더된 DOM에서 옵션(색상/사이즈/수량 등)을 보수적으로 수집.

    1) <select> 드롭다운 → {name, values}(placeholder 제외).
    2) 라벨 텍스트가 옵션 키워드인 그룹의 클릭 가능 자식(버튼/스와치/li/img[alt]) 값.
    확신 없으면 비움(거짓 데이터 금지). 값은 짧은 텍스트만, 캡 적용.
    """
    options: list = []
    seen_names = set()

    def _clean(v: str) -> str:
        return re.sub(r"\s+", " ", (v or "")).strip()

    def _add(name: str, values: list) -> None:
        name = _clean(name)[:40] or "옵션"
        vals, seenv = [], set()
        for v in values:
            cv = _clean(v)
            if not cv or len(cv) > 40 or _OPTION_VALUE_BAD_RE.search(cv):
                continue
            if cv in seenv:
                continue
            seenv.add(cv)
            vals.append(cv)
            if len(vals) >= 40:
                break
        key = name.lower()
        if len(vals) >= 2 and key not in seen_names:   # 값이 2개 이상일 때만 옵션으로 인정
            seen_names.add(key)
            options.append({"name": name, "values": vals})

    # 1) <select>
    try:
        for sel in soup.find_all("select"):
            opts = [o.get_text() for o in sel.find_all("option")
                    if (o.get_text() or "").strip() and not o.get("disabled")]
            # placeholder("선택하세요" 류) 첫 항목 제거 추정
            if opts and re.search(r"(선택|choose|select|please)", opts[0], re.IGNORECASE):
                opts = opts[1:]
            name = sel.get("aria-label") or sel.get("name") or sel.get("id") or "옵션"
            _add(name, opts)
    except Exception:
        pass

    # 2) 라벨된 스와치 그룹
    try:
        for lab in soup.find_all(["label", "h2", "h3", "h4", "span", "div", "dt"]):
            txt = _clean(lab.get_text())
            if not txt or len(txt) > 24 or not _OPTION_LABEL_RE.search(txt):
                continue
            # 라벨 다음 형제/부모 내에서 클릭 가능 후보 텍스트 수집
            group = lab.find_next_sibling() or lab.parent
            if not group:
                continue
            cands = group.find_all(["button", "li", "a"], limit=60)
            values = []
            for c in cands:
                v = _clean(c.get_text()) or _clean(c.get("aria-label") or "")
                if not v:
                    img = c.find("img")
                    if img:
                        v = _clean(img.get("alt") or "")
                if v:
                    values.append(v)
            if values:
                _add(txt, values)
    except Exception:
        pass

    return options[:8]   # 옵션 그룹 과다 방지


class UniversalScraper:
    """범용 수집기 — 도메인 불문 상품 메타 추출."""

    name = "universal"

    def fetch(self, url: str) -> ScrapedProduct:
        """URL에서 상품 정보 수집. ADAPTER_DRY_RUN=1이면 빈 결과 반환."""
        html = _fetch_html(url)
        return self.parse_html(html, url)

    def parse_html(self, html: Optional[str], url: str) -> ScrapedProduct:
        """제공된 HTML에서 상품 정보 파싱 (네트워크 fetch 없음).

        크롬확장이 사용자 브라우저의 페이지 HTML을 보내면, 서버가 직접 fetch할 수 없는
        봇 차단(403) 사이트도 동일한 JSON-LD/OG/Microdata/Heuristic 파이프라인으로 수집한다.
        """
        domain = _extract_domain(url)
        empty = ScrapedProduct(
            source_url=url,
            domain=domain,
            title="",
            description="",
            extraction_method="heuristic",
            confidence=0.0,
        )

        if not html:
            return empty

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            logger.warning("beautifulsoup4 미설치 — 범용 수집기 제한 모드")
            return empty

        # 1~4: JSON-LD → OG → Microdata → Heuristic (순서대로 첫 성공 사용)
        result = (
            self._parse_jsonld(soup, url, domain)
            or self._parse_opengraph(soup, url, domain)
            or self._parse_microdata(soup, url, domain)
            or self._heuristic(soup, url, domain)
        )

        # v11 P0 후처리: 옵션이 비었으면 렌더된 DOM에서 보수적으로 보강(색상/사이즈/수량 등),
        #               이미지는 무관 패턴을 한 번 더 필터(첫 번째=대표 유지).
        if result is not None:
            try:
                if not getattr(result, "options", None):
                    result.options = _collect_dom_options(soup)
            except Exception:
                pass
            try:
                if getattr(result, "images", None):
                    result.images = filter_product_images(result.images)
            except Exception:
                pass
        return result

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
                        images=list(dict.fromkeys(list(images) + _collect_dom_images(soup, url)))[:40],
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
                # v16 P0: 사이트 공통 마케팅 필러는 상품 설명으로 저장하지 않는다(정직).
                if not is_filler_description(content):
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
            images=list(dict.fromkeys(images + _collect_dom_images(soup, url)))[:40],
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

        # 설명 — 사이트 공통 마케팅 필러는 제외(정직, v16 P0)
        desc = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            _d = meta_desc.get("content", "")
            if not is_filler_description(_d):
                desc = _d

        # 이미지 — og:image 없으면 페이지의 상품 이미지를 최대한 수집
        # (src + lazy-load 속성 + srcset 최대해상도, 로고/배너/아이콘 제외)
        images = _collect_dom_images(soup, url)[:40]

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
