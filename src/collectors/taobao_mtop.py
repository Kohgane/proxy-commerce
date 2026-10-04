"""Z3(오너 2026-10-04) 실측 — 타오바오 모바일 상세 API(`mtop.taobao.detail.getdetail`)를 **익명**으로 부를 수 있나.

조회만 한다(쓰기 0). 결과는 숫자와 응답 코드(ret)만 — 쿠키·토큰 값은 남기지 않는다.
  1) e.tb.cn 공유 링크 → 리다이렉트를 따라가 상품번호(id=)
  2) h5api 1차(토큰 없음) → `_m_h5_tk` 쿠키 → 서명 md5(token&t&appKey&data) 붙여 2차
  3) 제목 길이 · 가격 · 갤러리 수 · SKU 수 · 옵션 축/값 수 · 상세(getdesc) 이미지 수
운영(Render) 진단 화면 `/admin/diagnostics/taobao-mtop`이 부른다. 같은 절차가 볼트 `scripts/srv/mtop_probe.py`(오너 서버).
"""
from __future__ import annotations

import hashlib
import json
import re
import time

APPKEY = "12574478"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")
_DESC_IMG = re.compile(r'(//[^"\s<>]+?\.(?:jpg|jpeg|png|webp|gif))')


def _session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://h5.m.taobao.com/", "Accept": "*/*"})
    return s


def item_id_from(arg: str, s=None) -> tuple:
    arg = str(arg or "").strip()
    if re.fullmatch(r"\d{6,15}", arg):
        return arg, "직접 입력"
    m = re.search(r"[?&]id=(\d{6,15})", arg)
    if m:
        return m.group(1), "주소의 id="
    s = s or _session()
    try:
        r = s.get(arg, timeout=15, allow_redirects=True)
        body = r.text[:200000]
    except Exception as exc:                                    # noqa: BLE001
        return "", f"단축 링크 열기 실패 {type(exc).__name__}"
    m = re.search(r"[?&]id=(\d{6,15})", r.url) or re.search(r"[?&]id=(\d{6,15})", body) \
        or re.search(r"item[_.]?id[\"'=:\s]+(\d{6,15})", body, re.I)
    return (m.group(1) if m else ""), f"HTTP {r.status_code} · 최종 주소 {r.url[:80]} · 본문 {len(body)}자"


def mtop(s, api: str, data: dict, v: str = "6.0") -> tuple:
    payload = json.dumps(data, separators=(",", ":"))
    log = []
    for attempt in (1, 2):
        tk = s.cookies.get("_m_h5_tk") or ""
        t = str(int(time.time() * 1000))
        sign = hashlib.md5(f"{tk.split('_')[0]}&{t}&{APPKEY}&{payload}".encode()).hexdigest()
        params = {"jsv": "2.7.2", "appKey": APPKEY, "t": t, "sign": sign, "api": api, "v": v,
                  "type": "json", "dataType": "json", "data": payload}
        try:
            r = s.get(f"https://h5api.m.taobao.com/h5/{api}/{v}/", params=params, timeout=20)
        except Exception as exc:                                # noqa: BLE001
            log.append(f"{attempt}차: {type(exc).__name__}")
            return None, log
        try:
            j = r.json()
        except Exception:
            log.append(f"{attempt}차: HTTP {r.status_code} · JSON 아님 · 앞 {r.text[:100]!r}")
            return None, log
        ret = j.get("ret") or []
        log.append(f"{attempt}차: HTTP {r.status_code} · ret={ret[:2]} · 토큰 쿠키 {'있음' if tk else '없음'}")
        if any("SUCCESS" in str(x) for x in ret) or not any("TOKEN" in str(x) for x in ret):
            return j, log
    return None, log


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


def probe(arg: str) -> dict:
    s = _session()
    iid, how = item_id_from(arg, s)
    out = {"input": arg[:80], "item_id": iid, "how": how, "log": [], "detail": None, "desc_images": None}
    if not iid:
        return out
    j, log = mtop(s, "mtop.taobao.detail.getdetail", {"itemNumId": iid})
    out["log"] += log
    out["detail"] = summarize(j) if j else None
    dj, dlog = mtop(s, "mtop.taobao.detail.getdesc", {"id": iid, "type": "1"})
    out["log"] += ["상세 " + x for x in dlog]
    if dj:
        out["desc_images"] = len(set(_DESC_IMG.findall(json.dumps(dj.get("data") or {}, ensure_ascii=False))))
    return out
