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
_X5_RE = re.compile(r'window\.location\.href\s*=\s*"([^"]*_____tmd_____/page/set_x5referer[^"]*)"\s*(\+\s*x5referer)?')
_PUNISH_RE = re.compile(r"_____tmd_____/(?:punish|verify)|captcha|nocaptcha|baxia", re.I)
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


def proxy_url() -> str:
    return os.getenv("TAOBAO_PROXY_URL", "").strip()


def proxy_label() -> str:
    """화면용 — 자격(user:pass)은 절대 안 보인다. 호스트도 숨기고 설정 여부만."""
    return "설정됨" if proxy_url() else "미설정(TAOBAO_PROXY_URL)"


class NoProxy(RuntimeError):
    pass


def _session(proxy: bool = False):
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://h5.m.taobao.com/", "Accept": "*/*"})
    if proxy:
        p = proxy_url()
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
    """1차 응답이 x5 핸드셰이크 스크립트면 갈 URL(+x5referer=원 요청 주소) — 아니면 빈 문자열."""
    m = _X5_RE.search(str(body or "")[:20000])
    if not m:
        return ""
    url = m.group(1)
    if m.group(2):                                 # `"…x5referer=" + x5referer` — 원 요청 주소를 이어 붙인다
        url += quote(original_url, safe="")
    return url


def _blocked(j: dict, body: str) -> str:
    """punish/captcha(=사람 확인) 사유 한 줄 — 아니면 빈 문자열. RGV587은 서버 IP를 막은 응답."""
    ret = " ".join(str(x) for x in ((j or {}).get("ret") or []))
    url = str(((j or {}).get("data") or {}).get("url") or "") if isinstance((j or {}).get("data"), dict) else ""
    if _PUNISH_RE.search(url) or (not j and _PUNISH_RE.search(str(body or "")[:20000])):
        return "사람 확인(punish/captcha) 요구 — " + (ret[:60] or "슬라이더 페이지")
    if "RGV587" in ret:
        return "접속 차단(RGV587) — " + ret[:60]
    return ""


def mtop_ex(s, api: str, data: dict, v: str = "6.0") -> dict:
    """`{json, log, state, reason}` — state: ok | blocked(→ (c) 수동) | error. API 호출 최대 3회(핸드셰이크 GET 별도)."""
    payload = json.dumps(data, separators=(",", ":"))
    log: list = []
    base = f"https://h5api.m.taobao.com/h5/{api}/{v}/"
    handshakes = 0
    for attempt in range(1, MAX_TRIES + 1):
        tk = s.cookies.get("_m_h5_tk") or ""
        t = str(int(time.time() * 1000))
        sign = hashlib.md5(f"{tk.split('_')[0]}&{t}&{APPKEY}&{payload}".encode()).hexdigest()
        params = {"jsv": "2.7.2", "appKey": APPKEY, "t": t, "sign": sign, "api": api, "v": v,
                  "type": "json", "dataType": "json", "data": payload}
        full = base + "?" + urlencode(params)
        try:
            r = _get_url(s, full)
        except Exception as exc:                                # noqa: BLE001
            log.append(f"{attempt}차: {type(exc).__name__}")
            return {"json": None, "log": log, "state": "error", "reason": f"요청 실패 {type(exc).__name__}"}
        body = r.text or ""
        try:
            j = r.json()
        except Exception:
            j = None
        if j is None:
            hs = x5_handshake_url(body, full)
            if hs and handshakes < 2:
                handshakes += 1
                try:
                    hr = _get_url(s, hs)
                    log.append(f"{attempt}차: HTTP {r.status_code} · x5 핸드셰이크 스크립트 → set_x5referer GET HTTP {hr.status_code}"
                               f" · x5sec 쿠키 {'받음' if s.cookies.get('x5sec') else '없음'}")
                except Exception as exc:                        # noqa: BLE001
                    log.append(f"{attempt}차: x5 핸드셰이크 GET 실패 {type(exc).__name__}")
                    return {"json": None, "log": log, "state": "error", "reason": "x5 핸드셰이크 GET 실패"}
                continue
            why = _blocked(None, body)
            log.append(f"{attempt}차: HTTP {r.status_code} · JSON 아님 · 앞 {body[:100]!r}")
            return {"json": None, "log": log, "state": "blocked" if why else "error",
                    "reason": why or "JSON 아닌 응답(핸드셰이크 스크립트도 아님)"}
        ret = j.get("ret") or []
        log.append(f"{attempt}차: HTTP {r.status_code} · ret={ret[:2]} · 토큰 쿠키 {'있음' if tk else '없음'}")
        if any("SUCCESS" in str(x) for x in ret):
            return {"json": j, "log": log, "state": "ok", "reason": ""}
        why = _blocked(j, body)
        if why:
            return {"json": None, "log": log, "state": "blocked", "reason": why}
        if not any("TOKEN" in str(x) for x in ret):
            return {"json": j, "log": log, "state": "error", "reason": "응답 코드 " + " ".join(str(x) for x in ret)[:80]}
    return {"json": None, "log": log, "state": "error", "reason": f"{MAX_TRIES}회 안에 토큰 왕복을 못 끝냄"}


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


def session_for(via: str):
    """mtop 경로 전용 세션 — via=proxy일 때만 주거 프록시를 싣는다."""
    if via == "relay":
        return RelaySession()
    return _session(proxy=(via == "proxy"))


def probe(arg: str, via: str = "direct") -> dict:
    """`via`: direct · relay(relay2 서울 IP — mkt.php 새 판) · proxy(`TAOBAO_PROXY_URL`)."""
    out = {"input": arg[:80], "item_id": "", "how": "", "log": [], "detail": None, "desc_images": None,
           "via": VIAS.get(via, via), "state": "", "reason": ""}
    try:
        s = session_for(via)
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
    out["state"], out["reason"] = r["state"], r["reason"]
    out["detail"] = summarize(r["json"]) if r["json"] else None
    if r["state"] != "ok":
        return out
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
    """자동 경로 한 건 — `{state: ok|blocked|error, reason, payload, log}`."""
    try:
        s = session_for(via)
    except NoProxy:
        return {"state": "error", "reason": "프록시 미설정 — TAOBAO_PROXY_URL", "payload": None, "log": []}
    r = mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": item_id})
    if r["state"] != "ok":
        return {"state": r["state"], "reason": r["reason"], "payload": None, "log": r["log"]}
    d = mtop_ex(s, "mtop.taobao.detail.getdesc", {"id": item_id, "type": "1"})
    payload = enrich_payload(r["json"], d["json"] if d["state"] == "ok" else None)
    if not (payload["title"] and payload["images"]):
        return {"state": "error", "reason": "응답은 왔지만 제목·사진이 비었어요", "payload": None, "log": r["log"] + d["log"]}
    return {"state": "ok", "reason": "", "payload": payload, "log": r["log"] + d["log"]}
