"""오너 11-26 진단 캡처 판정 1 — 아마존 상품 사진·옵션·가격·A+를 **페이지의 데이터**에서 읽는다(img 태그를 긁지 않는다).

표본 행 b6809323(tomtoc, 공유)의 images 14장은 범용 수집기가 페이지의 `<img>`를 다 긁은 결과였다:
`_AC_US40_` 40px 썸네일 6 · 배지 svg 3(`/images/S/sash`) · `images-na` 추천 상품 2 · 쓸 만한 판 1~2. 옵션·SKU·상세 0.
게다가 서버는 HTML을 1MB에서 끊었는데 아마존 상품 화면은 그보다 길다 — 사진 데이터가 뒤에 있으면 아예 못 봤다.

읽는 곳(아마존이 상품 화면에 싣는 것 그대로):
  · 사진: `'colorImages': {'initial': [{hiRes, large, thumb, main, variant}]}` → `hiRes`(없으면 `large`, 없으면 `main`의 가장 큰 판).
          없으면 `#landingImage[data-a-dynamic-image]`의 가장 큰 판 한 장.
  · 버리는 것: svg · `/images/S/`(배지·아이콘) · `images-na`·추천 캐러셀 · 메인 사진 블록 밖 · 같은 사진 ID 중복.
  · 옵션: twister `variationValues`(값) + `dimensionsDisplay`(이름).
  · 가격: `priceAmount`(현재 판매가) → 없으면 가격 블록의 `a-offscreen`.
  · 상세(A+): `#aplus` 안 `aplus-media` 사진.
옵션별 가격은 이 화면에 없다(고른 옵션 하나만 값이 있다) — 지어내지 않는다. 그러면 사전검증의 「수집이 덜 됐어요」(옵션은 있는데 SKU 0)가 말한다.
크기 토큰(`._AC_US40_.`)을 떼서 「원본」을 만들지 않는다 — 실측(AMZIMG2 11-26): 토큰 뗀 썸네일은 400×500·500×500(작은 판),
같은 사진의 `hiRes`는 1070×1428~1500×1500이었다.
"""
from __future__ import annotations

import html as _html
import json
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

_ID_RE = re.compile(r"/images/I/([A-Za-z0-9+\-%]+)\.")
_COLOR_IMAGES_RE = re.compile(r"""['"]colorImages['"]\s*:\s*\{\s*['"]initial['"]\s*:\s*(?=\[|\s*(?:A\.\$|jQuery|\$)\.parseJSON)""")
_DYN_RE = re.compile(r"""<img[^>]*\bid=["']landingImage["'][^>]*>""", re.S)
_DYN_ATTR_RE = re.compile(r"""data-a-dynamic-image=["']([^"']+)["']""")
_VAR_VALUES_RE = re.compile(r'"variationValues"\s*:\s*(?=\{)')
_DIM_DISPLAY_RE = re.compile(r'"dimensionsDisplay"\s*:\s*(?=\[)')
_DIMS_RE = re.compile(r'"dimensions"\s*:\s*(?=\[)')
_PRICE_AMOUNT_RE = re.compile(r'"priceAmount"\s*:\s*([0-9]+(?:\.[0-9]+)?)')
_CURRENCY_RE = re.compile(r'"currencyCode"\s*:\s*"([A-Z]{3})"')
_APLUS_RE = re.compile(r'id=["\']aplus["\'](.*?)(?:id=["\']aplus_feature_div_end["\']|id=["\']productDescription_feature_div["\']|</body>)', re.S)
_APLUS_IMG_RE = re.compile(r'(?:data-src|src)=["\'](https://m\.media-amazon\.com/images/S/aplus-media[^"\']+)["\']')
_OFFSCREEN_RE = re.compile(r'id=["\'](?:corePrice_feature_div|corePriceDisplay_desktop_feature_div|apex_desktop)["\'].{0,4000}?class=["\']a-offscreen["\']>\s*([^<]{1,24})<', re.S)
_BULLET_RE = re.compile(r'id=["\']feature-bullets["\'](.*?)</ul>', re.S)

_DIM_LABEL = {"color_name": "색상", "size_name": "사이즈", "style_name": "스타일", "pattern_name": "패턴",
              "material_type": "소재", "item_package_quantity": "수량", "configuration": "구성"}


def is_amazon_page(html: Optional[str], url: str = "") -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    if ".amazon." in "." + host or host.startswith("amazon."):
        return True
    return bool(html) and ("colorImages" in html or 'id="landingImage"' in html) and "amazon" in html[:20000].lower()


def image_id(url: str) -> str:
    m = _ID_RE.search(str(url or ""))
    return m.group(1) if m else ""


def _ok_image(url: str) -> bool:
    u = str(url or "")
    if not u.startswith("https://") or u.lower().endswith(".svg") or "/images/S/" in u:
        return False
    host = (urlparse(u).hostname or "").lower()
    return host == "m.media-amazon.com" and bool(image_id(u))


def _balanced(text: str, start: int) -> str:
    """`text[start]`의 괄호(`[`·`{`)와 짝인 닫는 괄호까지 — 문자열 안 괄호는 센다에서 뺀다."""
    if start >= len(text) or text[start] not in "[{":
        return ""
    depth, quote, esc = 0, "", False
    for i in range(start, min(len(text), start + 400_000)):
        c = text[i]
        if quote:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                quote = ""
            continue
        if c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


_PARSEJSON_RE = re.compile(r"""\s*(?:A\.\$|jQuery|\$)\.parseJSON\(\s*(['"])""")


def _js_string(text: str, start: int, quote: str) -> str:
    """`text[start:]`부터 따옴표 `quote`로 닫히는 JS 문자열 내용(이스케이프 `\'`·`\"`·`\\` 풀어서)."""
    out, i = [], start
    while i < len(text) and i < start + 400_000:
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            n = text[i + 1]
            out.append(n if n in (quote, "\\", "/") else "\\" + n)
            i += 2
            continue
        if c == quote:
            return "".join(out)
        out.append(c)
        i += 1
    return ""


def _block(rx, html: str):
    """`키: [..]`·`키: {..}` 또는 실측 꼴 `키: A.$.parseJSON('[..]')`(11-26 AMZIMG2 — 아마존 ImageBlockATF)."""
    m = rx.search(html or "")
    if not m:
        return None
    pj = _PARSEJSON_RE.match(html, m.end())
    if pj:
        return _json(_js_string(html, pj.end(), pj.group(1)))
    return _json(_balanced(html, m.end()))


def _json(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        try:
            return json.loads(raw.replace("'", '"'))
        except Exception:
            return None


def _largest(dyn: dict) -> str:
    best, area = "", -1
    for u, wh in (dyn or {}).items():
        try:
            a = int(wh[0]) * int(wh[1])
        except Exception:
            a = 0
        if a > area and _ok_image(u):
            best, area = u, a
    return best


def gallery(html: str) -> Dict:
    """`{images, source}` — 사진 데이터에서 고른 큰 판(ID 중복 없음). 못 찾으면 빈 목록(img 태그로 메우지 않는다)."""
    out: List[str] = []
    seen = set()

    def _add(u):
        if _ok_image(u) and image_id(u) not in seen:
            seen.add(image_id(u))
            out.append(u)

    arr = _block(_COLOR_IMAGES_RE, html)
    if isinstance(arr, list) and arr:
        for e in arr:
            if not isinstance(e, dict):
                continue
            # 실측(AMZIMG2 11-26): hiRes 1070×1428~1500×1500 · main 최대판 679 · large 338~500 — 큰 것부터
            _add(e.get("hiRes") or _largest(e.get("main") or {}) or e.get("large"))
        if out:
            return {"images": out, "source": "colorImages"}
    tag = _DYN_RE.search(html or "")
    attr = _DYN_ATTR_RE.search(tag.group(0)) if tag else None
    if attr:
        dyn = _json(_html.unescape(attr.group(1))) or {}
        _add(_largest(dyn) if isinstance(dyn, dict) else "")
        if out:
            return {"images": out, "source": "dynamic-image"}
    return {"images": [], "source": ""}


def options(html: str) -> List[dict]:
    vv = _block(_VAR_VALUES_RE, html)
    if not isinstance(vv, dict) or not vv:
        return []
    disp, dims = _block(_DIM_DISPLAY_RE, html), _block(_DIMS_RE, html)
    order = [d for d in (dims if isinstance(dims, list) else []) if d in vv] or list(vv.keys())
    out = []
    for i, key in enumerate(order):
        vals = [str(v).strip() for v in (vv.get(key) or []) if str(v).strip()]
        if not vals:
            continue
        name = (disp[i] if isinstance(disp, list) and i < len(disp) and str(disp[i]).strip() else "") or _DIM_LABEL.get(key, key)
        out.append({"name": str(name).strip(), "values": list(dict.fromkeys(vals)), "dim": key})
    return out


_ANY_OFFSCREEN_RE = re.compile(r'class=["\']a-offscreen["\']>\s*([^<]{1,24})<')
_CODE_PREFIX_RE = re.compile(r"^\s*([A-Z]{3})(?=[\s\xa0\d])")


def _currency_of(txt: str) -> str:
    """가격 글자에서 통화 — `KRW107,003`(실측 · 한국 배송지로 본 화면) · `$39.99` · `¥` · `€` · `£`. 모르면 빈칸."""
    t = str(txt or "")
    m = _CODE_PREFIX_RE.match(t)
    if m:
        return m.group(1)
    return "USD" if "$" in t else ("JPY" if ("¥" in t or "￥" in t) else ("EUR" if "€" in t else ("GBP" if "£" in t else "")))


def price(html: str) -> Dict:
    """현재 판매가 + 통화. 통화는 `currencyCode` → 가격 블록 글자(`KRW…`·`$…`) 순 — 지어내지 않는다
    (실측 11-26: 한국 배송지 화면은 `priceAmount` 107002.62에 `currencyCode`가 없고 글자가 `KRW107,003`)."""
    m = _PRICE_AMOUNT_RE.search(html or "")
    mc = _CURRENCY_RE.search(html or "")
    m2 = _OFFSCREEN_RE.search(html or "") or _ANY_OFFSCREEN_RE.search(html or "")
    txt = m2.group(1).strip() if m2 else ""
    cur = (mc.group(1) if mc else "") or _currency_of(txt)
    if m:
        return {"price": m.group(1), "currency": cur, "source": "priceAmount"}
    num = re.sub(r"[^0-9.]", "", txt.replace(",", ""))
    if num:
        return {"price": num, "currency": cur, "source": "a-offscreen"}
    return {"price": "", "currency": cur, "source": ""}


def aplus_images(html: str) -> List[str]:
    m = _APLUS_RE.search(html or "")
    if not m:
        return []
    return [u for u in dict.fromkeys(_APLUS_IMG_RE.findall(m.group(1)))
            if not re.search(r"1x1|pixel|grey-pixel", u) and _aplus_big(u)][:30]


_APLUS_TOKEN_RE = re.compile(r"\.__([A-Z0-9,_]+?)___?\.")


def _aplus_big(url: str) -> bool:
    """A+ 사진 중 비교표 아이콘(`__CR0,0,315,145_PT0_SX315_V1___` · `__AC_SR166,182___` — 실측 11-26)은 상세 본문이 아니다.
    `SX`/`SR` 폭이 500 미만이면 뺀다. 토큰이 없으면 둔다."""
    m = _APLUS_TOKEN_RE.search(str(url or ""))
    if not m:
        return True
    w = re.search(r"(?:SX|SR)(\d{2,4})", m.group(1))
    return (not w) or int(w.group(1)) >= 500


def bullets(html: str) -> List[str]:
    m = _BULLET_RE.search(html or "")
    if not m:
        return []
    items = re.findall(r'<span class=["\']a-list-item["\'][^>]*>(.*?)</span>', m.group(1), re.S)
    out = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.unescape(t))).strip() for t in items]
    return [t for t in out if len(t) > 3][:10]


def parse(html: Optional[str]) -> Dict:
    """한 번에 — `{images, image_source, options, price, currency, price_source, detail_images, bullets}`."""
    h = html or ""
    g, p = gallery(h), price(h)
    return {"images": g["images"], "image_source": g["source"], "options": options(h),
            "price": p["price"], "currency": p["currency"], "price_source": p["source"],
            "detail_images": aplus_images(h), "bullets": bullets(h)}


_SIZE_TOKEN_RE = re.compile(r"\._([A-Z0-9,_]+)_\.")


def usable_photo(url: str) -> bool:
    """주소만 보고(네트워크 0) — 등록에 쓸 만한 아마존 사진인가. svg·배지(`/images/S/`)·추천(`images-na`)·
    긴 변 500px 미만을 뜻하는 크기 토큰(`_AC_US40_`·`_SS100_`·`_UL116_SR116`·`_SY300_SX300_`)이면 아니다.
    토큰이 없거나 큰 판(`_SX522_`·`_SL1500_`)이면 쓸 만하다. 아마존 사진이 아니면 판정하지 않는다(True)."""
    u = str(url or "")
    host = (urlparse(u).hostname or "").lower()
    if "amazon" not in host:
        return True
    if u.lower().endswith(".svg") or "/images/S/" in u or host.startswith("images-na"):
        return False
    m = _SIZE_TOKEN_RE.search(u)
    if not m:
        return True
    nums = [int(n) for n in re.findall(r"(\d{2,4})", m.group(1))]
    return (not nums) or max(nums) >= 500            # `._AC_.`처럼 숫자 없는 토큰은 원본 판


# ── 오너 11-26 오후 ① — 옵션별 가격(자식 ASIN) ────────────────────────────────
#   상품 화면엔 「고른 옵션」 가격만 있다. 옵션 조합 → 자식 ASIN 표(`dimensionValuesDisplayData` = {ASIN: [값…]},
#   값 순서는 `dimensions`)를 읽고, 자식 ASIN 화면을 하나씩 열어 그 가격을 읽는다. 못 읽은 조합은 사유를 남기고 SKU로 만들지 않는다.
_DVD_RE = re.compile(r'"dimensionValuesDisplayData"\s*:\s*(?=\{)')
_CUR_ASIN_RE = re.compile(r'"(?:currentAsin|parentAsin_unused|mediaAsin)"\s*:\s*"([A-Z0-9]{10})"')
_ASIN_IN_URL_RE = re.compile(r"/dp/([A-Z0-9]{10})")
MAX_CHILDREN = 40


def variants(html: str) -> Dict:
    """`{dims, values_by_asin, current}` — dims = 옵션 축 키 순서(`dimensions`), values_by_asin = {ASIN: [값…]}(dims 순서)."""
    dvd = _block(_DVD_RE, html)
    dims = _block(_DIMS_RE, html)
    cur = _CUR_ASIN_RE.search(html or "")
    out = {"dims": [d for d in (dims if isinstance(dims, list) else [])],
           "values_by_asin": {}, "current": cur.group(1) if cur else ""}
    if isinstance(dvd, dict):
        for asin, vals in dvd.items():
            if re.fullmatch(r"[A-Z0-9]{10}", str(asin)) and isinstance(vals, list):
                out["values_by_asin"][str(asin)] = [str(v).strip() for v in vals]
    return out


def child_skus(variant_map: Dict, fetch_html, *, gap: float = 1.2, max_children: int = MAX_CHILDREN,
               sleep=None) -> Dict:
    """자식 ASIN마다 화면을 열어 가격을 읽는다 — `{skus:[{spec, price, currency, asin}], missing:[{spec, asin, why}], read, capped}`.
    `fetch_html(url) -> str|None` · 간격 `gap`초 · 최대 `max_children`개(넘는 건 「상한」으로 남긴다) · 가격은 지어내지 않는다."""
    import time as _t
    sleep = sleep or _t.sleep
    vba = variant_map.get("values_by_asin") or {}
    skus, missing, read = [], [], 0
    for i, (asin, spec) in enumerate(vba.items()):
        if i >= max_children:
            missing.append({"spec": spec, "asin": asin, "why": f"상한 {max_children}개 넘음 — 읽지 않음"})
            continue
        if i:
            sleep(gap)
        h = fetch_html(f"https://www.amazon.com/dp/{asin}?th=1&psc=1")
        read += 1
        if not h:
            missing.append({"spec": spec, "asin": asin, "why": "화면을 못 읽음(막힘·빈 화면)"})
            continue
        p = price(h)
        if not p["price"] or not p["currency"]:
            why = "현재 구매 불가(가격 없음)" if re.search(r"Currently unavailable|outOfStock", h) else ("통화 모름" if p["price"] else "가격 없음")
            missing.append({"spec": spec, "asin": asin, "why": why})
            continue
        skus.append({"spec": spec, "price": p["price"], "currency": p["currency"], "asin": asin, "source": "amazon_child"})
    return {"skus": skus, "missing": missing, "read": read, "capped": max(0, len(vba) - max_children)}
