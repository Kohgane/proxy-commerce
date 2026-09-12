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
import re
import time
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

MAX_HOPS = 8
TIMEOUT_SEC = 10
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
    out = {"body_item_url": "", "body_item_id": "",
           "body_len": 0, "body_title": "", "body_script_count": 0}
    if not html:
        return out
    out["body_len"] = len(html)
    head = html[:BODY_SCAN_CAP]

    m = _BODY_ITEM_RE.search(head)
    if m:
        from src.collectors.share_text import extract_item_id
        url = m.group(0).rstrip(".,;\"'")
        out["body_item_url"] = url
        out["body_item_id"] = extract_item_id(url)

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


def _probe(url: str, *, ua_label: str, user_agent: str,
           max_hops: int, timeout: int) -> dict:
    """한 UA로 리다이렉트 체인을 **직접 따라가며** 기록한다. 한 번의 측정 = 이 함수 한 번."""
    from src.collectors.share_text import parse_final_url, sanitize_final_url

    out: dict = {"ua_label": ua_label, "ok": False, "hops": [], "final_url": "",
                 "final_url_kept": "", "item_id": "", "price": "", "currency": "",
                 "hop_count": 0, "elapsed_ms": 0, "error": "", "error_class": "",
                 "final_status": 0, "body_scanned": False,
                 "body_item_url": "", "body_item_id": "",
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
            resp = requests.get(cur, headers=headers, allow_redirects=False,
                                timeout=timeout, stream=True)
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
                 "body_item_id": "", "body_len": 0, "body_title": "",
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
