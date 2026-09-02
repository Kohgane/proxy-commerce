"""scripts/taobao_probe.py — M1-0 L1~L3·L5 실측 프로브. **egress가 열린 곳에서 돌린다.**

이 컨테이너에서는 못 돈다: 에이전트 프록시가 타오바오 계열 CONNECT를 403으로 막는다(실측
`item.taobao.com` 등 전부 HTTP 000). 그래서 **오너 서버(Bluehost·SSH)나 Render 셸**에서
돌리라고 이 파일을 남긴다. 추측으로 어댑터를 쓰지 않기 위한 도구다 — 구현 전 실측이 원칙.

    python3 scripts/taobao_probe.py                  # 기본 3종(본토·티몰·해외판)
    python3 scripts/taobao_probe.py --url <상품URL>   # 특정 상품
    python3 scripts/taobao_probe.py --json            # 기계가 읽을 형태로

**하는 일:** 층별로 무엇이 오는지 재고 **필드 커버리지 표**를 찍는다.
  L1 게스트 HTML   — 비로그인 GET. 뭐가 오고 뭐가 가려지는지.
  L2 mtop h5 API   — 게스트 쿠키 → `_m_h5_tk` 토큰 → md5 서명 → 상세 API.
  L3 모바일 h5     — `main.m.taobao.com` 초기상태 JSON(window.__ 계열).
  L5 이미지 CDN    — alicdn 크기 접미(`_430x430q90.jpg`) 제거 시 원본이 살아 있는가.

**쓰지 않는 것:** 로그인 쿠키·계정 자격. 게스트로 뭐가 되는지가 이 프로브의 질문이다.
계정을 태우면 차단 위험이 생기고, 어차피 서버 수집은 게스트로 돌아야 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from urllib.parse import urlencode

try:
    import requests
except ImportError:  # 서버에 없으면 그것부터 알린다
    print("requests가 필요합니다: pip install requests")
    sys.exit(2)

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")

DEFAULT_TARGETS = [
    ("taobao 본토", "https://item.taobao.com/item.htm?id=666666666666"),
    ("tmall", "https://detail.tmall.com/item.htm?id=666666666666"),
    ("world(해외판)", "https://world.taobao.com/item/666666666666.htm"),
]

# 필드 커버리지 — 층마다 같은 잣대로 잰다(층별 비교가 되게).
FIELDS = ("제목", "가격", "옵션", "SKU", "이미지", "설명")

# 로그인 벽·캡차 신호. 이게 잡히면 그 층은 게스트로 못 뚫는다는 뜻이다.
_BLOCK_MARKERS = ("login.taobao.com", "_m_h5_c", "punish", "captcha", "訪問頻繁",
                  "亲，小二正忙", "FAIL_SYS_USER_VALIDATE", "RGV587_ERROR")

MTOP_HOST = "https://h5api.m.taobao.com"
MTOP_API = "mtop.taobao.pcdetail.data.get"
MTOP_APPKEY = "12574478"          # h5 공개 appKey(비밀 아님 — 브라우저가 그대로 보낸다)


def _item_id(url: str) -> str:
    m = re.search(r"[?&]id=(\d+)", url) or re.search(r"/item/(\d+)", url)
    return m.group(1) if m else ""


def _has(hay: str, *needles) -> bool:
    return any(n in hay for n in needles)


def _coverage_from_html(html: str) -> dict:
    """HTML에서 필드가 잡히는지. **추정하지 않는다** — 신호가 있으면 True, 없으면 False."""
    return {
        "제목": _has(html, "tb-main-title", '"title"', "og:title"),
        "가격": bool(re.search(r'"(price|priceText|defaultPrice)"\s*:', html))
                 or _has(html, "tb-rmb-num"),
        "옵션": _has(html, '"skuBase"', '"props"', "tb-skin", "J_isku"),
        "SKU": _has(html, '"skuId"', '"sku2info"', '"skuCore"'),
        "이미지": bool(re.search(r"(gw|img)\.alicdn\.com/[^\"']+\.(jpg|png|webp)", html)),
        "설명": _has(html, "descUrl", "desc_url", "J_DivItemDesc", '"detailUrl"'),
    }


def _probe_l1(url: str, timeout: int) -> dict:
    """L1 — 게스트 HTML GET."""
    out = {"layer": "L1 게스트 HTML", "url": url}
    try:
        r = requests.get(url, headers={"User-Agent": UA_PC, "Accept-Language": "zh-CN,zh;q=0.9"},
                         timeout=timeout, allow_redirects=True)
        html = r.text or ""
        out.update(status=r.status_code, bytes=len(html), final_url=r.url,
                   blocked=[m for m in _BLOCK_MARKERS if m in html],
                   coverage=_coverage_from_html(html))
    except Exception as exc:
        out.update(status=None, error=f"{type(exc).__name__}: {exc}")
    return out


def _mtop_sign(token: str, t: str, appkey: str, data: str) -> str:
    """공개 알고리즘: md5(token & t & appKey & data)."""
    return hashlib.md5(f"{token}&{t}&{appkey}&{data}".encode()).hexdigest()


def _probe_l2(item_id: str, timeout: int) -> dict:
    """L2 — mtop h5: 게스트 쿠키로 `_m_h5_tk` 받고 서명해 상세 API 호출.

    1차 호출은 토큰이 없어 반드시 실패한다(그게 정상) — 그 응답의 쿠키에서 토큰을 받아 2차를 친다.
    """
    out = {"layer": "L2 mtop h5", "item_id": item_id}
    if not item_id:
        out["error"] = "상품 ID를 URL에서 못 뽑았습니다"
        return out
    s = requests.Session()
    s.headers.update({"User-Agent": UA_MOBILE, "Referer": "https://h5.m.taobao.com/"})
    data = json.dumps({"itemNumId": item_id}, separators=(",", ":"))
    url = f"{MTOP_HOST}/h5/{MTOP_API}/1.0/"

    def _call(token: str) -> tuple:
        t = str(int(time.time() * 1000))
        q = {"jsv": "2.6.1", "appKey": MTOP_APPKEY, "t": t,
             "sign": _mtop_sign(token, t, MTOP_APPKEY, data),
             "api": MTOP_API, "v": "1.0", "dataType": "json", "type": "jsonp",
             "callback": "cb", "data": data}
        r = s.get(f"{url}?{urlencode(q)}", timeout=timeout)
        return r, (r.text or "")

    try:
        _r1, _b1 = _call("")                       # 토큰 받기용(실패가 정상)
        raw = s.cookies.get("_m_h5_tk", "") or ""
        token = raw.split("_")[0]
        out["token_received"] = bool(token)
        if not token:
            out["error"] = "게스트 쿠키에서 _m_h5_tk를 못 받았습니다(차단 가능)"
            out["first_body"] = _b1[:200]
            return out
        time.sleep(0.3)
        r2, body = _call(token)
        out.update(status=r2.status_code, bytes=len(body),
                   blocked=[m for m in _BLOCK_MARKERS if m in body],
                   coverage=_coverage_from_html(body), body_head=body[:200])
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _probe_l3(item_id: str, timeout: int) -> dict:
    """L3 — 모바일 h5 상세 페이지의 초기상태 JSON."""
    out = {"layer": "L3 모바일 h5", "item_id": item_id}
    if not item_id:
        out["error"] = "상품 ID 없음"
        return out
    u = f"https://main.m.taobao.com/item/detail.html?id={item_id}"
    try:
        r = requests.get(u, headers={"User-Agent": UA_MOBILE}, timeout=timeout)
        html = r.text or ""
        states = re.findall(r"window\.(__[A-Za-z_]+)\s*=", html)
        out.update(status=r.status_code, bytes=len(html), url=r.url,
                   initial_state_keys=sorted(set(states))[:8],
                   blocked=[m for m in _BLOCK_MARKERS if m in html],
                   coverage=_coverage_from_html(html))
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def strip_alicdn_suffix(u: str) -> str:
    """L5 — alicdn 크기 접미 제거: `..._430x430q90.jpg` → `....jpg`(라쿠텐 동형 규칙)."""
    return re.sub(r"_\d+x\d+(q\d+)?(\.\w+)?(?=\.(jpg|jpeg|png|webp))", "", u, flags=re.I)


def _probe_l5(img_url: str, timeout: int) -> dict:
    """접미를 뗀 원본이 실제로 살아 있는지 HEAD로 확인(크기 비교까지)."""
    out = {"layer": "L5 이미지 CDN", "thumb": img_url, "origin": strip_alicdn_suffix(img_url)}
    if out["origin"] == img_url:
        out["note"] = "크기 접미가 없어 승격 대상이 아닙니다"
        return out
    for key, u in (("thumb_bytes", img_url), ("origin_bytes", out["origin"])):
        try:
            r = requests.head(u, headers={"User-Agent": UA_PC}, timeout=timeout,
                              allow_redirects=True)
            out[key] = int(r.headers.get("Content-Length") or 0) if r.ok else None
            out[f"{key}_status"] = r.status_code
        except Exception as exc:
            out[key] = None
            out[f"{key}_error"] = f"{type(exc).__name__}: {exc}"
    t, o = out.get("thumb_bytes"), out.get("origin_bytes")
    out["origin_bigger"] = bool(t and o and o > t)
    return out


def _row(label: str, cov: dict) -> str:
    cells = "".join(f" {'O' if cov.get(f) else '·'}  |" for f in FIELDS)
    return f"| {label:<16}|{cells}"


def main() -> int:
    ap = argparse.ArgumentParser(description="타오바오 수집 층별 실측 프로브(게스트)")
    ap.add_argument("--url", action="append", help="상품 URL(여러 번 지정 가능)")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--image", help="L5로 확인할 alicdn 썸네일 URL")
    ap.add_argument("--json", action="store_true", help="원자료를 JSON으로")
    args = ap.parse_args()

    targets = ([(f"url{i+1}", u) for i, u in enumerate(args.url)] if args.url
               else DEFAULT_TARGETS)
    results = []
    for name, url in targets:
        iid = _item_id(url)
        results.append({"target": name, "url": url, "item_id": iid, "layers": [
            _probe_l1(url, args.timeout),
            _probe_l2(iid, args.timeout),
            _probe_l3(iid, args.timeout),
        ]})
    if args.image:
        results.append({"target": "이미지", "layers": [_probe_l5(args.image, args.timeout)]})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    print("=== 타오바오 층별 실측 (게스트·로그인 쿠키 미사용) ===\n")
    header = "| 층               |" + "".join(f" {f[:4]:<3}|" for f in FIELDS)
    for res in results:
        print(f"■ {res['target']}  {res.get('url', '')}")
        if res.get("item_id") is not None:
            print(f"  상품 ID: {res['item_id'] or '(추출 실패)'}")
        print(header)
        print("|" + "-" * (len(header) - 2) + "|")
        for L in res["layers"]:
            cov = L.get("coverage")
            if cov:
                print(_row(L["layer"], cov))
            note = L.get("error") or (", ".join(L.get("blocked") or []) and
                                      f"차단 신호: {', '.join(L['blocked'])}")
            extra = []
            if L.get("status") is not None:
                extra.append(f"HTTP {L['status']}")
            if L.get("bytes") is not None:
                extra.append(f"{L['bytes']:,}B")
            if L.get("token_received") is not None:
                extra.append(f"토큰 {'수신' if L['token_received'] else '실패'}")
            if L.get("initial_state_keys"):
                extra.append("state " + ",".join(L["initial_state_keys"][:3]))
            if L.get("origin_bigger") is not None:
                extra.append(f"원본 승격 {'성공' if L['origin_bigger'] else '실패'}")
            line = f"    {L['layer']}: " + " · ".join(extra) if extra else f"    {L['layer']}:"
            if note:
                line += f"  ← {note}"
            print(line)
        print()

    print("읽는 법: O = 그 층의 응답에서 해당 필드 신호가 잡힘 · · = 안 잡힘.")
    print("차단 신호가 뜨면 그 층은 게스트로 못 뚫는 것 — 다음 층(또는 L4 대안)으로 간다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
