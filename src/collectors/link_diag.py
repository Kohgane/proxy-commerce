"""링크 진단 — **서버가 이 링크를 어디까지 펼 수 있나**를 서버 자신이 재서 원문으로 돌려준다.

## 왜 만들었나 (C-F9-3)

`e.tb.cn` 302 체인을 **Render 싱가포르에서** 재야 한다는 숙제가 F7-2로 열려 있었다.
CC 샌드박스 프록시가 그 도메인을 막고(`CONNECT tunnel failed`), Render Shell은 오너 손이
필요하다. 그래서 **앱 안에** 재는 자리를 만들었다 — 오너가 폰에서 한 번 누르면 닫힌다.

측정을 사람 손에 맡기면 매번 사람 손이 필요하다. 서버가 스스로 재게 하면 한 번 만들고 끝난다.

## 무엇을 돌려주나 — 원문이다, 요약이 아니다

홉마다 `상태코드`와 `Location` 원문. 최종 URL 원문. 거기서 뽑은 `상품번호`·`가격`.
실패면 **예외 클래스명과 메시지 그대로**(「진단 실패」 같은 말로 덮지 않는다 —
덮으면 진단을 또 해야 한다).

## UA 2종을 각각 잰다 (C-F10-2)

타오바오는 **UA로 응답을 가른다.** 한 가지로만 재면 "막혔다"가 *우리 서버 지역 문제*인지
*UA 문제*인지 구별이 안 된다. 그래서 두 번 재서 둘 다 돌려준다 —
`기본`(UA 미지정 = 라이브러리 기본값)과 `iOS Safari`(오너가 실제로 성공한 환경).
둘이 다르면 그 차이 자체가 답이다.

## 최종 홉이 200이면 본문도 본다 (C-F10-1)

최종 URL 쿼리에 `id`가 없어도 **본문에 상품 링크가 들어 있을 수 있다**(안내·중간 페이지).
그걸 안 보고 "상품번호 없음"이라 말하면 **덜 보고 단정한 것**이다. 그래서 본문에서
상품 도메인 링크와 `id=` 숫자를 찾아 `body_item_url`·`body_item_id`로 **따로** 돌려준다.

최종 URL에서 읽은 값과 **섞지 않는다** — 출처가 다르면 신뢰도도 다르다.
못 찾으면 **본문 길이·`<title>`·`<script>` 개수만** 보고한다(원문은 저장·반환 0).

## 무엇을 안 하나

- **저장 0.** 진단 결과는 이력·DB에 남기지 않는다. 최종 URL 원문엔 `suid`(기기 UUID)·
  `un`(사용자 해시)·`wxsign`이 실려 온다(실측). 화면에 보여 주는 건 오너 자신의 값이지만,
  **쌓아 두면 우리가 만든 구멍**이다. 로그엔 호스트·상태코드·상품번호 유무만 남긴다.
- **본문 원문을 돌려주지 않는다.** 길이·제목·스크립트 수라는 **계량값**만 낸다.
- **임의 호스트 안 딴다.** 허용목록(타오바오 계열·단축 도메인)만. 안 걸면 이 라우트가
  사내에서 밖으로 나가는 **열린 프록시**가 된다.
"""
from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

MAX_HOPS = 8
TIMEOUT_SEC = 10
# 수집 경로에서 단축 링크를 펼 때의 예산. 진단(10s·UA 2종)보다 **짧게** 잡는다 —
#   이건 요청 안에서 도는 코드라, W10에서 동기 번역 체인이 워커를 점유한 흉이 그대로 적용된다.
#
# C-F12-A 실측: 이 값이 **홉당** 타임아웃으로만 쓰이고 있었다. `MAX_HOPS=8`이라
#   최악 8×6 = **48초** — 「6초 예산」은 문서에만 있었고 코드엔 없었다. 폰이
#   「요청한 시간이 초과되었습니다」로 죽은 것이 그대로 설명된다.
#   → 이제 **wall-clock 마감**을 둔다: 홉마다 남은 시간만 준다.
RESOLVE_TIMEOUT_SEC = 6
# 연결과 읽기를 따로 준다. 한 숫자로 주면 "연결이 안 되는 상황"과 "느린 응답"이 같은 예산을
#   쓰고, 연결 단계에서 전부 태울 수 있다.
CONNECT_TIMEOUT_SEC = 3
# 본문에서 훑을 최대 길이. 진단이 페이지 전체를 메모리에 들고 있을 이유가 없다.
BODY_SCAN_CAP = 400_000

_IOS_SAFARI_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                  "Mobile/15E148 Safari/604.1")

# C-F10-2: 이 둘로 각각 잰다. `기본`은 **UA 미지정**(라이브러리 기본값)이라 일부러 비워 둔다 —
#   가리는지 보려면 가려지지 않은 쪽도 있어야 비교가 된다.
UA_PROBES = (("기본", ""), ("iOS Safari", _IOS_SAFARI_UA))

# 진단해도 되는 호스트 — 허용목록. 이 라우트가 열린 프록시가 되지 않게 하는 유일한 장치다.
_ALLOWED_SUFFIXES = ("tb.cn", "taobao.com", "tmall.com", "1688.com", "goofish.com",
                     "alicdn.com", "taobao.net")

# C-F10-1: 본문에 박혀 있을 수 있는 **상품 상세 링크**. 호스트를 못 박아 두는 이유는
#   아무 링크나 "상품"이라 부르지 않기 위해서다 — 상품 도메인만 상품으로 센다.
_BODY_ITEM_RE = re.compile(
    r"https?://(?:item\.taobao\.com|detail\.tmall\.com|item\.tmall\.com|"
    r"world\.taobao\.com|m\.intl\.taobao\.com|(?:www\.)?goofish\.com)"
    r"/[^\s\"'<>\\)]+", re.I)
# 링크가 없어도 `id=993154784090`처럼 숫자만 박혀 있는 경우가 있다(스크립트 안 설정값).
_BODY_ID_RE = re.compile(r"\b(?:item_?id|itemId|id)\s*[=:]\s*[\"']?(\d{8,})", re.I)
# O-4(오너 채팅 실측 2026-10-01, UA iPhone Safari): e.tb.cn은 200·Location 없음·본문이
#   `var url = 'https://item.taobao.com/item.htm?…&id=809968335363&…'; location.replace(url)` —
#   **페이지가 스스로 넘기는 그 주소**가 정답이다. 본문의 다른 상품 링크(추천 등)보다 먼저 본다.
_BODY_JS_REDIRECT_RE = re.compile(r"var\s+url\s*=\s*['\"]([^'\"]+)['\"]\s*;?[^<]{0,200}?location\.replace\s*\(\s*url\s*\)",
                                  re.I | re.S)
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def host_allowed(url: str) -> bool:
    """타오바오 계열인가. 아니면 진단하지 않는다(임의 URL을 서버가 대신 따 주면 안 된다)."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in _ALLOWED_SUFFIXES)


def scan_body_for_item(html: str) -> dict:
    """본문에서 **상품 링크·상품번호**를 찾는다. 못 찾으면 계량값만 낸다.

    반환 `{body_item_url, body_item_id, body_len, body_title, body_script_count}`.
    **본문 원문은 담지 않는다** — 길이·제목·스크립트 수는 "무엇을 받았는지" 가늠할
    최소치이고, 그 이상은 진단에 필요하지 않은데 새면 곤란한 값이다.
    """
    out = {"body_item_url": "", "body_item_id": "", "body_price": "", "body_currency": "",
           "body_len": 0, "body_title": "", "body_script_count": 0}
    if not html:
        return out
    out["body_len"] = len(html)
    head = html[:BODY_SCAN_CAP]

    js = _BODY_JS_REDIRECT_RE.search(head)
    m = _BODY_ITEM_RE.search(js.group(1)) if js else None
    if not m:
        m = _BODY_ITEM_RE.search(head)
    if m:
        from src.collectors.share_text import parse_final_url
        url = m.group(0).rstrip(".,;\"'").replace("&amp;", "&")   # HTML 이스케이프 복원
        out["body_item_url"] = url
        # C-F11 실측(오너 2026-09-12): 본문 링크에 `id`**와 `price`가 함께** 실려 온다
        #   (`…&id=1060535477134&price=76.86&…`). 그래서 같은 파서로 둘을 한 번에 읽는다 —
        #   `id`만 읽고 가격을 버리면 있는 값을 못 쓰는 것이고, 그게 곧 '보강 대기'다.
        f = parse_final_url(url)
        out["body_item_id"] = f.get("item_id", "")
        out["body_price"] = f.get("price", "")
        out["body_currency"] = f.get("currency", "")

    if not out["body_item_id"]:
        m2 = _BODY_ID_RE.search(head)
        if m2:
            out["body_item_id"] = m2.group(1)

    # 못 찾았을 때 **무엇을 받았는지** 가늠할 값 — 로그인 벽인지 빈 셸인지 구별된다.
    t = _TITLE_TAG_RE.search(head)
    if t:
        out["body_title"] = re.sub(r"\s+", " ", t.group(1)).strip()[:200]
    out["body_script_count"] = len(re.findall(r"<script\b", head, re.I))
    return out


def resolve_short_link(url: str, *, timeout: int = RESOLVE_TIMEOUT_SEC) -> dict:
    """단축 링크(`e.tb.cn` 계열)를 **펴서 상품번호·가격만** 건진다.

    ## 실측이 문을 다시 열었다 (오너 2026-09-12, 링크 진단 라이브)

    `e.tb.cn` → **200**(UA 무관) → **본문에** `item.taobao.com/item.htm?…&id=…&price=…`.
    F9까지 우리가 「서버는 타오바오를 못 읽는다」고 적은 건 **리다이렉트 쿼리만 봤기 때문**이다.
    쿼리엔 없었지만 **본문에는 있었다** — 덜 보고 닫은 문이었다.

    그래서 이 함수는 **펴는 일만** 한다:
      · 상품번호(`id`)와 **공유 시점 가격**(`price`)을 본문 링크에서 읽는다
      · 정규형 URL(`item.taobao.com/item.htm?id=<id>`)을 만든다 — 추적 파라미터 전부 버림
      · **페이지를 수집하지 않는다.** 상세·이미지·옵션은 여전히 로그인 벽 뒤다(실측 불변).

    반환 `{ok, item_id, price, currency, canonical_url, final_status, reason, elapsed_ms}`.
    `reason`은 **실패 갈래를 그대로** 싣는다 — `ok`·`no_item_in_body`·`http_<코드>`·
    `error:<예외클래스>`·`not_short_link`. 원인을 짐작해 붙이지 않는다.
    """
    from src.collectors.share_text import canonical_item_url, is_short_link

    out = {"ok": False, "item_id": "", "price": "", "currency": "",
           "canonical_url": "", "final_status": 0, "reason": "", "elapsed_ms": 0}
    if not is_short_link(url):
        out["reason"] = "not_short_link"
        return out
    # 수집 요청 안에서 밖으로 나가는 코드다 — 끌 수 있어야 한다(운영 기본 ON).
    #   테스트는 `conftest`가 OFF로 고정한다: 계약이 네트워크를 재기 시작하면 그건 계약이 아니다.
    if os.getenv("KGP_SHORT_LINK_RESOLVE", "1").strip() == "0":
        out["reason"] = "disabled"
        return out
    try:
        import requests                                            # noqa: F401
    except Exception as exc:                                        # pragma: no cover
        out["reason"] = f"error:{type(exc).__name__}"
        return out

    # 실측에서 성공한 UA로 한 번만 잰다. 수집 경로는 **요청 안에서** 도는 코드라
    #   진단(UA 2종·10s)과 달리 예산을 짧게 잡는다 — W10에서 동기 체인이 워커를 점유한 흉이 있다.
    # **전체 예산**을 걸어 넘긴다 — 홉당이 아니다(실측: 홉당이면 최악 48초였다).
    p = _probe(url, ua_label="수집", user_agent=_IOS_SAFARI_UA,
               max_hops=MAX_HOPS, timeout=timeout,
               deadline=time.monotonic() + float(timeout))
    out["final_status"] = p["final_status"]
    out["elapsed_ms"] = p["elapsed_ms"]

    if p["error_class"] == "BudgetExceeded":
        out["reason"] = "timeout"                 # 오너 지정 갈래 — 초안은 그대로 세운다
        return out
    if p["error_class"]:
        out["reason"] = f"error:{p['error_class']}"
        return out
    # 쿼리에 실려 온 값이 있으면 그게 1순위(출처가 더 짧다), 없으면 본문에서 찾은 값.
    item_id = p["item_id"] or p["body_item_id"]
    price = p["price"] or p["body_price"]
    currency = p["currency"] or p["body_currency"]
    if not item_id:
        out["reason"] = ("no_item_in_body" if p["final_status"] == 200
                         else f"http_{p['final_status'] or 0}")
        return out

    out.update({"ok": True, "item_id": item_id, "price": price, "currency": currency,
                "canonical_url": canonical_item_url(item_id), "reason": "ok"})
    # 로그엔 **원문 URL을 남기지 않는다** — 단축 링크에도 `tk`가 붙어 온다.
    logger.info("[단축링크 펴기] host=%s 최종=%s 상품번호=%s 가격=%s%s %sms",
                (urlparse(url).hostname or "?"), p["final_status"],
                item_id, price or "-", currency or "", p["elapsed_ms"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 오너 11-25 15:56 「짧은 링크를 서버가 푼다」 — 아마존·알리 공유 단축 주소.
#   표본: 쿠팡 보류 「원본 상품 주소 없음 (지금 주소: https://a.co/d/00RG5ThB)」 — 이 주소엔 ASIN이 없어 SKU가 비었다.
#   아마존·알리 단축 주소는 **리다이렉트(Location)** 에 상품 주소를 싣는다(타오바오는 본문). 그래서 펴는 법이 다르다 —
#   하지만 **부르는 곳은 한 곳**(`resolve_share_link`)이다. 상품 페이지 본문은 받지 않는다(봇 차단 · 필요 없음):
#   Location에서 상품번호가 읽히는 순간 멈춘다.
#
# 허용목록이 곧 안전장치다 — 단축 호스트에서 출발하고, 따라가는 홉도 그 마켓 도메인 안에서만 간다(열린 프록시 금지).
SHARE_SHORT_HOSTS = {
    "a.co": "amazon", "amzn.to": "amazon", "amzn.asia": "amazon", "amzn.eu": "amazon", "amzn.com": "amazon",
    "a.aliexpress.com": "aliexpress", "s.click.aliexpress.com": "aliexpress", "click.aliexpress.com": "aliexpress",
}
_HOP_SUFFIXES = {
    "amazon": ("a.co", "amzn.to", "amzn.asia", "amzn.eu", "amzn.com", "amazon.com", "amazon.co.jp", "amazon.co.uk",
               "amazon.de", "amazon.fr", "amazon.it", "amazon.es", "amazon.ca", "amazon.com.au", "amazon.in",
               "amazon.com.mx", "amazon.sg", "amazon.ae", "amazon.com.br", "amazon.nl", "amazon.se", "amazon.pl"),
    "aliexpress": ("aliexpress.com", "aliexpress.us", "aliexpress.ru"),
}
_ALI_ITEM_RE = re.compile(r"https?://(?:[a-z0-9-]+\.)*aliexpress\.(?:com|us|ru)/item/(\d{6,20})\.html", re.I)
_ALI_BODY_ID_RE = re.compile(r"(?:productId|productIds|item_id)[\"'=:\s]+(\d{10,20})", re.I)


def _host_of(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower()


def _under(host: str, suffixes) -> bool:
    return any(host == s or host.endswith("." + s) for s in suffixes)


def short_link_market(url: str) -> str:
    """`url`이 공유 단축 주소면 그 마켓(`taobao`·`amazon`·`aliexpress`), 아니면 ''."""
    from src.collectors.share_text import is_short_link
    if is_short_link(url):
        return "taobao"
    return SHARE_SHORT_HOSTS.get(_host_of(url), "")


def _item_from_url(market: str, url: str) -> tuple:
    """`(상품번호, 정규형 주소)` — 못 읽으면 `('', '')`. 지어내지 않는다."""
    from src.collectors.product_key import extract_asin
    host = _host_of(url)
    if market == "amazon" and _under(host, _HOP_SUFFIXES["amazon"]) and "amazon." in host:
        asin = extract_asin(url)
        if asin:
            return asin, f"https://{host}/dp/{asin}"
    if market == "aliexpress":
        m = _ALI_ITEM_RE.search(url or "")
        if m:
            return m.group(1), f"https://www.aliexpress.com/item/{m.group(1)}.html"
    return "", ""


_RESOLVED: dict = {}          # 같은 요청 흐름(중복 확인 → 수집 → 사전검증)에서 두 번 나가지 않게 — 성공만 10분
_RESOLVED_TTL = 600.0


def resolve_share_link(url: str, *, timeout: int = RESOLVE_TIMEOUT_SEC) -> dict:
    """공유 단축 주소(타오바오·아마존·알리) → 정본 주소. **한 입구.** 성공한 결과는 10분 기억한다."""
    key = str(url or "").strip()
    hit = _RESOLVED.get(key)
    if hit and time.time() - hit[0] < _RESOLVED_TTL:
        return dict(hit[1], cached=True)
    out = _resolve_share_link(key, timeout=timeout)
    if out.get("ok"):
        if len(_RESOLVED) > 256:
            _RESOLVED.clear()
        _RESOLVED[key] = (time.time(), dict(out))
    return out


def _resolve_share_link(url: str, *, timeout: int = RESOLVE_TIMEOUT_SEC) -> dict:
    """공유 단축 주소(타오바오·아마존·알리) → 정본 주소. **한 입구.**

    반환 `{ok, market, item_id, canonical_url, reason, hops, elapsed_ms}`.
    `hops`는 `[{status, host}]`만 — 쿼리(추적값)는 싣지 않는다. 실패 사유는 갈래 그대로(`http_403`·`timeout`·
    `no_item_in_location`·`error:<예외>`·`not_short_link`·`disabled`).
    """
    market = short_link_market(url)
    out = {"ok": False, "market": market, "item_id": "", "canonical_url": "", "reason": "", "hops": [], "elapsed_ms": 0}
    if not market:
        out["reason"] = "not_short_link"
        return out
    if market == "taobao":
        r = resolve_short_link(url, timeout=timeout)
        out.update({"ok": bool(r.get("ok")), "item_id": r.get("item_id", ""), "canonical_url": r.get("canonical_url", ""),
                    "reason": r.get("reason", ""), "elapsed_ms": r.get("elapsed_ms", 0),
                    "price": r.get("price", ""), "currency": r.get("currency", "")})
        return out
    if os.getenv("KGP_SHORT_LINK_RESOLVE", "1").strip() == "0":
        out["reason"] = "disabled"
        return out
    import requests
    t0, deadline = time.time(), time.monotonic() + float(timeout)
    headers = {"User-Agent": _IOS_SAFARI_UA, "Accept": "text/html,application/xhtml+xml,*/*",
               "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
    cur = url
    try:
        for _n in range(MAX_HOPS):
            left = deadline - time.monotonic()
            if left <= 0.3:
                out["reason"] = "timeout"
                break
            if not _under(_host_of(cur), _HOP_SUFFIXES[market]):
                out["reason"] = f"off_host:{_host_of(cur)}"          # 마켓 밖으로 보내면 따라가지 않는다
                break
            resp = requests.get(cur, headers=headers, allow_redirects=False,
                                timeout=(min(CONNECT_TIMEOUT_SEC, left), left), stream=True)
            loc = resp.headers.get("Location", "") or ""
            out["hops"].append({"status": int(resp.status_code), "host": _host_of(cur)})
            if 300 <= resp.status_code < 400 and loc:
                resp.close()
                cur = urljoin(cur, loc)
                iid, canon = _item_from_url(market, cur)
                if iid:
                    out.update({"ok": True, "item_id": iid, "canonical_url": canon, "reason": "ok"})
                    break
                continue
            # 리다이렉트가 끝났다 — 지금 주소에서, 그다음 본문 앞부분에서 한 번 더 찾는다(알리는 JS로 넘길 때가 있다).
            iid, canon = _item_from_url(market, cur)
            if not iid and resp.status_code == 200:
                head = ""
                try:
                    head = next(resp.iter_content(BODY_SCAN_CAP, decode_unicode=False), b"").decode("utf-8", "ignore")
                except Exception:                                     # noqa: BLE001
                    head = ""
                m = _ALI_ITEM_RE.search(head) if market == "aliexpress" else None
                if m:
                    iid, canon = _item_from_url(market, m.group(0))
                elif market == "amazon":
                    from src.collectors.product_key import extract_asin
                    a = extract_asin(head[:BODY_SCAN_CAP]) if "/dp/" in head else ""
                    if a:
                        iid, canon = a, f"https://{_host_of(cur)}/dp/{a}"
            resp.close()
            if iid:
                out.update({"ok": True, "item_id": iid, "canonical_url": canon, "reason": "ok"})
            else:
                out["reason"] = "no_item_in_location" if resp.status_code == 200 else f"http_{resp.status_code}"
            break
        else:
            out["reason"] = out["reason"] or "too_many_hops"
    except Exception as exc:                                          # noqa: BLE001 — 사유를 그대로
        out["reason"] = f"error:{type(exc).__name__}"
    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    logger.info("[단축링크 펴기] %s host=%s → %s 상품번호=%s %sms", market, _host_of(url), out["reason"],
                out["item_id"] or "-", out["elapsed_ms"])
    return out


_BOT_MARKERS = ("captcha", "robot check", "are you a robot", "punish", "x5sec", "slide to verify", "/errors/validatecaptcha",
                "_____tmd_____", "verify you are human", "unusual traffic")


def share_diag(url: str) -> dict:
    """오너 11-25 15:56 ④ — 아마존·알리 링크를 **서버가 어디까지 읽나** 실측(링크 진단 화면에서 오너가 누른다).

    ① 단축 주소 펴기(`resolve_share_link`) ② 정본 주소 GET 한 번(상태·최종 호스트·제목·차단 표식) ③ 수집기(dispatcher)
    결과(제목·사진 수·가격 또는 실패 원문). 본문 원문은 돌려주지 않는다(길이·제목·표식만). 허용 호스트 밖은 안 간다."""
    out = {"market": "", "resolve": None, "page": None, "collector": None}
    market = short_link_market(url)
    host = _host_of(url)
    if not market:
        market = "amazon" if "amazon." in host else ("aliexpress" if "aliexpress." in host else "")
    out["market"] = market
    if market not in ("amazon", "aliexpress"):
        return out
    canon = url
    if short_link_market(url):
        out["resolve"] = resolve_share_link(url)
        canon = out["resolve"].get("canonical_url") or ""
    if not canon:
        return out
    try:
        import requests
        cur, page = canon, {"status": 0, "host": "", "title": "", "body_len": 0, "blocked": [], "hops": 0}
        for _n in range(4):
            if not _under(_host_of(cur), _HOP_SUFFIXES[market]):
                page["host"] = _host_of(cur); page["off_host"] = True
                break
            resp = requests.get(cur, headers={"User-Agent": _IOS_SAFARI_UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
                                allow_redirects=False, timeout=(CONNECT_TIMEOUT_SEC, TIMEOUT_SEC))
            page.update({"status": int(resp.status_code), "host": _host_of(cur), "hops": _n + 1})
            loc = resp.headers.get("Location", "") or ""
            if 300 <= resp.status_code < 400 and loc:
                cur = urljoin(cur, loc)
                continue
            body = resp.text[:BODY_SCAN_CAP] if resp.status_code == 200 else (resp.text or "")[:20000]
            t = _TITLE_TAG_RE.search(body)
            low = body.lower()
            page.update({"title": re.sub(r"\s+", " ", t.group(1)).strip()[:160] if t else "", "body_len": len(body),
                         "blocked": [m for m in _BOT_MARKERS if m in low]})
            break
        out["page"] = page
    except Exception as exc:                                          # noqa: BLE001 — 원문 그대로
        out["page"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    try:
        from src.collectors.dispatcher import collect as _dcollect
        res = _dcollect(canon)
        out["collector"] = {"title": (getattr(res, "title", "") or "")[:120], "images": len(getattr(res, "images", []) or []),
                            "price": str(getattr(res, "price", "") or ""), "currency": str(getattr(res, "currency", "") or ""),
                            "error": str(getattr(res, "error", "") or "")[:200]}
    except Exception as exc:                                          # noqa: BLE001
        out["collector"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return out


def _probe(url: str, *, ua_label: str, user_agent: str,
           max_hops: int, timeout: int, deadline: float | None = None) -> dict:
    """한 UA로 리다이렉트 체인을 **직접 따라가며** 기록한다. 한 번의 측정 = 이 함수 한 번."""
    from src.collectors.share_text import parse_final_url, sanitize_final_url

    out: dict = {"ua_label": ua_label, "ok": False, "hops": [], "final_url": "",
                 "final_url_kept": "", "item_id": "", "price": "", "currency": "",
                 "hop_count": 0, "elapsed_ms": 0, "error": "", "error_class": "",
                 "final_status": 0, "body_scanned": False,
                 "body_item_url": "", "body_item_id": "", "body_price": "",
                 "body_currency": "",
                 "body_len": 0, "body_title": "", "body_script_count": 0}

    import requests

    headers = {"Accept": "text/html,application/xhtml+xml,*/*",
               "Accept-Language": "zh-CN,zh;q=0.9,ko;q=0.8"}
    if user_agent:
        headers["User-Agent"] = user_agent      # 비우면 라이브러리 기본값이 그대로 간다

    t0 = time.time()
    cur, final_resp = url, None
    try:
        for n in range(1, max_hops + 1):
            # C-F12-A: 남은 예산을 홉마다 다시 계산한다. 마감을 넘겼으면 **더 안 나간다** —
            #   요청이 죽는 것보다 부분 초안이 낫다(호출부가 `server_timeout`으로 읽는다).
            if deadline is not None:
                left = deadline - time.monotonic()
                if left <= 0.3:
                    out["error"] = f"예산({timeout}s) 초과 — {n - 1}홉에서 멈췄습니다."
                    out["error_class"] = "BudgetExceeded"
                    out["final_url"] = cur
                    break
                hop_timeout = (min(CONNECT_TIMEOUT_SEC, left), left)
            else:
                hop_timeout = (min(CONNECT_TIMEOUT_SEC, timeout), timeout)
            resp = requests.get(cur, headers=headers, allow_redirects=False,
                                timeout=hop_timeout, stream=True)
            loc = resp.headers.get("Location", "") or ""
            out["hops"].append({"n": n, "status": int(resp.status_code),
                                "location": loc,
                                "host": (urlparse(cur).hostname or "")})
            if 300 <= resp.status_code < 400 and loc:
                try:
                    resp.close()
                except Exception:
                    pass
                cur = urljoin(cur, loc)          # 상대 Location도 정상 처리
                continue
            out["final_url"] = cur
            out["final_status"] = int(resp.status_code)
            out["ok"] = True
            final_resp = resp                    # 본문은 **여기서만** 읽는다
            break
        else:
            out["final_url"] = cur
            out["error"] = f"리다이렉트가 {max_hops}홉에서도 끝나지 않았습니다."
    except Exception as exc:
        # 「진단 실패」로 덮지 않는다 — 클래스명과 메시지가 곧 다음 판단의 근거다.
        out["error"] = str(exc)[:400]
        out["error_class"] = type(exc).__name__
        out["final_url"] = cur

    # C-F10-1: 최종이 200이면 **본문도 본다.** 안 보고 "상품번호 없음"이라 말하면 덜 본 것이다.
    if final_resp is not None and out["final_status"] == 200:
        try:
            out.update(scan_body_for_item(final_resp.text or ""))
            out["body_scanned"] = True
        except Exception as exc:
            out["error"] = out["error"] or f"본문을 읽지 못했습니다: {exc}"[:400]
            out["error_class"] = out["error_class"] or type(exc).__name__
    if final_resp is not None:
        try:
            final_resp.close()
        except Exception:
            pass

    out["hop_count"] = len(out["hops"])
    out["elapsed_ms"] = int((time.time() - t0) * 1000)

    if out["final_url"]:
        f = parse_final_url(out["final_url"])
        out["item_id"] = f.get("item_id", "")
        out["price"] = f.get("price", "")
        out["currency"] = f.get("currency", "")
        out["final_url_kept"] = sanitize_final_url(out["final_url"])

    out["note"] = _note_for(out)
    # 로그엔 **원문 URL도 본문도 남기지 않는다**(세션성 값·상품 정보가 실려 있다).
    logger.info("[link-diag] ua=%s host=%s hops=%s 최종=%s URL상품번호=%s 본문상품번호=%s "
                "가격=%s 오류=%s %sms",
                ua_label, (urlparse(url).hostname or "?"), out["hop_count"],
                out["final_status"] or "-", out["item_id"] or "-",
                out["body_item_id"] or "-", out["price"] or "-",
                out["error_class"] or "-", out["elapsed_ms"])
    return out


def _note_for(p: dict) -> str:
    """이 측정이 무엇을 뜻하는지 한 줄. **추측은 안 붙인다.**"""
    if p["item_id"] and p["price"]:
        return ("서버가 이 링크를 펼 수 있습니다 — 상품번호·가격이 최종 URL에 실려 왔습니다. "
                "폰 단축어 없이도 담을 수 있다는 뜻입니다.")
    if p["item_id"]:
        return "서버가 링크를 펴서 상품번호까지 얻었습니다. 가격은 최종 URL에 없었습니다."
    if p["body_item_id"]:
        return ("최종 URL엔 상품번호가 없지만 **본문에 상품 링크가 있습니다** — "
                "한 번 더 따라가면 상품에 닿을 수 있다는 뜻입니다.")
    if p["ok"] and p["body_scanned"]:
        return ("링크는 펴졌고 본문도 읽었지만 상품 링크·상품번호가 없습니다 — "
                "로그인 벽이나 빈 셸(JS로 그리는 페이지)일 수 있습니다. "
                "아래 본문 계량값이 어느 쪽인지 가늠할 단서입니다.")
    if p["ok"]:
        return (f"링크는 펴졌지만 최종 응답이 {p['final_status']}라 본문을 읽지 않았습니다. "
                "홉 목록의 마지막 주소를 확인해 주세요.")
    return ("서버에서 이 링크를 열지 못했습니다. 아래 오류가 원문입니다 — "
            "연결 거부면 우리 서버 지역에서 막힌 것이고, 그때는 폰이 펴는 지금 방식이 정답입니다.")


def _rank(p: dict) -> tuple:
    """어느 측정이 **더 멀리 갔나**. 대표(요약)로 올릴 하나를 고르는 기준."""
    return (bool(p.get("item_id")), bool(p.get("body_item_id")),
            bool(p.get("price")), bool(p.get("ok")), p.get("hop_count", 0))


def diagnose_link(url: str, *, max_hops: int = MAX_HOPS,
                  timeout: int = TIMEOUT_SEC, user_agent: str = "") -> dict:
    """UA 2종으로 각각 재서 **둘 다** 돌려준다.

    반환 = 가장 멀리 간 측정을 **최상위에 펼치고**(`hops`·`final_url`·`item_id`·
    `body_item_id`·`note`…) 전체를 `probes`에 담는다. 호출부가 갈래를 몰라도 읽히고,
    둘을 비교하고 싶으면 `probes`를 보면 된다.

    `user_agent`를 주면 **그 하나만** 잰다(단일 측정을 원하는 호출부용).
    """
    out: dict = {"ok": False, "probes": [], "hops": [], "final_url": "",
                 "final_url_kept": "", "item_id": "", "price": "", "currency": "",
                 "hop_count": 0, "elapsed_ms": 0, "error": "", "error_class": "",
                 "final_status": 0, "body_scanned": False, "body_item_url": "",
                 "body_item_id": "", "body_price": "", "body_currency": "",
                 "body_len": 0, "body_title": "",
                 "body_script_count": 0, "note": "", "ua_disagree": False}

    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        out["error"] = "http/https 주소가 아닙니다."
        out["note"] = _note_for(out)
        return out
    if not host_allowed(url):
        out["error"] = ("타오바오 계열 주소만 진단합니다 — 서버가 임의 주소를 대신 따 주면 "
                        "그건 진단이 아니라 우회로가 됩니다.")
        out["note"] = _note_for(out)
        return out
    try:
        import requests                                            # noqa: F401
    except Exception as exc:                                       # pragma: no cover
        out["error"] = str(exc); out["error_class"] = type(exc).__name__
        out["note"] = _note_for(out)
        return out

    probes = [("직접 지정", user_agent)] if user_agent else list(UA_PROBES)
    for label, ua in probes:
        out["probes"].append(_probe(url, ua_label=label, user_agent=ua,
                                    max_hops=max_hops, timeout=timeout))

    best = max(out["probes"], key=_rank)
    for k, v in best.items():
        if k != "ua_label":
            out[k] = v
    out["best_ua"] = best.get("ua_label", "")
    # UA가 응답을 가르는지 — 그 자체가 측정 결과다(둘이 다르면 화면이 그렇게 말한다).
    out["ua_disagree"] = len({(p["final_status"], bool(p["item_id"]),
                               bool(p["body_item_id"]), p["error_class"])
                              for p in out["probes"]}) > 1
    return out
