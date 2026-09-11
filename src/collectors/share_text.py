"""공유 텍스트 → 상품 링크. **모든 입력구가 쓰는 단일 파서.**

실측 정본(2026-09-11 상하이, 오너 아이폰 · 타오바오 앱 공유 시트)::

    【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356
    「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」
    点击链接直接打开 或者 淘宝搜索直接打开

이 덩어리를 그대로 붙여넣으면 웹 폼이 **"유효한 http/https URL"로 거부**했다.
유저가 손으로 URL만 골라내야 했다는 뜻이다 — 공유 시트는 이 형태로만 주는데.

## 왜 한 곳인가

입력구마다 제 정규식을 갖고 있었다(실측 3벌: `collect_one`의 인라인 `https?://[^\\s]+`,
`telegram_collect._URL_RE`, 웹 폼의 클라이언트 검증). 셋이 서로 다르게 틀리면
"텔레그램은 되는데 웹은 안 되는" 식으로 갈라진다. 그래서 **파서는 하나**고
입력구는 이걸 부르기만 한다.

## 무엇을 건지나 — 그리고 무엇을 안 건지나

건진다: URL · 제목(「」) · `tk` 토큰(보존) · itemId(URL에 있을 때) · 공유 코드.
**안 건진다: 가격·이미지·옵션.** 공유 텍스트에 없기 때문이다.
없는 값을 0이나 빈 문자열로 채우지 않는다 — 그건 수집이 아니라 날조다.
"""
from __future__ import annotations

import base64
import re
from typing import Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

# URL 뒤에 붙어 오는 중국어 문장부호·괄호 — URL의 일부가 아니다.
#   실측: 「…」 앞뒤, 【淘宝】 뒤, 문장 끝 。， 등이 그대로 물려 들어왔다.
_TRAILING = "」』】）)、，。！？…\"'《》〉>,.;:"
_URL_RE = re.compile(r"https?://[^\s<>\"'，。、！？「」【】]+")

# 「제목」 — 타오바오·티몰 공유가 제목을 감싸는 괄호. 【淘宝】는 **플랫폼 태그**라 제목이 아니다.
_TITLE_RE = re.compile(r"[「『]([^」』]{2,200})[」』]")

# 공유 코드(CZ356 같은 것) — 앱이 클립보드로 상품을 찾는 데 쓴다. 보존만 하고 해석하지 않는다.
_SHARE_CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2}[A-Za-z0-9]{3,8})(?![A-Za-z0-9])")

# 단축 도메인 — 본문이 아니라 **리다이렉트**를 들고 있다(T2 해석기 대상).
SHORT_HOSTS = ("e.tb.cn", "m.tb.cn", "s.click.taobao.com", "qr.1688.com")
# 최종 상품 도메인 — 여기까지 오면 itemId를 URL에서 직접 뽑을 수 있다.
ITEM_HOSTS = ("item.taobao.com", "detail.tmall.com", "m.intl.taobao.com",
              "world.taobao.com", "detail.1688.com", "item.tmall.com")


def is_taobao_family(url: str) -> bool:
    """타오바오 계열인가 — **서버가 나가면 안 되는 곳**이다(C-T4'' 실측).

    단축 링크는 해외 IP에서 연결 거부, 상세는 IP 무관 로그인 벽.
    그래서 호출부는 이걸 보고 **서버 수집을 아예 건너뛴다** — 될 리 없는 요청의
    실패 로그는 "시도했다"는 알리바이일 뿐이다.
    """
    host = (urlparse(url).hostname or "").lower() if url else ""
    if not host:
        return False
    fam = ("taobao.", "tmall.", "tb.cn")
    return any(host == h.rstrip(".") or host.endswith("." + h.rstrip(".")) or h in host for h in fam)


def _clean_url(raw: str) -> str:
    """URL 꼬리에 물려 온 문장부호를 떼어낸다. **쿼리는 건드리지 않는다** — `tk`가 거기 있다."""
    u = raw.strip().rstrip(_TRAILING)
    # 괄호가 짝으로 열렸으면 닫는 괄호는 URL의 일부다(위키 링크 등) — 짝이 안 맞을 때만 떼낸다.
    while u.endswith(")") and u.count("(") < u.count(")"):
        u = u[:-1]
    return u


def _host_rank(url: str) -> int:
    """여러 URL이 있을 때 무엇을 상품으로 볼지. 낮을수록 우선."""
    host = (urlparse(url).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in ITEM_HOSTS):
        return 0
    if any(host == h or host.endswith("." + h) for h in SHORT_HOSTS):
        return 1
    return 2


def extract_item_id(url: str) -> str:
    """상품 URL에서 itemId. **없으면 빈 문자열** — 추측해서 만들지 않는다."""
    try:
        q = parse_qs(urlparse(url).query)
    except Exception:
        return ""
    for key in ("id", "itemId", "itemid", "offerId"):
        vals = q.get(key) or []
        if vals and str(vals[0]).strip().isdigit():
            return str(vals[0]).strip()
    m = re.search(r"/(?:item|offer)/(\d{6,})", urlparse(url).path)
    return m.group(1) if m else ""


# 최종 URL에서 **남겨도 되는** 파라미터. 허용목록이다 — 차단목록이 아니다.
#   실측 원문(오너 2026-09-11)엔 18개가 실려 왔고 그중 넷만 열쇠다.
#   나머지는 `suid`(기기 UUID)·`un`(사용자 해시)·`wxsign`·`ut_sk`처럼 **세션성·개인식별 가능** 값이다.
#   차단목록으로 짜면 타오바오가 새 파라미터를 붙이는 날 그게 그대로 저장된다 — 그래서 허용목록이다.
_KEEP_PARAMS = ("id", "price", "tk", "short_name", "sourceType")


def sanitize_final_url(url: str) -> str:
    """최종 URL에서 **열쇠만 남기고** 세션성 값을 떼어낸다. 저장·표시는 이것만 쓴다.

    실측 원문에 들어 있던 것 중 버리는 것: `ut_sk` · `suid` · `un` · `wxsign` · `spm` ·
    `shareUniqueId` · `tbSocialPopKey` 등. 열쇠가 아니고, 남기면 **개인식별 가능한 값을
    우리 이력에 쌓는 셈**이 된다.
    """
    if not url:
        return ""
    try:
        u = urlparse(url)
        q = parse_qs(u.query)
    except Exception:
        return url
    kept = [(k, v[0]) for k in _KEEP_PARAMS for v in [q.get(k) or []] if v]
    query = urlencode(kept)
    return urlunparse((u.scheme, u.netloc, u.path, "", query, ""))


def parse_final_url(url: str) -> dict:
    """리다이렉트가 끝난 **최종 URL**에서 건질 것 — `{item_id, price, currency, tk, short_name}`.

    실측(2026-09-11 상하이, 오너): `e.tb.cn`을 중국 IP에서 열면 리다이렉트만으로
    `id=993154784090` · `price=199` · `tk` · `short_name`이 최종 URL에 실려 온다.
    **로그인도 페이지 렌더도 필요 없다** — 리다이렉트만 따라가면 된다.
    그래서 iOS 단축어의 「URL 확장」이 이걸 할 수 있다(폰이 중국망일 때).

    ※ 호스트·경로는 가정하지 않는다 — **쿼리 파라미터로만** 읽는다.
      타오바오가 최종 착지 경로를 바꿔도 파라미터 이름이 남는 한 계속 동작한다.
    """
    out = {"item_id": "", "price": "", "currency": "", "tk": "", "short_name": ""}
    if not url:
        return out
    try:
        q = parse_qs(urlparse(url).query)
    except Exception:
        return out

    def _one(*keys) -> str:
        for k in keys:
            v = q.get(k) or []
            if v and str(v[0]).strip():
                return str(v[0]).strip()
        return ""

    out["item_id"] = extract_item_id(url)
    # `tk`와 `sp_tk`는 **검증 가능한 파생 관계**다 — `sp_tk = base64(tk)`
    #   (실측 원문: `bnlYcFQ3VkE3bHQ=` → `nyXpT7VA7lt`). 둘 중 하나만 있어도 열쇠를 복원한다.
    out["tk"] = _one("tk")
    if not out["tk"]:
        raw_sp = _one("sp_tk")
        if raw_sp:
            try:
                cand = base64.b64decode(unquote(raw_sp) + "==", validate=False).decode("utf-8")
                if re.fullmatch(r"[A-Za-z0-9_-]{4,64}", cand):
                    out["tk"] = cand
            except Exception:
                pass
    out["short_name"] = _one("short_name", "shortName")
    price = _one("price")
    # 숫자만 인정한다 — "199", "199.00"은 값이고 "면의"는 값이 아니다.
    if re.fullmatch(r"\d+(?:\.\d+)?", price or ""):
        out["price"] = price
        # 타오바오 공유 링크의 price는 **위안(CNY)**이다. 통화를 비워 두면 뒤에서 USD로 오해된다.
        out["currency"] = "CNY"
    return out


def parse_share_text(raw: str, final_url: str = "") -> dict:
    """공유 텍스트(또는 맨 URL) → `{url, title, tk, item_id, price, currency, short_name, ...}`.

    URL이 하나도 없으면 `url`이 빈 문자열이다 — 호출부가 그걸 보고 정직하게 거절한다.

    `final_url`(C-T2''): 폰이 **단축어 「URL 확장」으로 이미 펴 준** 최종 URL.
    중국망에서만 성공하므로 **올 수도 있고 안 올 수도 있다** — 오면 `id`·`price`까지 건지고,
    안 오면 단축 링크와 제목만으로 간다. 두 갈래 다 정직하게 표기한다(한쪽을 다른 쪽인 척 하지 않는다).
    """
    text = str(raw or "").strip()
    urls = [_clean_url(u) for u in _URL_RE.findall(text)]
    urls = [u for u in urls if u.startswith(("http://", "https://"))]
    urls.sort(key=_host_rank)                       # 상품 도메인 > 단축 > 그 외
    url = urls[0] if urls else ""
    # 유저가 **최종 URL을 통째로 붙여넣는** 경우도 있다(사파리 주소창 복사). 그때도 세션성 값을 떼어낸다 —
    #   `final_url` 인자로 올 때만 정제하면 이 경로로 `suid`·`un`·`wxsign`이 그대로 저장된다.
    if url and is_taobao_family(url):
        url = sanitize_final_url(url)

    title = ""
    m = _TITLE_RE.search(text)
    if m:
        title = m.group(1).strip()

    tk = ""
    if url:
        try:
            tk = (parse_qs(urlparse(url).query).get("tk") or [""])[0].strip()
        except Exception:
            tk = ""

    # 공유 코드는 URL 바깥의 토큰에서만 찾는다(URL 안의 대문자 조각이 잡히지 않게).
    outside = text
    for u in urls:
        outside = outside.replace(u, " ")
    codes = [c for c in _SHARE_CODE_RE.findall(outside) if not c.isalpha() or len(c) <= 6]
    host = (urlparse(url).hostname or "").lower() if url else ""

    out = {
        "url": url,
        "title": title,
        "tk": tk,
        "item_id": extract_item_id(url) if url else "",
        "price": "",
        "currency": "",
        "short_name": "",
        "final_url": "",
        "share_code": codes[0] if codes else "",
        "is_short": bool(url) and any(host == h or host.endswith("." + h) for h in SHORT_HOSTS),
        "raw": text,
    }

    # 폰이 펴 준 최종 URL이 함께 왔으면 거기서 id·가격을 건진다(우리가 편 게 아니다 — 폰이 편 것이다).
    #   인자로 안 오고 **본문에 통째로 붙여넣어졌을 수도** 있다(사파리 주소창 복사). 같은 값을 같게 읽는다 —
    #   입력 모양이 달라 결과가 달라지면 그게 "웹은 되는데 단축어는 안 되는" 갈래의 시작이다.
    fin = (final_url or "").strip()
    if not fin.startswith(("http://", "https://")) and url and is_taobao_family(url):
        if parse_final_url(url).get("item_id"):
            fin = url
    if fin.startswith(("http://", "https://")):
        f = parse_final_url(fin)
        out["final_url"] = sanitize_final_url(fin)
        out["item_id"] = f["item_id"] or out["item_id"]
        out["price"] = f["price"]
        out["currency"] = f["currency"]
        out["short_name"] = f["short_name"]
        out["tk"] = out["tk"] or f["tk"]
    return out


def url_from_input(raw: str) -> str:
    """입력구 공용 단축 헬퍼 — 텍스트든 맨 URL이든 상품 URL 하나를 준다(없으면 '')."""
    return parse_share_text(raw).get("url", "")
