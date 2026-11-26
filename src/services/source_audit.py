"""오너 11-26 저녁 ② — 다른 소싱처도 아마존과 같은 병이 있나(운영 **읽기 전용** 진단).

최근 N일 수집 행을 소싱처별로 센다:
  · 쓸 만한 사진 비율 — 주소에 박힌 크기 토큰으로만 판정(아마존 크기 토큰 · 알리 `_480x480` · 테무 `w/180`). 토큰이 없는 주소는
    「주소로는 모름」으로 따로 센다(쓸 만하다고 치지 않는다). `measure=n`이면 소싱처마다 첫 사진 n장을 **실제로 잰다**(머리만).
  · 옵션은 있는데 SKU 0 — 옵션 값이 2개 이상인 옵션이 있는데 조합별 가격(SKU)이 하나도 없는 행.
  · 주소가 짧은 링크 — 공유 단축 주소(a.co · s.click.aliexpress · e.tb.cn …)가 펴지지 않은 채 저장된 행.
쓰기 0 · 마켓 호출 0.
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

KEYS = ["images", "options", "skus"]

SOURCES = [("amazon", "아마존"), ("aliexpress", "알리익스프레스"), ("taobao", "타오바오·티몰"), ("1688", "1688"),
           ("temu", "테무"), ("rakuten", "라쿠텐"), ("other", "그 밖")]
LABELS = dict(SOURCES)


def source_of(url: str, domain: str = "") -> str:
    host = (urlparse(str(url or "")).hostname or str(domain or "")).lower()
    if not host:
        return "other"
    if "amazon." in host or host in ("a.co", "amzn.to", "amzn.asia", "amzn.eu", "amzn.com"):
        return "amazon"
    if "aliexpress" in host:
        return "aliexpress"
    if "1688.com" in host:
        return "1688"
    if "taobao" in host or "tmall" in host or host.endswith("tb.cn"):
        return "taobao"
    if "temu" in host:
        return "temu"
    if "rakuten" in host:
        return "rakuten"
    return "other"


def _extra(it: Dict) -> Dict:
    try:
        return json.loads(it.get("extra_json") or "{}") or {}
    except Exception:
        return {}


def _has_multi_option(ex: Dict) -> bool:
    for o in ex.get("options") or []:
        if isinstance(o, dict) and len([v for v in (o.get("values") or []) if str(v).strip()]) >= 2:
            return True
    return False


def audit(rows: List[Dict], *, measure: int = 0, size_of: Optional[Callable] = None) -> Dict:
    from src.collectors.link_diag import short_link_market
    from src.services.photo_fix import url_small, SMALL
    agg = {k: {"source": k, "label": v, "rows": 0, "images": 0, "usable": 0, "small": 0, "unknown": 0,
               "no_images": 0, "opt_no_sku": 0, "opt_rows": 0, "short": 0, "samples": []} for k, v in SOURCES}
    firsts: Dict[str, List[str]] = {k: [] for k in agg}
    for it in rows or []:
        ex = _extra(it)
        src = source_of(str(it.get("url") or ""), str(it.get("domain") or ""))
        a = agg[src]
        a["rows"] += 1
        imgs = [u for u in (ex.get("images") or []) if isinstance(u, str) and u]
        if not imgs:
            a["no_images"] += 1
        else:
            firsts[src].append(imgs[0])
        for u in imgs:
            a["images"] += 1
            v = url_small(u)
            if v is None:
                a["unknown"] += 1
            elif v:
                a["small"] += 1
            else:
                a["usable"] += 1
        if _has_multi_option(ex):
            a["opt_rows"] += 1
            if not [s for s in (ex.get("skus") or []) if isinstance(s, dict)]:
                a["opt_no_sku"] += 1
        if short_link_market(str(it.get("url") or "")):
            a["short"] += 1
            if len(a["samples"]) < 3:
                a["samples"].append({"id": str(it.get("id") or ""), "url": str(it.get("url") or "")[:120]})
    if measure:
        if size_of is None:
            from src.services.coupang_image_check import size_of
        for k, urls in firsts.items():
            got = []
            for u in urls[:int(measure)]:
                try:
                    ls = int((size_of(u) or {}).get("long_side") or 0)
                except Exception:                              # noqa: BLE001
                    ls = 0
                got.append(ls)
            ok = [g for g in got if g]
            agg[k]["measured"] = {"n": len(got), "read": len(ok), "under": sum(1 for g in ok if g < SMALL),
                                  "min": min(ok) if ok else 0, "max": max(ok) if ok else 0}
    out = []
    for k, _ in SOURCES:
        a = agg[k]
        if not a["rows"]:
            continue
        judged = a["usable"] + a["small"]
        a["usable_pct"] = round(100.0 * a["usable"] / judged, 1) if judged else None
        a["unknown_pct"] = round(100.0 * a["unknown"] / a["images"], 1) if a["images"] else None
        out.append(a)
    return {"sources": out, "rows": sum(a["rows"] for a in out)}


def verdict(data: Dict) -> str:
    bits = []
    for a in data.get("sources") or []:
        b = []
        if a.get("usable_pct") is not None and a["usable_pct"] < 80:
            b.append(f"쓸 만한 사진 {a['usable_pct']}%")
        if a.get("opt_no_sku"):
            b.append(f"옵션 있는데 SKU 0 {a['opt_no_sku']}건")
        if a.get("short"):
            b.append(f"짧은 링크 {a['short']}건")
        m = a.get("measured") or {}
        if m.get("under"):
            b.append(f"잰 첫 사진 {m['read']}장 중 {m['under']}장 500px 미만")
        if b:
            bits.append(f"{a['label']}: " + " · ".join(b))
    return " / ".join(bits) if bits else "걸리는 소싱처 없음"
