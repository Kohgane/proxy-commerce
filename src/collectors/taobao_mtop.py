"""Z3(오너 2026-10-04) 실측 — 타오바오 모바일 상세 API(`mtop.taobao.detail.getdetail`)를 **익명**으로 부를 수 있나.

조회만 한다(쓰기 0). 결과는 숫자와 응답 코드(ret)만 — 쿠키·토큰 값은 남기지 않는다.
  1) e.tb.cn 공유 링크 → 리다이렉트를 따라가 상품번호(id=)
  2) h5api 1차(토큰 없음) → `_m_h5_tk` 쿠키 → 서명 md5(token&t&appKey&data) 붙여 2차
  3) 제목 길이 · 가격 · 갤러리 수 · SKU 수 · 옵션 축/값 수 · 상세(getdesc) 이미지 수
운영(Render) 진단 화면 `/admin/diagnostics/taobao-mtop`이 부른다. 같은 절차가 볼트 `scripts/srv/mtop_probe.py`(오너 서버).

Z3 자동 경로(오너 2026-10-05) — 서버 IP(싱가포르·서울)는 RGV587, 한국 주거 회선(폰 LTE·PC 집)은 **x5 핸드셰이크**로 통과:
  a) 1차 응답 본문이 `_____tmd_____/page/set_x5referer`로 보내는 **스크립트**면 그 URL(+x5referer)을 **같은 쿠키통**으로 GET
     → Set-Cookie(x5sec 등) 보존 → 원 요청 재시도
  b) 그다음 `_m_h5_tk` 토큰 왕복 → 서명 → getdetail
  c) 응답이 punish/captcha(`_____tmd_____/punish`·RGV587)면 그 건은 **(c) 수동 경로**(폰 사진·옵션 직접 입력)로 — 사유를 남긴다
경로 3가지: direct(이 서버) · relay(relay2 서울, mkt.php 새 판 — Set-Cookie·Location 전달) ·
proxy(`TAOBAO_PROXY_URL`, 한국 주거 회전형 — **이 모듈의 세션에만** 싣는다. 쿠팡·네이버·그 밖의 호출은 절대 안 탄다).
호출 간격 2~3초(`TAOBAO_MTOP_GAP_SEC`, 테스트는 0) · API 호출당 최대 3회.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from urllib.parse import quote, urlencode

APPKEY = "12574478"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")
_DESC_IMG = re.compile(r'(//[^"\s<>]+?\.(?:jpg|jpeg|png|webp|gif))')


MAX_TRIES = 3
# Z3-H(오너 2026-10-05 15:51 실측: GET 200인데 x5sec 없음 ×3) — 스크립트가 어떻게 이어 붙이든 URL이 `x5referer=`로 끝나면 꼬리를 붙인다.
_X5_RE = re.compile(r'(?:window\.)?location(?:\.href)?\s*=\s*["\']([^"\']*_____tmd_____/page/set_x5referer[^"\']*)["\']')
_PUNISH_RE = re.compile(r"_____tmd_____/(?:punish|verify)|captcha|nocaptcha|baxia", re.I)
# 본문 JS로 심는 쿠키(document.cookie = "x5sec=…; path=/; domain=.taobao.com") · 맨 x5sec=… 폴백
_COOKIE_JS = re.compile(r"""document\.cookie\s*=\s*["']\s*([A-Za-z0-9_]+)\s*=\s*([^;"']+)""")
_X5SEC_ANY = re.compile(r"\bx5sec\s*[=:]\s*[\"']?([A-Za-z0-9%._\-]{8,})")
_LAST = [0.0]
_sleep = time.sleep


def gap_range() -> tuple:
    """호출 간격(초) — `TAOBAO_MTOP_GAP_SEC`: 「2-3」(기본) · 「0」(테스트)."""
    raw = os.getenv("TAOBAO_MTOP_GAP_SEC", "2-3").strip() or "2-3"
    try:
        lo, _, hi = raw.partition("-")
        lo_f = float(lo)
        return lo_f, float(hi) if hi else lo_f
    except ValueError:
        return 2.0, 3.0


def _pace() -> None:
    lo, hi = gap_range()
    if hi <= 0:
        return
    wait = random.uniform(lo, hi) - (time.monotonic() - _LAST[0])
    if _LAST[0] and wait > 0:
        _sleep(wait)
    _LAST[0] = time.monotonic()


# Z3-P(오너 2026-10-05, IPRoyal Residential): `http://<user>:<pass>_country-kr[_session-XXXXXXXX_lifetime-30m]@geo.iproyal.com:12321`
#   오너가 session 붙은 값/안 붙은 값 어느 쪽을 넣어도 — 비밀번호에서 `_session-…`·`_lifetime-…`를 떼어 base로 두고,
#   **상품마다 결정적 session id**(상품 키 sha1 앞 8자)를 붙인다. 같은 상품의 핸드셰이크 → getdetail은 같은 session(= 같은 IP).
_SESSION_PART = re.compile(r"_session-[A-Za-z0-9]+")
_LIFETIME_PART = re.compile(r"_lifetime-[0-9]+[smhd]?")


def proxy_parts() -> dict:
    """`{scheme, user, base_pass, host, port, country}` — 미설정이면 빈 dict. 값은 화면·로그에 그대로 안 낸다."""
    from urllib.parse import unquote, urlsplit
    raw = os.getenv("TAOBAO_PROXY_URL", "").strip()
    if not raw:
        return {}
    u = urlsplit(raw if "://" in raw else "http://" + raw)
    pw = unquote(u.password or "")
    base = _LIFETIME_PART.sub("", _SESSION_PART.sub("", pw))
    m = re.search(r"_country-([a-z]{2})", base, re.I)
    return {"scheme": u.scheme or "http", "user": unquote(u.username or ""), "base_pass": base,
            "host": u.hostname or "", "port": u.port, "country": (m.group(1).lower() if m else "")}


def session_id(key: str) -> str:
    """상품 키 → IPRoyal session id(영숫자 8자, 결정적). 같은 상품은 늘 같은 IP 세션."""
    return hashlib.sha1(str(key or "").encode("utf-8")).hexdigest()[:8]


def session_lifetime() -> str:
    v = os.getenv("TAOBAO_PROXY_SESSION_LIFETIME", "30m").strip() or "30m"
    return v if re.fullmatch(r"[0-9]+[smhd]", v) else "30m"


def proxy_url(sticky: str = "") -> str:
    """정규화한 프록시 URL. `sticky`(session id)가 있으면 `_session-<id>_lifetime-<lt>`를 붙인다(없으면 회전 모드)."""
    pp = proxy_parts()
    if not pp:
        return ""
    pw = pp["base_pass"] + (f"_session-{sticky}_lifetime-{session_lifetime()}" if sticky else "")
    port = f":{pp['port']}" if pp["port"] else ""
    return f"{pp['scheme']}://{quote(pp['user'], safe='')}:{quote(pw, safe='')}@{pp['host']}{port}"


def masked_proxy(sticky: str = "") -> str:
    """화면·로그용 — 비밀번호는 앞 3자 + 「…」. session id는 그대로."""
    pp = proxy_parts()
    if not pp:
        return "미설정(TAOBAO_PROXY_URL)"
    port = f":{pp['port']}" if pp["port"] else ""
    tail = f" · session {sticky} · lifetime {session_lifetime()}" if sticky else " · 회전(세션 없음)"
    return f"{pp['scheme']}://{pp['user']}:{pp['base_pass'][:3]}…@{pp['host']}{port}{tail}"


def new_sticky() -> str:
    """(옛 호출부 호환) 키 없이 부를 때 — 무작위 8자. 자동 경로는 `session_id(상품 키)`를 쓴다."""
    return "".join(random.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(8))


def proxy_scope() -> str:
    """`TAOBAO_PROXY_SCOPE` — mtop(기본: 핸드셰이크·h5api만) | all(이미지까지, 디버그)."""
    return "all" if os.getenv("TAOBAO_PROXY_SCOPE", "mtop").strip().lower() == "all" else "mtop"


def image_proxies(url: str):
    """이미지 내려받기에 프록시를 쓸지 — SCOPE=all이고 타오바오 이미지일 때만. 기본(mtop)은 None(직결)."""
    if proxy_scope() != "all":
        return None
    host = (re.match(r"https?://([^/]+)", str(url or "")) or [None, ""])[1].lower()
    if not re.search(r"(alicdn|taobao|tmall)\.com$", host):
        return None
    p = proxy_url()
    return {"http": p, "https": p} if p else None


def proxy_label() -> str:
    """화면용 — 자격·호스트는 안 보인다. 설정 여부 · 세션 방식 · 국가 · 범위."""
    pp = proxy_parts()
    if not pp:
        return "미설정(TAOBAO_PROXY_URL)"
    return (f"설정됨 · 상품마다 고정 세션(lifetime {session_lifetime()})"
            + (f" · 국가 {pp['country']}" if pp["country"] else " · 국가 지정 없음") + f" · 범위 {proxy_scope()}")


def _is_proxy(s) -> bool:
    return not isinstance(s, RelaySession) and bool(getattr(s, "proxies", None))


def proxy_error(exc) -> tuple:
    """프록시 연결 실패를 「IP 차단」과 가른다 → `(code, 사유)`. code: proxy_auth(407) · proxy_timeout · proxy_conn."""
    txt = f"{type(exc).__name__}: {exc}"
    try:
        import requests
        is_timeout = isinstance(exc, requests.exceptions.Timeout)
    except Exception:
        is_timeout = False
    if "407" in txt or "Proxy Authentication" in txt:
        return "proxy_auth", "프록시 인증 실패(407) — TAOBAO_PROXY_URL 아이디·비밀번호 확인"
    if is_timeout or "timed out" in txt.lower():
        return "proxy_timeout", "프록시 시간 초과 — 프록시 서버 응답 없음"
    return "proxy_conn", f"프록시 연결 실패 — {type(exc).__name__}"


def bytes_used(s) -> int:
    return int(getattr(s, "_kgp_bytes", 0) or 0)


class NoProxy(RuntimeError):
    pass


def _session(proxy: bool = False, sticky: str = ""):
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://h5.m.taobao.com/", "Accept": "*/*"})
    if proxy:
        p = proxy_url(sticky)
        if not p:
            raise NoProxy("TAOBAO_PROXY_URL 미설정")
        s.trust_env = False                      # 컨테이너 공용 프록시 env를 섞지 않는다 — 이 세션만 주거 프록시
        s.proxies = {"http": p, "https": p}
    return s


def item_id_from(arg: str, s=None) -> tuple:
    arg = str(arg or "").strip()
    if re.fullmatch(r"\d{6,15}", arg):
        return arg, "직접 입력"
    # Z 후속2(오너 2026-10-04 20:39 실측): 공유 문구 통째로 넘기면 InvalidSchema/InvalidURL —
    #   공유 수집과 같은 추출(parse_share_text: 상품 링크 우선 → https?://\S+)로 링크 하나만 뽑는다.
    if not re.match(r"https?://\S+$", arg):
        from src.collectors.share_text import url_from_input
        picked = url_from_input(arg)
        if not picked:
            m = re.search(r"https?://\S+", arg)
            picked = m.group(0) if m else ""
        if not picked:
            return "", "입력에서 링크를 찾지 못했어요(https://… 또는 숫자 상품 ID)"
        arg, pre = picked, f"뽑은 링크 {picked[:60]} · "
    else:
        pre = ""
    m = re.search(r"[?&]id=(\d{6,15})", arg)
    if m:
        return m.group(1), pre + "주소의 id="
    s = s or _session()
    try:
        r = s.get(arg, timeout=15, allow_redirects=True)
        body = r.text[:200000]
    except Exception as exc:                                    # noqa: BLE001
        return "", f"{pre}단축 링크 열기 실패 {type(exc).__name__}"
    m = re.search(r"[?&]id=(\d{6,15})", r.url) or re.search(r"[?&]id=(\d{6,15})", body) \
        or re.search(r"item[_.]?id[\"'=:\s]+(\d{6,15})", body, re.I)
    return (m.group(1) if m else ""), f"{pre}HTTP {r.status_code} · 최종 주소 {r.url[:80]} · 본문 {len(body)}자"


class RelaySession:
    """relay2(서울 IP) 경유 — mkt.php가 돌려주는 Set-Cookie로 쿠키를 손으로 들고 다닌다(`_m_h5_tk` 왕복)."""

    def __init__(self):
        self.jar = {}
        self.cookies = self

    def get(self, name, default=None):                       # requests 쿠키 jar 흉내(`s.cookies.get`)
        return self.jar.get(name, default)

    def request(self, url, params=None, timeout=20):
        from urllib.parse import urlencode
        from src.market_relay import _api_relay_send
        full = url + ("?" + urlencode(params) if params else "")
        hdrs = {"User-Agent": UA, "Referer": "https://h5.m.taobao.com/", "Accept": "*/*"}
        if self.jar:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.jar.items())
        r = _api_relay_send("GET", full, hdrs, None, None, timeout)
        for c in (r.headers or {}).get("Set-Cookie") or []:
            kv = str(c).split(";", 1)[0]
            if "=" in kv:
                k, v = kv.split("=", 1)
                self.jar[k.strip()] = v.strip()
        return r


def _get_url(s, full: str, timeout=20):
    _pace()
    r = s.request(full, timeout=timeout) if isinstance(s, RelaySession) else s.get(full, timeout=timeout)
    # Z3-P: 경유 바이트(요청 줄 + 응답 본문·헤더) — 트라이얼 100MB라 상품당으로 센다
    try:
        hdr = sum(len(str(k)) + len(str(v)) for k, v in (getattr(r, "headers", None) or {}).items())
        body = len(getattr(r, "content", b"") or b"") or len((getattr(r, "text", "") or "").encode("utf-8"))
        s._kgp_bytes = bytes_used(s) + len(full) + 200 + hdr + body
    except Exception:
        pass
    if _is_proxy(s) and getattr(r, "status_code", 0) == 407:
        raise _ProxyAuth("407 Proxy Authentication Required")
    return r


class _ProxyAuth(RuntimeError):
    pass


def x5_handshake_url(body: str, original_url: str) -> str:
    """1차 응답이 x5 핸드셰이크 스크립트면 갈 URL — 브라우저가 만드는 그대로(`…x5referer=` + encodeURIComponent(원 요청 전체 URL)).
    아니면 빈 문자열. 꼬리를 붙이는 판단은 **URL 모양**으로(스크립트가 `+ x5referer`로 잇든 다른 식으로 잇든 같다)."""
    m = _X5_RE.search(str(body or "")[:20000])
    if not m:
        return ""
    url = m.group(1)
    if re.search(r"[?&]x5referer=$", url):
        url += quote(original_url, safe="-_.!~*'()")     # encodeURIComponent와 같은 안전 문자
    return url


def cookie_value(s, name: str) -> str:
    """쿠키통에서 이름으로 — requests 쿠키통은 같은 이름이 두 도메인(.taobao.com · h5api.m.taobao.com)에 있으면
    `.get`이 CookieConflictError를 낸다(Z3-H 후보 3). 이름만 보고 마지막 값을 쓴다."""
    if isinstance(s, RelaySession):
        return str(s.jar.get(name) or "")
    val = ""
    for c in getattr(s.cookies, "__iter__", lambda: iter(()))():
        if getattr(c, "name", "") == name:
            val = c.value
    if not val and hasattr(s.cookies, "get") and not hasattr(s.cookies, "list_domains"):
        val = str(s.cookies.get(name) or "")         # 테스트 대역(dict)
    return val


def _cookie_domains(s) -> list:
    if isinstance(s, RelaySession):
        return [f"{k}(릴레이 쿠키통)" for k in s.jar]
    out = []
    for c in getattr(s.cookies, "__iter__", lambda: iter(()))():
        if hasattr(c, "domain"):
            out.append(f"{c.name}@{c.domain or '?'}{c.path or ''}")
    if not out and isinstance(s.cookies, dict):
        out = [f"{k}(대역)" for k in s.cookies]
    return out


def _set_cookie(s, name: str, value: str) -> None:
    if isinstance(s, RelaySession):
        s.jar[name] = value
    elif hasattr(s.cookies, "set") and hasattr(s.cookies, "list_domains"):
        s.cookies.set(name, value, domain=".taobao.com", path="/")
    else:
        s.cookies[name] = value


def body_cookies(body: str) -> dict:
    """Z3-H 후보 2: 응답 본문 JS가 심는 쿠키 — `document.cookie = "k=v; …"` 전부 + 맨 `x5sec=…` 폴백."""
    b = str(body or "")[:50000]
    out = {k: v.strip() for k, v in _COOKIE_JS.findall(b)}
    if "x5sec" not in out:
        m = _X5SEC_ANY.search(b)
        if m:
            out["x5sec"] = m.group(1)
    return out


def _mask(text: str) -> str:
    """진단용 — 쿠키 값은 글자 수로만(`x5sec=<84자>`). 이름·도메인·경로·나머지 본문은 그대로."""
    t = re.sub(r"\b(x5sec\w*|_m_h5_tk(?:_enc)?|cookie2|t|_tb_token_|cna|isg|l)\s*=\s*([^;,\s\"'&]{4,})",
               lambda m: f"{m.group(1)}=<{len(m.group(2))}자>", str(text or ""))
    return re.sub(r"""(document\.cookie\s*=\s*["']\s*[A-Za-z0-9_]+\s*=\s*)([^;"']{4,})""",
                  lambda m: f"{m.group(1)}<{len(m.group(2))}자>", t)


def _headers_view(r) -> list:
    """응답 헤더 — Set-Cookie는 이름·속성만(값은 글자 수). 릴레이는 Set-Cookie·Location만 돌아온다."""
    out = []
    h = getattr(r, "headers", None) or {}
    try:
        items = list(h.items())
    except Exception:
        items = []
    for k, v in items:
        if str(k).lower() == "set-cookie":
            for c in (v if isinstance(v, list) else [v]):
                out.append("Set-Cookie: " + _mask(str(c))[:200])
        else:
            out.append(f"{k}: {str(v)[:160]}")
    return out[:30]


def _blocked(j: dict, body: str) -> str:
    """punish/captcha(=사람 확인) 사유 한 줄 — 아니면 빈 문자열. RGV587은 서버 IP를 막은 응답."""
    ret = " ".join(str(x) for x in ((j or {}).get("ret") or []))
    url = str(((j or {}).get("data") or {}).get("url") or "") if isinstance((j or {}).get("data"), dict) else ""
    if _PUNISH_RE.search(url) or (not j and _PUNISH_RE.search(str(body or "")[:20000])):
        return "사람 확인(punish/captcha) 요구 — " + (ret[:60] or "슬라이더 페이지")
    if "RGV587" in ret:
        return "접속 차단(RGV587) — " + ret[:60]
    if not j and "RGV587" in str(body or "")[:20000]:          # Z3-B: 본문에 RGV587(JSON 아닌 응답)
        return "접속 차단(RGV587) — 본문"
    return ""


# ── Z3-H2(오너 2026-10-05 17:04 실측: 꼬리 붙임 · GET 200 · 쿠키통 x5secdata@.taobao.com · 「x5sec 미발급」 → 3차 스크립트) ──
#   ① 성공 판정은 이름 하나(x5sec)가 아니라 **x5sec* · _m_h5_tk* 계열 아무거나** 새로 생겼나
#   ② 핸드셰이크 응답 스크립트가 만드는 **jump URL**을 그대로 재현해 그 주소로 재시도(원 URL이 아니라)
#   ③ Z3-B(오너 실측 2026-10-05): 핸드셰이크 본문이 login_jump → 「로그인 요구」(IP 무관 — 집·LTE·주거 프록시 모두 같음).
#      로그인 표지 없이 getdetail이 다시 1단계 스크립트면 「x5_loop」. (rand/uuid로 IP 평판을 점치던 판정은 폐기)
_X5_COOKIE = re.compile(r"^(x5sec\w*|_m_h5_tk\w*)$")


def _ends(u: str, head: int = 110, tail: int = 90) -> str:
    """진단용 긴 주소 — 앞(경로)과 뒤(이어 붙인 파라미터)를 둘 다 보인다."""
    u = str(u or "")
    return u if len(u) <= head + tail + 1 else u[:head] + "…" + u[-tail:]


def x5_cookie_names(s) -> list:
    """쿠키통에서 x5sec*·_m_h5_tk* 계열 이름(값 없이)."""
    if isinstance(s, RelaySession):
        names = list(s.jar)
    else:
        try:
            names = [c.name for c in s.cookies] if not isinstance(s.cookies, dict) else list(s.cookies)
        except Exception:
            names = []
    return sorted({n for n in names if _X5_COOKIE.match(str(n))})


def x5_ids(url: str) -> tuple:
    """set_x5referer URL의 (rand, uuid) — 비교용."""
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(str(url or "")).query)
    return (q.get("rand", [""])[0], q.get("uuid", [""])[0])


_JS_STR = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''


def _js_unquote(tok: str) -> str:
    body = tok[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)


def _split_plus(expr: str) -> list:
    """`a + "b" + c` → 조각(문자열 리터럴 안의 +는 안 자른다)."""
    out, cur, i = [], "", 0
    while i < len(expr):
        m = re.match(_JS_STR, expr[i:])
        if m:
            cur += m.group(0)
            i += len(m.group(0))
            continue
        ch = expr[i]
        if ch == "+":
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur.strip())
    return [x for x in out if x]


def jump_url(body: str, page_url: str) -> str:
    """핸드셰이크 응답 스크립트가 이동하는 주소를 **문자열 이어 붙이기만** 재현한다 — 리터럴 · var 값 ·
    location.href(=이 페이지 주소) · 쿼리의 x5referer 값 · encodeURIComponent/decodeURIComponent.
    그 밖의 계산이 섞이면 재현하지 않는다(빈 문자열 — 추측 금지, 진단 본문으로 사람이 본다)."""
    from urllib.parse import unquote, urlparse
    b = str(body or "")[:20000]
    env = {"location.href": page_url, "window.location.href": page_url, "document.URL": page_url,
           "location.search": "?" + urlparse(page_url).query}
    raw = re.search(r"[?&]x5referer=([^&#]*)", page_url)
    if raw:                       # 브라우저 스크립트의 x5referer 변수 = 쿼리의 **날 값**(인코딩 그대로) — 한 번만 풀린다
        env["x5referer"] = raw.group(1)

    def ev(expr: str):
        parts = _split_plus(expr.strip().rstrip(";"))
        if not parts:
            return None
        out = ""
        for p in parts:
            p = p.strip()
            m = re.fullmatch(r"(encodeURIComponent|decodeURIComponent|unescape|escape)\((.+)\)", p, re.S)
            if m:
                inner = ev(m.group(2))
                if inner is None:
                    return None
                out += quote(inner, safe="-_.!~*'()") if m.group(1) in ("encodeURIComponent", "escape") else unquote(inner)
            elif re.fullmatch(_JS_STR, p, re.S):
                out += _js_unquote(p)
            elif p in env:
                out += env[p]
            else:
                return None
        return out
    for m in re.finditer(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)", b):
        v = ev(m.group(2))
        if v is not None:
            env[m.group(1)] = v
    for m in re.finditer(r"(?:window\.)?location(?:\.href)?\s*=\s*([^;\n]+)|(?:window\.)?location\.(?:replace|assign)\(\s*([^;\n]+?)\s*\)\s*;?", b):
        v = ev(m.group(1) or m.group(2))
        if v and v.startswith("http") and "_____tmd_____/page/set_x5referer" not in v:
            return v
    return ""


def _kind(state: str, reason: str) -> str:
    """집계용 갈래 — ok · login_required · rgv587 · x5_loop · punish · empty(JSON 아님·빈 응답) · proxy_* · error."""
    if state == "ok":
        return "ok"
    r = str(reason or "")
    for pre, k in (("프록시 인증 실패", "proxy_auth"), ("프록시 시간 초과", "proxy_timeout"), ("프록시 연결 실패", "proxy_conn"),
                   ("로그인 요구", "login_required"), ("x5 루프", "x5_loop")):
        if r.startswith(pre):
            return k
    if r.startswith("사람 확인"):
        return "punish"
    if "RGV587" in r:
        return "rgv587"
    if "JSON 아닌" in r or "비었" in r or "x5sec" in r or "스크립트 응답" in r:
        return "empty"
    return "error"


# Z3-B(오너 2026-10-05 실측 — 프록시·LTE·집 PC 모두): 987자 스크립트가
#   `login_jump = href.replace("set_x5referer","login_jump"); location = loginUrl + uuid + "&redirectURL=" + login_jump`
#   → 익명 세션 거부. 표지는 오너가 지정한 세 개만(추측으로 넓히지 않는다).
LOGIN_MARKERS = ("login_jump", "login.m.taobao.com/login.htm", "login.taobao.com/member/login.jhtml")


def login_required(body: str, j=None) -> bool:
    url = ""
    if isinstance(j, dict) and isinstance(j.get("data"), dict):
        url = str(j["data"].get("url") or "")
    text = str(body or "")[:20000] + " " + url
    return any(m in text for m in LOGIN_MARKERS)


LOGIN_WHY = "로그인 요구 — 익명 수집 불가(IP 무관). 외부 API 또는 로그인 쿠키 경로 필요."
X5_LOOP_WHY = "x5 루프 — 핸드셰이크 뒤에도 getdetail이 다시 1단계 리다이렉트 스크립트(로그인 표지는 없음)"


def mtop_ex(s, api: str, data: dict, v: str = "6.0") -> dict:
    """`{json, log, state, kind, reason, handshakes}` — state: ok | blocked(→ (c) 수동) | error.
    API 호출 최대 3회(핸드셰이크 GET은 별도, 최대 2번). `handshakes`는 진단용(쿠키 값은 글자 수만)."""
    payload = json.dumps(data, separators=(",", ":"))
    log: list = []
    hs_diag: list = []
    base = f"https://h5api.m.taobao.com/h5/{api}/{v}/"
    jump = ""                     # Z3-H2: 핸드셰이크 스크립트가 보내는 주소 — 있으면 다음 시도는 그리로
    # Z3-P 판정 다섯 단계(진단): ① RGV587 없음 ② set_x5referer 스크립트 ③ x5secdata 획득 ④ 로그인 요구 없음 ⑤ 상세 JSON
    stages = {"rgv587": False, "script": False, "x5": False, "login": False, "detail": False}

    def done(state, reason, j=None):
        if j is not None and state == "ok":
            stages["detail"] = True
        return {"json": j, "log": log, "state": state, "kind": _kind(state, reason), "reason": reason, "handshakes": hs_diag,
                "stages": dict(stages), "bytes": bytes_used(s)}

    def req_fail(exc, what):
        if _is_proxy(s) or isinstance(exc, _ProxyAuth):
            code, why = proxy_error(exc)
            log.append(f"{what}: {why}")
            return done("error", why)
        log.append(f"{what}: {type(exc).__name__}")
        return done("error", f"요청 실패 {type(exc).__name__}")
    for attempt in range(1, MAX_TRIES + 1):
        tk = cookie_value(s, "_m_h5_tk")
        t = str(int(time.time() * 1000))
        sign = hashlib.md5(f"{tk.split('_')[0]}&{t}&{APPKEY}&{payload}".encode()).hexdigest()
        params = {"jsv": "2.7.2", "appKey": APPKEY, "t": t, "sign": sign, "api": api, "v": v,
                  "type": "json", "dataType": "json", "data": payload}
        full = base + "?" + urlencode(params)
        target, via_jump = (jump, True) if jump else (full, False)
        jump = ""
        carried = x5_cookie_names(s)
        try:
            r = _get_url(s, target)
        except Exception as exc:                                # noqa: BLE001
            return req_fail(exc, f"{attempt}차")
        body = r.text or ""
        try:
            j = r.json()
        except Exception:
            j = None
        if via_jump or carried:
            log.append(f"{attempt}차 요청: {'jump URL' if via_jump else '원 URL(재서명)'} · 실은 x5 계열 쿠키 {', '.join(carried) or '없음'}")
        if j is None:
            hs = x5_handshake_url(body, full)
            ids = x5_ids(hs) if hs else None
            if hs:
                stages["script"] = True
            if hs and len(hs_diag) < 2:
                before = set(x5_cookie_names(s))
                try:
                    hr = _get_url(s, hs)
                except Exception as exc:                        # noqa: BLE001
                    if _is_proxy(s) or isinstance(exc, _ProxyAuth):
                        return req_fail(exc, f"{attempt}차 x5 핸드셰이크 GET")
                    log.append(f"{attempt}차: x5 핸드셰이크 GET 실패 {type(exc).__name__}")
                    return done("error", "x5 핸드셰이크 GET 실패")
                hbody = hr.text or ""
                from_hdr = sorted(set(x5_cookie_names(s)) - before)
                planted = []
                for k, val in body_cookies(hbody).items():      # 본문 JS가 심는 쿠키
                    if not cookie_value(s, k):
                        _set_cookie(s, k, val)
                        planted.append(k)
                got = sorted(set(x5_cookie_names(s)) - before)
                if any(n.startswith("x5sec") for n in x5_cookie_names(s)):
                    stages["x5"] = True
                src = "헤더" if from_hdr else ("본문 JS" if got else "")
                tail = "x5referer=" in hs and not hs.endswith("x5referer=")
                jump = jump_url(hbody, hs)
                hs_diag.append({"url": _ends(hs), "tail": tail, "url_len": len(hs),
                                "status": hr.status_code, "headers": _headers_view(hr),
                                "body_head": _mask(hbody[:4000]), "body_len": len(hbody),
                                "planted": planted, "cookies": _cookie_domains(s), "got": got,
                                "jump": _ends(jump),
                                "rand_uuid": "/".join(x or "—" for x in ids) if ids else ""})
                log.append(f"{attempt}차: HTTP {r.status_code} · x5 핸드셰이크 스크립트 → set_x5referer GET HTTP {hr.status_code}"
                           f" · x5referer 꼬리 {'붙임' if tail else '없음'}"
                           f" · x5 계열 쿠키 {(', '.join(got) + '(' + src + ')') if got else '새로 받은 것 없음'}"
                           f" · jump URL {'재현함 → 그 주소로 재시도' if jump else '재현 못 함(원 URL 재시도)'}")
                loc = str(((getattr(hr, "headers", None) or {}).get("Location")) or "")
                if login_required(hbody) or login_required(loc):
                    stages["login"] = True
                    log.append(f"{attempt}차: 핸드셰이크 본문이 로그인 요구(login_jump) — 재시도해도 같다(IP 무관), 여기서 멈춤")
                    return done("blocked", LOGIN_WHY)
                if not got and (_PUNISH_RE.search(loc) or _PUNISH_RE.search(hbody[:20000])):
                    return done("blocked", "사람 확인(punish/captcha) 요구 — x5 핸드셰이크가 슬라이더 페이지로 보냄")
                continue
            if login_required(body):
                stages["login"] = True
                log.append(f"{attempt}차: HTTP {r.status_code} · 로그인 요구(login_jump)")
                return done("blocked", LOGIN_WHY)
            if "RGV587" in body[:20000]:
                stages["rgv587"] = True
            why = _blocked(None, body)
            log.append(f"{attempt}차: HTTP {r.status_code} · JSON 아님 · 앞 {body[:100]!r}")
            if why:
                return done("blocked", why)
            if hs:
                log.append("판정: x5_loop — 핸드셰이크 뒤 getdetail이 다시 1단계 스크립트")
                return done("error", X5_LOOP_WHY)
            return done("error", "JSON 아닌 응답(핸드셰이크 스크립트도 아님)")
        ret = j.get("ret") or []
        log.append(f"{attempt}차: HTTP {r.status_code} · ret={ret[:2]} · 토큰 쿠키 {'있음' if tk else '없음'}")
        if any("RGV587" in str(x) for x in ret):
            stages["rgv587"] = True
        if login_required("", j):
            stages["login"] = True
            return done("blocked", LOGIN_WHY)
        if any("SUCCESS" in str(x) for x in ret):
            return done("ok", "", j)
        why = _blocked(j, body)
        if why:
            return done("blocked", why)
        if not any("TOKEN" in str(x) for x in ret):
            return done("error", "응답 코드 " + " ".join(str(x) for x in ret)[:80], j)
    return done("error", f"{MAX_TRIES}회 안에 토큰 왕복을 못 끝냄")


def mtop(s, api: str, data: dict, v: str = "6.0") -> tuple:
    r = mtop_ex(s, api, data, v)
    return (r["json"] if r["state"] == "ok" else None), r["log"]


def summarize(j: dict) -> dict:
    d = (j or {}).get("data") or {}
    item = d.get("item") or {}
    sku = d.get("skuBase") or {}
    props = sku.get("props") or []
    price = ""
    for raw in ((d.get("apiStack") or [{}])[0].get("value") if d.get("apiStack") else None, d.get("mockData")):
        try:
            price = price or (((json.loads(raw or "{}").get("price") or {}).get("price") or {}).get("priceText")) or ""
        except Exception:
            pass
    return {"title_len": len(str(item.get("title") or "")), "title": str(item.get("title") or "")[:40], "price": price,
            "gallery": len(item.get("images") or []), "skus": len(sku.get("skus") or []), "axes": len(props),
            "values": sum(len(p.get("values") or []) for p in props)}


VIAS = {"direct": "직결(이 서버)", "relay": "relay2(서울)", "proxy": "프록시(한국 주거)"}


def norm_via(via: str) -> str:
    v = str(via or "").strip().lower()
    return "relay" if v == "relay2" else v


def session_for(via: str, sticky: str = ""):
    """mtop 경로 전용 세션 — via=proxy일 때만 주거 프록시를 싣는다(`sticky` = 이 건의 IPRoyal 세션 id)."""
    via = norm_via(via)
    if via == "relay":
        return RelaySession()
    return _session(proxy=(via == "proxy"), sticky=sticky)


def resolver_session(via: str):
    """단축 링크(e.tb.cn) 펴기용 — 기본은 **직결**(트래픽 절약, h5api가 아니라 프록시 범위 밖). SCOPE=all이면 프록시."""
    if norm_via(via) == "proxy" and proxy_scope() == "all":
        return _session(proxy=True)
    return _session()


def exit_ip(sticky: str = "") -> dict:
    """Z3-P 진단: 이 세션의 프록시 출구 IP(icanhazip, 수십 바이트) + 국가(직결로 ipinfo — 프록시 바이트 0)."""
    try:
        s = _session(proxy=True, sticky=sticky)
    except NoProxy as exc:
        return {"ok": False, "why": str(exc)}
    try:
        r = s.get("https://ipv4.icanhazip.com", timeout=15)
        ip = (r.text or "").strip()[:45]
        nbytes = len(r.content or b"") + 300
    except Exception as exc:                                    # noqa: BLE001
        code, why = proxy_error(exc)
        return {"ok": False, "code": code, "why": why}
    country = ""
    try:
        import requests
        c = requests.get(f"https://ipinfo.io/{ip}/country", timeout=8)
        country = (c.text or "").strip()[:2] if c.status_code == 200 else ""
    except Exception:
        country = ""
    return {"ok": bool(ip), "ip": ip, "country": country or "확인 못 함", "bytes": nbytes}


def exit_line(via: str, sticky: str = "") -> dict:
    """Z3-B: 경로마다 출구 IP 한 줄 — 비교용. `{ok, ip, country, how, bytes}`.
    proxy=icanhazip(프록시 경유 실측) · direct=icanhazip(이 서버 직결 실측) ·
    relay=릴레이는 허용 호스트(타오바오)만 통과라 icanhazip 불가 → 설정·DNS에서 파생한 릴레이 서버 주소(실측 아님이라고 적는다)."""
    via = norm_via(via)
    if via == "proxy":
        e = exit_ip(sticky)
        return {**e, "how": "프록시 경유 icanhazip 실측"}
    if via == "relay":
        try:
            from src.market_relay import relay_outbound_ip
            ip = relay_outbound_ip()
        except Exception:
            ip = ""
        return {"ok": bool(ip), "ip": ip or "확인 못 함", "country": "", "bytes": 0,
                "how": "relay2 서버 주소(설정·DNS 파생 — 실측 아님, 릴레이가 icanhazip을 안 통과시킴)"}
    if os.getenv("TAOBAO_EXIT_IP_CHECK", "1").strip() == "0":
        return {"ok": False, "ip": "", "country": "", "bytes": 0, "how": "직결 출구 확인 꺼짐(TAOBAO_EXIT_IP_CHECK=0)"}
    try:
        import requests
        r = requests.get("https://ipv4.icanhazip.com", timeout=8)
        ip = (r.text or "").strip()[:45] if r.status_code == 200 else ""
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "ip": "", "country": "", "bytes": 0, "how": f"직결 icanhazip 실패 {type(exc).__name__}"}
    return {"ok": bool(ip), "ip": ip or "확인 못 함", "country": "", "bytes": 0, "how": "이 서버 직결 icanhazip 실측"}


def verdict(stages: dict) -> list:
    """다섯 단계 ○/× — 진단 화면 판정 줄."""
    st = stages or {}
    return [("① RGV587 없음", not st.get("rgv587")),
            ("② set_x5referer 스크립트 받음", bool(st.get("script"))),
            ("③ x5secdata 획득", bool(st.get("x5"))),
            ("④ 로그인 요구 없음", not st.get("login")),
            ("⑤ getdetail JSON에 가격·옵션", bool(st.get("detail")))]


def probe(arg: str, via: str = "direct") -> dict:
    """`via`: direct · relay(relay2 서울 IP — mkt.php 새 판) · proxy(`TAOBAO_PROXY_URL`, 상품마다 고정 세션)."""
    via = norm_via(via)
    out = {"input": arg[:80], "item_id": "", "how": "", "log": [], "detail": None, "desc_images": None,
           "via": VIAS.get(via, via), "state": "", "reason": "", "kind": "", "handshakes": [],
           "stages": {}, "bytes": 0, "session": "", "proxy": "", "exit": None}
    if via == "proxy" and not proxy_parts():
        out.update(how="프록시 미설정", state="error", kind="proxy_unset", reason="프록시 미설정 — TAOBAO_PROXY_URL")
        return out
    # 단축 링크(e.tb.cn)는 h5api가 아니다 → 직결로 편다(SCOPE=all이면 프록시).
    iid, how = item_id_from(arg, resolver_session(via))
    out.update(item_id=iid, how=how)
    if not iid:
        return out
    sticky = session_id(iid) if via == "proxy" else ""
    out["exit"] = exit_line(via, sticky)                       # Z3-B: 경로마다 출구 IP(비교용)
    if via == "proxy":
        out["session"], out["proxy"] = sticky, masked_proxy(sticky)
        if not out["exit"].get("ok"):
            out.update(state="error", kind=out["exit"].get("code") or "proxy_conn", reason=out["exit"].get("why") or "출구 IP 확인 실패")
            return out
    s = session_for(via, sticky=sticky)
    r = mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": iid})
    out["log"] += r["log"]
    out["state"], out["reason"], out["kind"], out["handshakes"] = r["state"], r["reason"], r["kind"], r["handshakes"]
    out["stages"] = r.get("stages") or {}
    out["detail"] = summarize(r["json"]) if r["state"] == "ok" else None
    if out["detail"] is not None:
        out["stages"]["detail"] = bool(out["detail"].get("price") or out["detail"].get("skus") or out["detail"].get("axes"))
    if r["state"] == "ok":
        out["raw_detail"] = r["json"]
        d = mtop_ex(s, "mtop.taobao.detail.getdesc", {"id": iid, "type": "1"})
        out["log"] += ["상세 " + x for x in d["log"]]
        if d["json"]:
            out["desc_images"] = len(desc_images(d["json"]))
    out["bytes"] = bytes_used(s) + ((out.get("exit") or {}).get("bytes") or 0)
    if via == "proxy":
        import logging as _lg
        _lg.getLogger(__name__).info("[Z3 프록시] 진단 상품=%s session=%s 바이트=%d 결과=%s", iid, sticky, out["bytes"], out["kind"])
    return out


def desc_images(dj: dict) -> list:
    seen, out = set(), []
    for u in _DESC_IMG.findall(json.dumps((dj or {}).get("data") or {}, ensure_ascii=False)):
        u = "https:" + u if u.startswith("//") else u
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _abs(u: str) -> str:
    u = str(u or "")
    return "https:" + u if u.startswith("//") else u


def enrich_payload(dj: dict, desc: dict | None = None) -> dict:
    """getdetail(+getdesc) JSON → `/enrich` 병합이 받는 모양(확장이 보내는 것과 같은 키)."""
    d = (dj or {}).get("data") or {}
    item = d.get("item") or {}
    sku = d.get("skuBase") or {}
    stack = {}
    for raw in ((d.get("apiStack") or [{}])[0].get("value") if d.get("apiStack") else None, d.get("mockData")):
        try:
            v = json.loads(raw or "{}")
            if v:
                stack = v
                break
        except Exception:
            continue
    props = sku.get("props") or []
    names = {}
    options = []
    for p in props:
        vals = []
        for val in p.get("values") or []:
            names[f"{p.get('pid')}:{val.get('vid')}"] = str(val.get("name") or "")
            vals.append(str(val.get("name") or ""))
        options.append({"name": str(p.get("name") or ""), "values": vals})
    s2i = ((stack.get("skuCore") or {}).get("sku2info") or {})
    skus = []
    for k in sku.get("skus") or []:
        spec = [names.get(pv, "") for pv in str(k.get("propPath") or "").split(";") if pv]
        info = s2i.get(str(k.get("skuId"))) or {}
        skus.append({"spec": spec, "price": str(((info.get("price") or {}).get("priceText")) or ""),
                     "stock": info.get("quantity"), "sku_id": str(k.get("skuId") or "")})
    price = str(((stack.get("price") or {}).get("price") or {}).get("priceText") or "")
    m = re.search(r"\d+(?:\.\d+)?", price)
    return {"title": str(item.get("title") or ""), "images": [_abs(u) for u in item.get("images") or []],
            "options": options, "skus": skus, "price": m.group(0) if m else "", "currency": "CNY",
            "detail_images": desc_images(desc) if desc else [], "source_path": "mtop"}


def fetch(item_id: str, via: str) -> dict:
    """자동 경로 한 건 — `{state: ok|blocked|error, kind, reason, payload, log, raw, bytes, session}`.
    프록시면 이 상품 전용 고정 세션(session_id(상품번호)) — 핸드셰이크·getdetail·getdesc 전부 같은 IP."""
    via = norm_via(via)
    sticky = session_id(item_id) if via == "proxy" else ""
    if via == "proxy" and not proxy_parts():
        return {"state": "error", "kind": "proxy_unset", "reason": "프록시 미설정 — TAOBAO_PROXY_URL", "payload": None,
                "log": [], "bytes": 0, "session": ""}
    try:
        s = session_for(via, sticky=sticky)
    except NoProxy:
        return {"state": "error", "kind": "proxy_unset", "reason": "프록시 미설정 — TAOBAO_PROXY_URL", "payload": None,
                "log": [], "bytes": 0, "session": ""}
    r = mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": item_id})
    if r["state"] != "ok":
        return {"state": r["state"], "kind": r["kind"], "reason": r["reason"], "payload": None, "log": r["log"],
                "bytes": bytes_used(s), "session": sticky}
    d = mtop_ex(s, "mtop.taobao.detail.getdesc", {"id": item_id, "type": "1"})
    payload = enrich_payload(r["json"], d["json"] if d["state"] == "ok" else None)
    if not (payload["title"] and payload["images"]):
        return {"state": "error", "kind": "empty", "reason": "응답은 왔지만 제목·사진이 비었어요", "payload": None,
                "log": r["log"] + d["log"], "bytes": bytes_used(s), "session": sticky}
    return {"state": "ok", "kind": "ok", "reason": "", "payload": payload, "log": r["log"] + d["log"], "raw": r["json"],
            "bytes": bytes_used(s), "session": sticky}
