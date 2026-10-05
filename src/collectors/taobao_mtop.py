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
    t = re.sub(r"\b(x5sec|_m_h5_tk(?:_enc)?|cookie2|t|_tb_token_|cna|isg|l)\s*=\s*([^;,\s\"']{4,})",
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


def _kind(state: str, reason: str) -> str:
    """집계용 갈래 — ok · punish · rgv587 · empty(JSON 아님·빈 응답) · error."""
    if state == "ok":
        return "ok"
    r = str(reason or "")
    if r.startswith("사람 확인"):
        return "punish"
    if "RGV587" in r:
        return "rgv587"
    if "JSON 아닌" in r or "비었" in r or "x5sec" in r:
        return "empty"
    return "error"


def mtop_ex(s, api: str, data: dict, v: str = "6.0") -> dict:
    """`{json, log, state, kind, reason, handshakes}` — state: ok | blocked(→ (c) 수동) | error.
    API 호출 최대 3회(핸드셰이크 GET은 별도, 최대 2번). `handshakes`는 진단용(쿠키 값은 글자 수만)."""
    payload = json.dumps(data, separators=(",", ":"))
    log: list = []
    hs_diag: list = []
    base = f"https://h5api.m.taobao.com/h5/{api}/{v}/"

    def done(state, reason, j=None):
        return {"json": j, "log": log, "state": state, "kind": _kind(state, reason), "reason": reason, "handshakes": hs_diag}
    for attempt in range(1, MAX_TRIES + 1):
        tk = cookie_value(s, "_m_h5_tk")
        t = str(int(time.time() * 1000))
        sign = hashlib.md5(f"{tk.split('_')[0]}&{t}&{APPKEY}&{payload}".encode()).hexdigest()
        params = {"jsv": "2.7.2", "appKey": APPKEY, "t": t, "sign": sign, "api": api, "v": v,
                  "type": "json", "dataType": "json", "data": payload}
        full = base + "?" + urlencode(params)
        try:
            r = _get_url(s, full)
        except Exception as exc:                                # noqa: BLE001
            log.append(f"{attempt}차: {type(exc).__name__}")
            return done("error", f"요청 실패 {type(exc).__name__}")
        body = r.text or ""
        try:
            j = r.json()
        except Exception:
            j = None
        if j is None:
            hs = x5_handshake_url(body, full)
            if hs and len(hs_diag) < 2:
                try:
                    hr = _get_url(s, hs)
                except Exception as exc:                        # noqa: BLE001
                    log.append(f"{attempt}차: x5 핸드셰이크 GET 실패 {type(exc).__name__}")
                    return done("error", "x5 핸드셰이크 GET 실패")
                hbody = hr.text or ""
                from_hdr = bool(cookie_value(s, "x5sec"))
                planted = []
                for k, val in body_cookies(hbody).items():      # 후보 2: 본문 JS가 심는 쿠키
                    if not cookie_value(s, k):
                        _set_cookie(s, k, val)
                        planted.append(k)
                have = bool(cookie_value(s, "x5sec"))
                src = "헤더" if from_hdr else ("본문 JS" if have else "")
                tail = "x5referer=" in hs and not hs.endswith("x5referer=")
                hs_diag.append({"url": hs[:180] + ("…" if len(hs) > 180 else ""), "tail": tail, "url_len": len(hs),
                                "status": hr.status_code, "headers": _headers_view(hr),
                                "body_head": _mask(hbody[:500]), "body_len": len(hbody),
                                "planted": planted, "cookies": _cookie_domains(s)})
                log.append(f"{attempt}차: HTTP {r.status_code} · x5 핸드셰이크 스크립트 → set_x5referer GET HTTP {hr.status_code}"
                           f" · x5referer 꼬리 {'붙임' if tail else '없음'} · x5sec 쿠키 {('받음(' + src + ')') if have else '없음'}")
                # 핸드셰이크가 쿠키 대신 사람 확인(슬라이더) 쪽으로 보내면 — 두드려 봐야 같다 → (c) 수동
                loc = str(((getattr(hr, "headers", None) or {}).get("Location")) or "")
                if not have and (_PUNISH_RE.search(loc) or _PUNISH_RE.search(hbody[:20000])):
                    return done("blocked", "사람 확인(punish/captcha) 요구 — x5 핸드셰이크가 슬라이더 페이지로 보냄")
                continue
            why = _blocked(None, body)
            log.append(f"{attempt}차: HTTP {r.status_code} · JSON 아님 · 앞 {body[:100]!r}")
            if why:
                return done("blocked", why)
            if hs:
                return done("error", "x5 핸드셰이크를 2번 했는데도 스크립트 응답(x5sec 미발급) — 진단의 핸드셰이크 헤더·본문 참고")
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
