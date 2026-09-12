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

## 무엇을 안 하나

- **저장 0.** 진단 결과는 이력·DB·로그에 남기지 않는다. 최종 URL 원문엔 `suid`(기기 UUID)·
  `un`(사용자 해시)·`wxsign`이 실려 온다(실측). 화면에 보여 주는 건 오너 자신의 값이지만,
  **쌓아 두면 우리가 만든 구멍**이다. 로그엔 호스트·상태코드·상품번호 유무만 남긴다.
- **임의 호스트 안 딴다.** 허용목록(타오바오 계열·단축 도메인)만. 안 걸면 이 라우트가
  사내에서 밖으로 나가는 **열린 프록시**가 된다.
- **본문 안 읽는다.** HEAD/리다이렉트 헤더만. 상세 페이지는 어차피 로그인 벽이다(실측).
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

MAX_HOPS = 8
TIMEOUT_SEC = 10

# 진단해도 되는 호스트 — 허용목록. 이 라우트가 열린 프록시가 되지 않게 하는 유일한 장치다.
_ALLOWED_SUFFIXES = ("tb.cn", "taobao.com", "tmall.com", "1688.com", "goofish.com",
                     "alicdn.com", "taobao.net")


def host_allowed(url: str) -> bool:
    """타오바오 계열인가. 아니면 진단하지 않는다(임의 URL을 서버가 대신 따 주면 안 된다)."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in _ALLOWED_SUFFIXES)


def diagnose_link(url: str, *, max_hops: int = MAX_HOPS,
                  timeout: int = TIMEOUT_SEC, user_agent: str = "") -> dict:
    """리다이렉트 체인을 **직접 따라가며** 기록한다.

    반환:
      `{ok, hops:[{n, status, location, host}], final_url, final_url_kept,
         item_id, price, currency, hop_count, elapsed_ms, error, error_class, note}`

    `final_url`은 **원문**(진단용), `final_url_kept`는 우리가 실제로 저장할 형태
    (`sanitize_final_url` 통과분). 둘을 나란히 보여 주는 게 진단의 요점이다 —
    "무엇이 왔고, 그중 무엇을 우리가 버리는지"가 한눈에 보인다.
    """
    from src.collectors.share_text import parse_final_url, sanitize_final_url

    out: dict = {"ok": False, "hops": [], "final_url": "", "final_url_kept": "",
                 "item_id": "", "price": "", "currency": "", "hop_count": 0,
                 "elapsed_ms": 0, "error": "", "error_class": "", "note": ""}

    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        out["error"] = "http/https 주소가 아닙니다."
        return out
    if not host_allowed(url):
        out["error"] = ("타오바오 계열 주소만 진단합니다 — 서버가 임의 주소를 대신 따 주면 "
                        "그건 진단이 아니라 우회로가 됩니다.")
        return out

    try:
        import requests
    except Exception as exc:                                      # pragma: no cover
        out["error"] = str(exc); out["error_class"] = type(exc).__name__
        return out

    # 폰에서 성공한 조건을 되짚으려면 UA도 같아야 한다 — 기본은 iOS 사파리(오너 실측 환경).
    ua = user_agent or ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                        "Mobile/15E148 Safari/604.1")
    headers = {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,*/*",
               "Accept-Language": "zh-CN,zh;q=0.9,ko;q=0.8"}

    t0 = time.time()
    cur = url
    try:
        for n in range(1, max_hops + 1):
            # 리다이렉트를 **우리가** 따라간다 — 그래야 홉마다 무엇이 왔는지 남는다.
            resp = requests.get(cur, headers=headers, allow_redirects=False,
                                timeout=timeout, stream=True)
            loc = resp.headers.get("Location", "") or ""
            out["hops"].append({"n": n, "status": int(resp.status_code),
                                "location": loc,
                                "host": (urlparse(cur).hostname or "")})
            try:
                resp.close()
            except Exception:
                pass
            if 300 <= resp.status_code < 400 and loc:
                cur = urljoin(cur, loc)          # 상대 Location도 정상 처리
                continue
            out["final_url"] = cur
            out["ok"] = True
            break
        else:
            out["final_url"] = cur
            out["error"] = f"리다이렉트가 {max_hops}홉에서도 끝나지 않았습니다."
    except Exception as exc:
        # 「진단 실패」로 덮지 않는다 — 클래스명과 메시지가 곧 다음 판단의 근거다.
        out["error"] = str(exc)[:400]
        out["error_class"] = type(exc).__name__
        out["final_url"] = cur

    out["hop_count"] = len(out["hops"])
    out["elapsed_ms"] = int((time.time() - t0) * 1000)

    if out["final_url"]:
        f = parse_final_url(out["final_url"])
        out["item_id"] = f.get("item_id", "")
        out["price"] = f.get("price", "")
        out["currency"] = f.get("currency", "")
        out["final_url_kept"] = sanitize_final_url(out["final_url"])

    # C-F9-3 판정 — 이 결과가 무엇을 뜻하는지 한 줄. **추측은 안 붙인다.**
    if out["item_id"] and out["price"]:
        out["note"] = ("서버가 이 링크를 펼 수 있습니다 — 상품번호·가격이 최종 URL에 실려 왔습니다. "
                       "폰 단축어 없이도 담을 수 있다는 뜻입니다.")
    elif out["item_id"]:
        out["note"] = "서버가 링크를 펴서 상품번호까지 얻었습니다. 가격은 최종 URL에 없었습니다."
    elif out["ok"]:
        out["note"] = ("링크는 펴졌지만 최종 URL에 상품번호가 없습니다 — 로그인·안내 페이지로 "
                       "떨어졌을 수 있습니다. 홉 목록의 마지막 주소를 확인해 주세요.")
    else:
        out["note"] = ("서버에서 이 링크를 열지 못했습니다. 아래 오류가 원문입니다 — "
                       "연결 거부면 우리 서버 지역에서 막힌 것이고, 그때는 폰이 펴는 지금 방식이 정답입니다.")

    # 로그엔 **원문 URL을 남기지 않는다**(세션성 값이 실려 있다).
    logger.info("[link-diag] host=%s hops=%s 최종상품번호=%s 가격=%s 오류=%s %sms",
                (urlparse(url).hostname or "?"), out["hop_count"],
                out["item_id"] or "-", out["price"] or "-",
                out["error_class"] or "-", out["elapsed_ms"])
    return out
