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

# 淘口令(타오커우링) — 앱에 붙여넣어야 열리는 **코드**다. 링크가 아니다.
#   ￥…￥ · $…$ · (…)  안에 8~12자. 우리가 서버에서 풀 수 없다(앱 전용) —
#   그래서 "못 찾았다"가 아니라 **"이건 링크가 아니라 코드다"**라고 말해 준다.
_TAOKOULING_RE = re.compile(r"[￥$¥]([A-Za-z0-9]{8,12})[￥$¥]|\(([A-Za-z0-9]{8,12})\)")

# 스킴이 없는 단축 도메인 — 앱이 "링크 복사" 대신 텍스트를 줄 때 `https://`가 빠져 온다.
#   실측(오너 F7): `_URL_RE`가 `https?://`를 요구해 이 형태를 통째로 놓쳤다.
_BARE_HOST_RE = re.compile(
    r"(?<![\w/@.])((?:[a-z0-9-]+\.)*(?:tb\.cn|taobao\.com|tmall\.com|goofish\.com|1688\.com)"
    r"/[^\s<>\"'，。、！？「」【】]+)", re.I)

# 단축 도메인 — 본문이 아니라 **리다이렉트**를 들고 있다(T2 해석기 대상).
SHORT_HOSTS = ("e.tb.cn", "m.tb.cn", "s.click.taobao.com", "qr.1688.com")
# 최종 상품 도메인 — 여기까지 오면 itemId를 URL에서 직접 뽑을 수 있다.
ITEM_HOSTS = ("item.taobao.com", "detail.tmall.com", "m.intl.taobao.com",
              "world.taobao.com", "detail.1688.com", "item.tmall.com")


# C-F8-b: **수집 입구 전수.** 가드를 호출부마다 두면 입구가 늘 때마다 샌다 —
#   실측(2026-09-12): 여섯 입구 중 「타오바오 요청 0」이 서 있던 곳은 **둘뿐**이었다.
#   그래서 가드는 **코어**(`_collect_real_draft`·`collect_one_url`)에 두고,
#   이 목록은 계약이 순회하며 "새 입구가 생겼는데 코어를 안 타는가"를 검사한다.
COLLECT_ENTRY_POINTS = (
    ("웹 미리보기",      "src/seller_console/views.py",      "/collect/preview"),
    ("웹 일괄",          "src/seller_console/views.py",      "/collect/bulk"),
    ("북마클릿·공유타겟", "src/seller_console/views.py",      "_quick_collect"),
    ("모바일 단건",      "src/api/extension_api.py",         "/one"),
    ("확장 벌크(job)",   "src/api/extension_api.py",         "/bulk"),
    ("텔레그램",         "src/api/telegram_collect.py",      "collect_one_url"),
)
# 셀러 수집 경로가 아닌 곳(관리자 진단·보강 큐)은 목록에 없다 — 같은 코어를 타므로 가드는 받는다.


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


def resolve_gap(share: dict) -> str:
    """초안에 **무엇이 없고, 서버가 그걸 어떻게 아는지** — 넷 중 하나.

    `ok` · `no_final_url` · `final_url_without_id` · `id_without_price`.

    C-F9-1: 이전 문구는 VPN 설정 때문이라고 **단정**했다(있지도 않은 앱 모드 이름까지 들며).
    서버는 폰의 VPN 상태를 모른다 — 오너 실측에서 VPN이 **꺼진 채로** 같은 결과가 나와
    그 단정이 곧바로 오진이 됐다. 그래서 서버는 **자기가 본 것만** 말한다:
    최종 URL이 왔는지 · 거기 상품번호가 있었는지 · 가격이 있었는지.
    원인(VPN·앱·네트워크)은 「링크 진단」이 재서 말한다.
    """
    if share.get("price"):
        return "ok"
    if not (share.get("final_url") or "").strip():
        return "no_final_url"
    if not share.get("item_id"):
        return "final_url_without_id"
    return "id_without_price"


# 갈래별 사용자 문장 — **한 벌만 둔다.** 단건·일괄·미리보기가 각자 문구를 갖고 있어
#   같은 상황이 화면마다 다르게 설명됐다(C-fix F1의 재발 방지).
_GAP_MESSAGE = {
    "ok": ("제목·상품번호·가격까지 담았어요(공유 시점 가격). "
           "이미지·옵션은 PC에서 고가수집기로 보강해 주세요."),
    "no_final_url": ("제목과 링크만 담았어요 — 펴진 링크가 오지 않아 가격·상품번호는 비었습니다. "
                     "가격·이미지는 PC에서 고가수집기로 보강해 주세요. "
                     "링크가 왜 안 펴졌는지는 「링크 진단」이 재 드립니다."),
    "final_url_without_id": ("제목과 링크만 담았어요 — 펴진 링크는 왔는데 거기 상품번호가 없었습니다. "
                             "가격·이미지는 PC에서 고가수집기로 보강해 주세요. "
                             "「링크 진단」에서 최종 URL을 확인하실 수 있습니다."),
    "id_without_price": ("제목·상품번호까지 담았어요 — 가격은 오지 않았습니다. "
                         "가격·이미지는 PC에서 고가수집기로 보강해 주세요."),
}


def gap_message(share: dict) -> str:
    """초안 결과 → 사용자 문장. 서버가 **모르는 것은 말하지 않는다**(VPN 단정 금지)."""
    return _GAP_MESSAGE.get(resolve_gap(share), _GAP_MESSAGE["no_final_url"])


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
    # C-F7: 스킴이 빠져 온 단축 도메인도 건진다(`m.tb.cn/h.xxx`).
    #   실측: 앱이 "링크 복사" 대신 텍스트를 줄 때 `https://`가 없고, 그걸 통째로 놓치고 있었다.
    #   **아는 도메인일 때만** 스킴을 붙인다 — 아무 `a/b`에나 붙이면 오탐이 된다.
    if not urls:
        for m_bare in _BARE_HOST_RE.finditer(text):
            urls.append("https://" + _clean_url(m_bare.group(1)))
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
        # 淘口令이 있으면 **링크가 아니라 코드**가 온 것이다 — 호출부가 그렇게 안내한다.
        "taokouling": (lambda m: (m.group(1) or m.group(2)) if m else "")(_TAOKOULING_RE.search(text)),
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


def link_failure_reason(raw: str, final_url: str = "") -> str:
    """링크를 못 찾았을 때 **무엇을 보고 그렇게 판단했는지** 한 문장으로.

    C-F7 실측(오너 단축어): 인증을 통과한 뒤 「상품 링크를 찾지 못했습니다」 하나만 돌아왔다.
    그 문장으로는 **공유 내용이 비어서 온 건지, 형태가 안 맞는 건지** 알 수 없다 —
    F6에서 401을 가른 것과 같은 이유로 여기도 가른다.

    **원문은 싣지 않는다.** 길이와 판정만 말한다: 내용에 상품명·계정 정보가 섞여 올 수 있고,
    그게 로그·스크린샷으로 새면 우리가 만든 구멍이다.
    """
    text = str(raw or "")
    n = len(text.strip())
    has_final = bool((final_url or "").strip())

    if n == 0:
        # C-F8-a 실측: 타오바오 分享 →「复制链接」은 **타오바오 자체 패널**이라 iOS 공유 시트를
        #   거치지 않는다 → 단축어를 나중에 실행하면 넘어오는 입력이 **항상 빈 값**이다.
        #   클립보드가 유일한 입력원이므로, 그 설정을 콕 집어 말한다(가장 흔한 원인이 이것이다).
        return ("공유 내용이 비어서 왔습니다 — 타오바오 「复制链接」(링크 복사)을 쓰셨다면 "
                "단축어 첫 액션의 「입력이 없으면 → 클립보드 가져오기」를 켜 주세요. "
                "공유 시트를 거치지 않는 방식이라 클립보드가 유일한 입력원입니다."
                + (" 최종 URL은 함께 왔습니다." if has_final else ""))

    tk = _TAOKOULING_RE.search(text)
    if tk:
        return (f"받은 것이 링크가 아니라 타오바오 앱 전용 코드입니다(淘口令, 길이 {n}자). "
                "서버에서는 이 코드를 열 수 없어요 — 앱에서 공유할 때 "
                "「링크 복사」를 고르시면 링크가 옵니다.")

    if "http" in text.lower():
        return (f"링크처럼 보이는 조각은 있는데 주소를 읽지 못했습니다(길이 {n}자). "
                "주소가 중간에 잘렸거나 줄바꿈이 섞인 경우입니다 — 공유 글을 통째로 다시 붙여넣어 주세요.")

    return (f"받은 내용에 상품 링크가 없습니다(길이 {n}자, 링크 조각 0). "
            "앱에서 「공유 → 링크 복사」로 받은 글을 통째로 보내 주세요."
            + (" 최종 URL만 따로 왔는데 본문이 비어 그것만으로는 제목을 못 만듭니다."
               if has_final else ""))


def split_input_blocks(raw: str) -> list:
    """여러 줄 입력 → **항목 단위** 블록. 줄 단위가 아니다.

    실측(오너 2026-09-11, 폰 웹 폼): 공유 텍스트를 「여러 URL 한 번에」에 붙여넣었더니
    `splitlines()`가 **한 상품을 2~3개로 쪼갰다** — 「전체 2개 · 성공 0 · 실패 2」.
    1줄은 단축 링크만 남아 서버가 못 읽고, 2줄은 `点击链接…`이라 링크가 아예 없다.

    규칙 하나면 된다: **URL이 있는 줄이 새 항목을 연다.**
    URL이 없는 줄(제목 「」·`点击链接…`)은 **앞 항목에 붙는다** — 그게 그 항목의 일부니까.

        【淘宝】https://e.tb.cn/h.xxx?tk=yyy CZ356   ← URL 있음 → 항목 1 시작
        「상품 제목」                                  ← URL 없음 → 항목 1에 붙음
        点击链接直接打开 或者 淘宝搜索直接打开          ← URL 없음 → 항목 1에 붙음
        https://item.taobao.com/item.htm?id=123      ← URL 있음 → 항목 2 시작

    맨 URL을 한 줄에 하나씩 넣던 기존 사용법도 그대로 동작한다(줄마다 URL이 있으니까).
    """
    lines = str(raw or "").splitlines()
    blocks: list = []
    for line in lines:
        if not line.strip():
            continue
        if _URL_RE.search(line) or not blocks:
            blocks.append([line])
        else:
            blocks[-1].append(line)
    return ["\n".join(b).strip() for b in blocks if "\n".join(b).strip()]


def url_from_input(raw: str) -> str:
    """입력구 공용 단축 헬퍼 — 텍스트든 맨 URL이든 상품 URL 하나를 준다(없으면 '')."""
    return parse_share_text(raw).get("url", "")
