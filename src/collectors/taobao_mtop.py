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


_STICKY_RE = re.compile(r"(_session-)([A-Za-z0-9]+)")


def proxy_url(sticky: str = "") -> str:
    """`TAOBAO_PROXY_URL`. Z3-P(오너 2026-10-05): IPRoyal 주거 sticky — 비밀번호의 `_session-<id>`를 **상품 1건마다** 새 id로
    바꿔 그 건 안에선 같은 IP, 건이 바뀌면 다른 IP. `_session-`이 없으면 그대로 쓴다."""
    p = os.getenv("TAOBAO_PROXY_URL", "").strip()
    if p and sticky:
        p = _STICKY_RE.sub(lambda m: m.group(1) + sticky, p, count=1)
    return p


def new_sticky() -> str:
    return "".join(random.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(8))


def proxy_label() -> str:
    """화면용 — 자격(user:pass)·호스트는 절대 안 보인다. 설정 여부와 sticky 교체 여부만."""
    p = proxy_url()
    if not p:
        return "미설정(TAOBAO_PROXY_URL)"
    return "설정됨 · 건마다 sticky 세션 교체" if _STICKY_RE.search(p) else "설정됨 · sticky 표기 없음(그대로 사용)"


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
    return s.request(full, timeout=timeout) if isinstance(s, RelaySession) else s.get(full, timeout=timeout)


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
    return ""


# ── Z3-H2(오너 2026-10-05 17:04 실측: 꼬리 붙임 · GET 200 · 쿠키통 x5secdata@.taobao.com · 「x5sec 미발급」 → 3차 스크립트) ──
#   ① 성공 판정은 이름 하나(x5sec)가 아니라 **x5sec* · _m_h5_tk* 계열 아무거나** 새로 생겼나
#   ② 핸드셰이크 응답 스크립트가 만드는 **jump URL**을 그대로 재현해 그 주소로 재시도(원 URL이 아니라)
#   ③ 그래도 스크립트면 1차·3차 핸드셰이크 URL의 rand/uuid 비교 — 같으면 쿠키 미반영, 다르면 IP 평판
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
    """집계용 갈래 — ok · punish · rgv587 · empty(JSON 아님·빈 응답) · error."""
    if state == "ok":
        return "ok"
    r = str(reason or "")
    if r.startswith("사람 확인"):
        return "punish"
    if "RGV587" in r:
        return "rgv587"
    if "JSON 아닌" in r or "비었" in r or "x5sec" in r or "스크립트 응답" in r:
        return "empty"
    return "error"


def mtop_ex(s, api: str, data: dict, v: str = "6.0") -> dict:
    """`{json, log, state, kind, reason, handshakes}` — state: ok | blocked(→ (c) 수동) | error.
    API 호출 최대 3회(핸드셰이크 GET은 별도, 최대 2번). `handshakes`는 진단용(쿠키 값은 글자 수만)."""
    payload = json.dumps(data, separators=(",", ":"))
    log: list = []
    hs_diag: list = []
    base = f"https://h5api.m.taobao.com/h5/{api}/{v}/"
    jump = ""                     # Z3-H2: 핸드셰이크 스크립트가 보내는 주소 — 있으면 다음 시도는 그리로
    first_ids = None

    def done(state, reason, j=None):
        return {"json": j, "log": log, "state": state, "kind": _kind(state, reason), "reason": reason, "handshakes": hs_diag}
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
            log.append(f"{attempt}차: {type(exc).__name__}")
            return done("error", f"요청 실패 {type(exc).__name__}")
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
            if ids and first_ids is None:
                first_ids = ids
            if hs and len(hs_diag) < 2:
                before = set(x5_cookie_names(s))
                try:
                    hr = _get_url(s, hs)
                except Exception as exc:                        # noqa: BLE001
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
                if not got and (_PUNISH_RE.search(loc) or _PUNISH_RE.search(hbody[:20000])):
                    return done("blocked", "사람 확인(punish/captcha) 요구 — x5 핸드셰이크가 슬라이더 페이지로 보냄")
                continue
            why = _blocked(None, body)
            log.append(f"{attempt}차: HTTP {r.status_code} · JSON 아님 · 앞 {body[:100]!r}")
            if why:
                return done("blocked", why)
            if hs:
                # ③ 1차와 지금의 rand/uuid — 같으면 우리 쿠키가 반영 안 됨, 다르면 서버가 새로 막은 것(IP 평판)
                same = (ids == first_ids) if (ids and first_ids) else None
                verdict = ("rand/uuid 1차와 같음 → 쿠키 미반영(재시도에 x5 쿠키가 안 먹음)" if same
                           else "rand/uuid 1차와 다름 → 새로 발급 = IP 평판(이 IP는 계속 막힘)" if same is False
                           else "rand/uuid 비교 불가(핸드셰이크 URL에 없음)")
                log.append(f"판정: {verdict} · 1차 {'/'.join(first_ids or ('—', '—'))} · 지금 {'/'.join(ids or ('—', '—'))}")
                return done("error", f"x5 핸드셰이크 2번 뒤에도 스크립트 응답 — {verdict}")
            return done("error", "JSON 아닌 응답(핸드셰이크 스크립트도 아님)")
        ret = j.get("ret") or []
        log.append(f"{attempt}차: HTTP {r.status_code} · ret={ret[:2]} · 토큰 쿠키 {'있음' if tk else '없음'}")
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


def session_for(via: str, sticky: str = ""):
    """mtop 경로 전용 세션 — via=proxy일 때만 주거 프록시를 싣는다(`sticky` = 이 건의 IPRoyal 세션 id)."""
    if via == "relay":
        return RelaySession()
    return _session(proxy=(via == "proxy"), sticky=sticky)


def probe(arg: str, via: str = "direct") -> dict:
    """`via`: direct · relay(relay2 서울 IP — mkt.php 새 판) · proxy(`TAOBAO_PROXY_URL`)."""
    out = {"input": arg[:80], "item_id": "", "how": "", "log": [], "detail": None, "desc_images": None,
           "via": VIAS.get(via, via), "state": "", "reason": "", "kind": "", "handshakes": []}
    try:
        s = session_for(via, sticky=new_sticky() if via == "proxy" else "")
    except NoProxy as exc:
        out.update(how=str(exc), state="error", reason="프록시 미설정 — TAOBAO_PROXY_URL")
        return out
    # 단축 링크(e.tb.cn)는 relay 허용 밖 → 직결로 편다. 프록시면 프록시 세션으로.
    iid, how = item_id_from(arg, s if not isinstance(s, RelaySession) else _session())
    out.update(item_id=iid, how=how)
    if not iid:
        return out
    r = mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": iid})
    out["log"] += r["log"]
    out["state"], out["reason"], out["kind"], out["handshakes"] = r["state"], r["reason"], r["kind"], r["handshakes"]
    out["detail"] = summarize(r["json"]) if r["state"] == "ok" else None
    if r["state"] != "ok":
        return out
    out["raw_detail"] = r["json"]
    d = mtop_ex(s, "mtop.taobao.detail.getdesc", {"id": iid, "type": "1"})
    out["log"] += ["상세 " + x for x in d["log"]]
    if d["json"]:
        out["desc_images"] = len(desc_images(d["json"]))
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
    """자동 경로 한 건 — `{state: ok|blocked|error, kind, reason, payload, log, raw}`. 프록시면 이 건 전용 sticky 세션."""
    try:
        s = session_for(via, sticky=new_sticky() if via == "proxy" else "")
    except NoProxy:
        return {"state": "error", "kind": "error", "reason": "프록시 미설정 — TAOBAO_PROXY_URL", "payload": None, "log": []}
    r = mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": item_id})
    if r["state"] != "ok":
        return {"state": r["state"], "kind": r["kind"], "reason": r["reason"], "payload": None, "log": r["log"]}
    d = mtop_ex(s, "mtop.taobao.detail.getdesc", {"id": item_id, "type": "1"})
    payload = enrich_payload(r["json"], d["json"] if d["state"] == "ok" else None)
    if not (payload["title"] and payload["images"]):
        return {"state": "error", "kind": "empty", "reason": "응답은 왔지만 제목·사진이 비었어요", "payload": None,
                "log": r["log"] + d["log"]}
    return {"state": "ok", "kind": "ok", "reason": "", "payload": payload, "log": r["log"] + d["log"], "raw": r["json"]}
