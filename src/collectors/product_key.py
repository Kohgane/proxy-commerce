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
    # F39: **`tbshare:` 키는 SKU가 아니다.** 앱 공유 단축 링크의 키는 `tbshare:<토큰>[:<tk>]`인데,
    #   `tk`가 붙으면 콜론이 둘이라 아래 규칙을 통과해 **`tk`가 SKU로 나갔다**(실측:
    #   `e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt` → `'nyXpT7VA7lt'`).
    #   `tk`는 **공유할 때마다 바뀌는 토큰**이고 상품번호가 아니다 — 마켓에 그걸 보내면
    #   같은 상품이 공유마다 다른 SKU로 등록된다. **빈값보다 나쁘다.**
    if key.startswith("tbshare:"):
        return ""
    # 도메인 규칙이 잡힌 키만 채택(`host:kind:id` 형태). 폴백 키(host+path)는 ':' 규칙이 없다.
    if key.count(":") >= 2:
        ident = key.rsplit(":", 1)[-1]
        if is_valid_vendor_sku(ident):
            return ident
    return ""


# 호스트별로 **무엇을 기대했는지**. 「(아마존 ASIN 등)」 한 문장은 타오바오 상품 앞에서
#   사람을 헷갈리게 한다 — 그 상품엔 ASIN이 있을 리 없다 (F39 오너 지적).
_SKU_EXPECTATION = (
    ("amazon.", "아마존 상품번호(ASIN) — 주소의 `/dp/` 뒤 10자"),
    ("temu.", "Temu 상품번호 — 주소의 `g-…` 또는 `goods_id`"),
    ("1688.", "1688 오퍼 번호 — 주소의 `offer/<번호>.html`"),
    ("tmall.", "티몰 상품번호 — 주소의 `id=` 값"),
    ("taobao.", "타오바오 상품번호 — 주소의 `id=` 값"),
    ("aliexpress.", "알리익스프레스 상품번호 — 주소의 `/item/<번호>.html`"),
    (".tb.cn", "타오바오 상품번호 — 공유 단축 링크에는 상품번호가 없습니다(앱에서 펴진 주소가 필요합니다)"),
)


def sku_expectation(url: str) -> str:
    """이 주소에서 **무엇을 찾으려 했는지** 한 문장. 모르는 호스트면 빈 문자열 (F39)."""
    try:
        host = _host(urlparse(str(url or "").strip()).netloc)
    except Exception:
        return ""
    if not host:
        return ""
    for frag, text in _SKU_EXPECTATION:
        if frag in host:
            return text
    return ""


def sku_failure_message(url: str) -> str:
    """SKU를 못 뽑았을 때 사람에게 할 말 — **무엇을 기대했는지**를 싣는다 (F39)."""
    want = sku_expectation(url)
    if want:
        return f"상품 주소에서 식별자를 찾지 못했습니다. 기대한 값: {want}."
    return "상품 주소에서 식별자를 찾지 못했습니다(알 수 없는 사이트)."


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

    # C-T2': 앱 공유 단축 링크(`e.tb.cn` 계열) — **이게 그 상품의 유일한 식별자다.**
    #   실측(2026-09-11 상하이): 서버에서 이 링크를 펼 수 없다(중국 IP는 로그인 벽, 해외 IP는 연결 거부).
    #   그래서 itemId를 못 얻고, 대신 **링크 자체**를 키로 삼는다.
    #   ① 경로 토큰은 **대소문자를 보존**한다(`h.8IcTrtZuTU19ieN` — 소문자로 접으면 다른 상품과 충돌한다)
    #   ② `tk`를 포함한다(같은 공유를 두 번 담았을 때만 중복으로 잡히게)
    #
    #   ★ 단 `id`가 실려 있으면 **그게 우선**이다(C-T2'' 실측: 폰이 편 최종 URL엔 id가 온다).
    #     같은 상품을 단축 링크로도 담고 편 링크로도 담았을 때, itemId로 하나가 되게 하려는 것이다 —
    #     tk는 공유마다 달라서 같은 상품을 남남으로 만든다.
    if host in ("e.tb.cn", "m.tb.cn") or host.endswith(".tb.cn"):
        gid = _query_id(query, ("id", "itemid"))
        if gid:
            return f"taobao:item:{gid}"
        tok = re.sub(r"^/+", "", path)
        tk = _query_id(query, ("tk",)) or ""
        if tok:
            return f"tbshare:{tok}" + (f":{tk}" if tk else "")

    # 타오바오/티몰/1688: 쿼리 id / offer 경로.
    if any(s in host for s in ("taobao.", "tmall.", "1688.")):
        m = _1688_RE.search(path)
        gid = m.group(1) if m else _query_id(query, ("id", "itemid", "offerid"))
        if gid:
            # C-T2'': 타오바오 계열은 **호스트를 키에 넣지 않는다.** 같은 상품이
            #   `item.taobao.com` · `m.intl.taobao.com` · `main.m.taobao.com`(폰이 편 최종 URL) 등
            #   여러 호스트로 오는데, 호스트를 키에 넣으면 **같은 상품이 남남으로 쌓인다**.
            #   티몰·1688은 그대로 둔다(상품 풀이 다르다 — 여기서 합치는 건 실측 없는 추측이다).
            if "taobao." in host:
                return f"taobao:item:{gid}"
            return f"{host}:item:{gid}"

    # 알리익스프레스: /item/<id>.html.
    if "aliexpress." in host:
        m = _ALI_RE.search(path)
        if m:
            return f"ali:item:{m.group(1)}"

    # 폴백: host + path(쿼리·프래그먼트 제거, 끝 슬래시 정규화). 트래킹 쿼리 무시로 중복 대부분 해소.
    p = re.sub(r"/+$", "", path) or "/"
    return f"{host}{p}".lower()
