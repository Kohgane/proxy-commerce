"""src/collectors/state_json.py — v49 STEP4: 수신 HTML의 초기 상태 JSON 파싱(서버 단일 파서).

근원: 북마클릿은 렌더된 페이지 outerHTML(최대 90만자)을 이미 서버로 보낸다. 그 안에 Temu 등이
초기 상태를 인라인 <script>로 심어둔다(window.rawData={...} / <script type=application/json>). 그런데
서버는 이를 파싱하지 않고 DOM/OG만 봐서 가격·갤러리·옵션·리뷰를 못 얻었다.

수리: 확장(kgp-extractor.js)의 초기상태 파서를 **파이썬으로 동형 이식** — HTML 텍스트에서 상태 JSON을
꺼내(균형 매칭) 키 이름 휴리스틱으로 sku 가격(센트 환산)·갤러리·옵션·상세 이미지·평점·리뷰를 매핑.
사이트 스키마 하드코딩 없음(추측 금지). 추가 네트워크(API) 호출 없음. DOM 셀렉터는 상위 호출부의 폴백.
확장·북마클릿 모두 이 파서를 경유해 통일(클라별 파서 중복 금지).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

_STATE_KEYS = ["__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "__INIT_DATA__", "__STORE__",
               "rawData", "__PRELOADED_STATE__", "__APOLLO_STATE__", "pageData"]

_IMG_KEY = re.compile(r"(image|img|pic|photo|thumb|gallery|carousel|album)", re.I)
_DET_KEY = re.compile(r"(detail|desc|content)", re.I)
_SKU_KEY = re.compile(r"(sku|variant|goodsspec|specsku|skulist|productlist)", re.I)
_SPEC_KEY = re.compile(r"(spec|attr|prop|option|variation)", re.I)
_PRICE_KEY = re.compile(r"(price|amount|sale|deal)", re.I)
_PRICE_BAD = re.compile(r"(count|qty|num|origin|list|regular|market|before|min|max|unit|discount|off|save)", re.I)
_RATE_KEY = re.compile(r"(avgrating|averagerating|ratingvalue|goodsscore|starscore|score|rating)$", re.I)
_CNT_KEY = re.compile(r"(reviewcount|reviewnum|commentcount|reviewtotal|totalreview|ratingcount)", re.I)
_NONPROD_IMG = re.compile(
    r"(logo|sprite|icon|favicon|avatar|placeholder|loading|blank|pixel|spinner|banner|badge|"
    r"button|arrow|chevron|caret|rating|star_|flags?|emoji|watermark|qr[-_]?code|coupon|nav_|"
    r"1x1|transparent\.|spacer)", re.I)
_TITLE_KEY = re.compile(r"(^title$|goodsname|productname|itemname|^name$)", re.I)
_DESC_KEY = re.compile(r"(description|detailtext|goodsdesc|productdesc)", re.I)
_CENTS = {"USD", "EUR", "GBP", "CNY", "AUD", "CAD"}
_REVIEW_MAX = 10
_MAX_NODES = 40000


def _slice_balanced(s: str, frm: int) -> Optional[str]:
    """s[frm]의 { 또는 [ 부터 문자열-인지 균형 매칭으로 JSON 조각을 잘라낸다."""
    if frm >= len(s):
        return None
    opn = s[frm]
    if opn not in "{[":
        return None
    depth = 0
    in_str = False
    esc = False
    q = ""
    i = frm
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == q:
                in_str = False
        else:
            if c in "\"'":
                in_str = True
                q = c
            elif c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    return s[frm:i + 1]
        i += 1
    return None


def extract_state_json(html: str) -> List[Any]:
    """HTML 텍스트에서 초기 상태 JSON 객체들을 추출한다(인라인 <script> 할당 + application/json)."""
    out: List[Any] = []
    if not html:
        return out
    # (1) <script type="application/json"> 블록(예: __NEXT_DATA__)
    for m in re.finditer(r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            o = json.loads(m.group(1).strip())
            if isinstance(o, (dict, list)):
                out.append(o)
        except Exception:
            pass
    # (2) 인라인 <script> 텍스트의 상태 할당(window.rawData = {...} 등)
    for sm in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I):
        t = sm.group(1)
        if len(t) < 20 or len(t) > 6_000_000:
            continue
        for key in _STATE_KEYS:
            pos = 0
            guard = 0
            while guard < 5:
                guard += 1
                idx = t.find(key, pos)
                if idx < 0:
                    break
                pos = idx + len(key)
                eq = t.find("=", idx)
                if eq < 0 or eq - idx > len(key) + 8:
                    continue
                seg = t[eq:eq + 300]
                mb = re.search(r"[{\[]", seg)
                if not mb:
                    continue
                raw = _slice_balanced(t, eq + mb.start())
                if raw:
                    try:
                        o = json.loads(raw)
                        if isinstance(o, (dict, list)):
                            out.append(o)
                    except Exception:
                        pass
    return out


def _is_product_img(s: Any) -> bool:
    return bool(s) and isinstance(s, str) and not s.startswith("data:") and not _NONPROD_IMG.search(s)


def _hi_res(u: str) -> str:
    try:
        u = re.sub(r"\._(AC_)?S[XYLS]\d+_", "", u)
        u = re.sub(r"(\?|&)(imageView2?|thumb|w|width|h|height|size|quality)=[^&]*", "", u, flags=re.I)
        u = re.sub(r"[?&]$", "", u)
        u = re.sub(r"\.{2,}(jpg|jpeg|png|webp|gif)", r".\1", u, flags=re.I)
    except Exception:
        pass
    return u


def _price_from_num(n: Any, cur: str) -> str:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return ""
    if not (v > 0):
        return ""
    if cur in _CENTS and v == int(v) and v >= 1000:
        return str(v / 100)
    return str(int(v)) if v == int(v) else str(v)


_PRICE_STR_RE = re.compile(
    r"([\$＄€£¥￥₩￦])\s*([\d,]+(?:\.\d{1,2})?)"
    r"|([\d,]+(?:\.\d{1,2})?)\s*(USD|EUR|GBP|JPY|KRW|CNY|원|엔|위안|元)", re.I)
_SYM = {"$": "USD", "＄": "USD", "€": "EUR", "£": "GBP", "¥": "JPY",
        "￥": "JPY", "₩": "KRW", "￦": "KRW"}
_CODEMAP = {"USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY", "KRW": "KRW", "CNY": "CNY",
            "원": "KRW", "엔": "JPY", "위안": "CNY", "元": "CNY"}


def _parse_price_str(raw: Any) -> Optional[Dict[str, str]]:
    m = _PRICE_STR_RE.search(str(raw or ""))
    if not m:
        return None
    sym = m.group(1) or ""
    num = (m.group(2) or m.group(3) or "").replace(",", "")
    code = m.group(4) or ""
    if not num:
        return None
    cur = (_CODEMAP.get(code) or _CODEMAP.get(code.upper()) or code.upper()) if code else _SYM.get(sym, "")
    return {"price": num, "currency": cur}


def _walk(root: Any, visit, max_nodes: int = _MAX_NODES) -> None:
    stack = [root]
    n = 0
    seen = set()
    while stack and n < max_nodes:
        cur = stack.pop()
        n += 1
        if not isinstance(cur, (dict, list)):
            continue
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)
        if isinstance(cur, dict):
            visit(cur)
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        else:
            for v in cur:
                if isinstance(v, (dict, list)):
                    stack.append(v)


def map_product(states: List[Any]) -> Dict[str, Any]:
    """상태 JSON들에서 상품 필드를 키 이름 휴리스틱으로 매핑(스키마 무관)."""
    res: Dict[str, Any] = {
        "title": "", "price": "", "currency": "", "images": [], "detail_images": [],
        "options": [], "skus": [], "reviews": [], "rating": "", "review_count": "", "description": "",
    }
    img_seen: set = set()
    det_seen: set = set()

    def push_imgs(arr, dest, seen):
        for u in arr:
            if len(dest) >= 40:
                break
            if isinstance(u, dict):
                u = u.get("url") or u.get("src") or u.get("imageUrl") or u.get("thumbUrl") or u.get("image") or ""
            if isinstance(u, str) and re.match(r"^https?://", u) and _is_product_img(u):
                hu = _hi_res(u)
                if hu not in seen:
                    seen.add(hu)
                    dest.append(hu)

    def sku_price(o: dict) -> Optional[Dict[str, str]]:
        for k, pv in o.items():
            if _PRICE_KEY.search(k) and not _PRICE_BAD.search(k):
                if isinstance(pv, str):
                    pp = _parse_price_str(pv)
                    if pp:
                        return pp
                elif isinstance(pv, (int, float)):
                    cur = str(o.get("currency") or o.get("currencyCode") or o.get("priceCurrency") or res["currency"] or "").upper()
                    val = _price_from_num(pv, cur)
                    if val:
                        return {"price": val, "currency": cur}
        return None

    sku_set = {"done": False}

    def visit(node: dict):
        for key, v in list(node.items()):
            try:
                kl = str(key).lower()
                if isinstance(v, list) and _IMG_KEY.search(kl):
                    push_imgs(v, res["detail_images"] if _DET_KEY.search(kl) else res["images"],
                              det_seen if _DET_KEY.search(kl) else img_seen)
                elif isinstance(v, str) and re.match(r"^https?://", v) and _IMG_KEY.search(kl) and _is_product_img(v):
                    dest, seen = (res["detail_images"], det_seen) if _DET_KEY.search(kl) else (res["images"], img_seen)
                    hu = _hi_res(v)
                    if hu not in seen:
                        seen.add(hu)
                        dest.append(hu)
                elif isinstance(v, list) and _SKU_KEY.search(kl) and v and isinstance(v[0], dict):
                    for so in v[:200]:
                        if not isinstance(so, dict):
                            continue
                        sp = sku_price(so)
                        spec_vals = []
                        for sk, sv in so.items():
                            if _SPEC_KEY.search(sk):
                                if isinstance(sv, list):
                                    spec_vals += [str(x) for x in sv]
                                elif isinstance(sv, str):
                                    spec_vals.append(sv)
                        res["skus"].append({"spec": spec_vals, "price": sp["price"] if sp else "", "currency": sp["currency"] if sp else ""})
                        if sp and not sku_set["done"]:
                            res["price"] = sp["price"]
                            res["currency"] = sp["currency"]
                            sku_set["done"] = True
                elif _RATE_KEY.search(kl) and not res["rating"] and isinstance(v, (str, int, float)):
                    try:
                        rn = float(v)
                        if 0 < rn <= 5:
                            res["rating"] = str(v)
                    except (TypeError, ValueError):
                        pass
                elif _CNT_KEY.search(kl) and not res["review_count"] and isinstance(v, (str, int, float)):
                    res["review_count"] = str(v)
                elif not res["title"] and _TITLE_KEY.search(kl) and isinstance(v, str) and len(v) > 2:
                    res["title"] = v[:300]
                elif not res["description"] and _DESC_KEY.search(kl) and isinstance(v, str) and len(v) > 20:
                    res["description"] = v[:4000]
            except Exception:
                pass
        # 가격: sku 미확보 시 표시 문자열(통화기호 포함) 우선
        if not res["price"]:
            for k2, pv2 in node.items():
                try:
                    if _PRICE_KEY.search(k2) and not _PRICE_BAD.search(k2) and isinstance(pv2, str):
                        pp2 = _parse_price_str(pv2)
                        if pp2 and pp2["currency"]:
                            res["price"] = pp2["price"]
                            res["currency"] = pp2["currency"]
                            break
                except Exception:
                    pass
        # 리뷰 텍스트(초기 JSON에 실린 것만)
        if len(res["reviews"]) < _REVIEW_MAX:
            try:
                body = node.get("reviewBody") or node.get("comment") or node.get("content") or node.get("text")
                has_rating = node.get("rating") is not None or node.get("star") is not None or node.get("score") is not None
                if isinstance(body, str) and len(body) >= 2 and (has_rating or node.get("reviewId") or node.get("commentId") or node.get("reviewer")):
                    res["reviews"].append({
                        "author": node.get("author") or node.get("userName") or node.get("nickname") or node.get("reviewer") or "",
                        "rating": node.get("rating") or node.get("star") or node.get("score") or "",
                        "text": str(body)[:500],
                    })
            except Exception:
                pass

    for st in states:
        _walk(st, visit)

    # 옵션: sku 스펙 값 축 이름 없이 합쳐(중복 제거). 2개 이상일 때만.
    if res["skus"]:
        ovals = []
        oseen = set()
        for sk in res["skus"]:
            for val in sk.get("spec", []):
                if val and val not in oseen:
                    oseen.add(val)
                    ovals.append(val)
        if len(ovals) >= 2:
            res["options"].append({"name": "옵션", "values": ovals[:100]})
    return res


_TEMU_HOST = re.compile(r"(^|\.)temu\.com$", re.I)


def parse_state_from_html(html: str, url: str = "") -> Dict[str, Any]:
    """수신 HTML → 초기 상태 JSON 파싱 → 상품 필드 매핑. 상태 JSON 없으면 빈 결과(폴백은 호출부).

    v51: **테무는 rawData/초기상태 전역이 구조적으로 없음(오너 확정)** → 테무 URL은 이 파서를 건너뛴다
    (PRERENDER_CONFIG 등 비-상품 인라인 JSON을 상품으로 오파싱하지 않도록). 테무는 확장 Tier1(API 캡처)로만.
    """
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "") if url else ""
        if host and _TEMU_HOST.search(host):
            return {}
    except Exception:
        pass
    states = extract_state_json(html)
    if not states:
        return {}
    return map_product(states)
