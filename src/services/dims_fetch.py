"""Y14(오너 2026-10-21 「가구 4건 치수 서버에서 수집」) — 상품 치수를 세 갈래에서 모아 맞춰 본다.

갈래:
  ① 온바운드 item_get — 规格参数(`item.props` 이름·값)의 尺寸·规格·长宽高·尺码·包装尺寸 · 옵션 값(`props_list` 「축:값」).
     옵션마다 치수가 다르면 **가장 큰 것**(배송비가 모자라지 않게). 24시간 보관본이 있으면 다시 부르지 않는다(과금 0).
  ② 사진 글자 — 갤러리·상세 사진. 번역 기록에 글자가 있으면 그 글자, 없는 장만 **텐센트 OCR**(번역 아님 · 장당 소량 · 상한).
  ③ 규격 블록 — 수집 때 읽은 규격표(`detail_specs`)와 상세 글.
읽는 규칙은 배송비 엔진(Y13-C)과 같다 — `A×B×C cm` · 이름표 치수(宽/长/高 · 가로/세로/높이 · 축마다 가장 큰 값).

판정: 셋 중 **둘 이상이 같으면 「확정」**(긴 변부터 맞춰 각 변 ±2cm 또는 ±5%) · 하나뿐이면 「추정(출처)」 ·
여럿인데 서로 다르면 가장 큰 것을 「추정(불일치)」. 결과는 상품 기록 `dims_auto`에 출처와 함께 — 오너가 넣은 `ship_input`은
덮어쓰지 않는다(배송비 엔진에서도 오너 값이 이긴다). 수집 원본(제목·사진·옵션)은 건드리지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

#: 规格参数에서 치수로 보는 이름
SPEC_KEYS = ("尺寸", "规格", "长宽高", "尺码", "产品尺寸", "包装尺寸", "外形尺寸", "商品尺寸", "규격", "사이즈", "크기", "치수")
OCR_MAX_PAGES = 12
SRC_LABEL = {"onebound": "온바운드 규격", "photo": "사진 글자", "spec": "규격 블록"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse(text: str) -> Optional[Dict[str, Any]]:
    """글 한 덩어리에서 치수 `{dims_cm:[a,b,c], seen}` — 여러 개면 부피가 가장 큰 것. 없으면 None."""
    from src.seller_console.shipping_ratio import _DIM_RE, labeled_dims, normalize_dim_text
    best = None
    text = normalize_dim_text(text)
    for m in _DIM_RE.finditer(text):
        vals = [float(m.group(i)) for i in (1, 2, 3)]
        if (m.group(4) or "").lower() in ("mm", "毫米"):
            vals = [v / 10 for v in vals]
        if not all(1 <= v <= 400 for v in vals):
            continue
        if best is None or _vol(vals) > _vol(best["dims_cm"]):
            best = {"dims_cm": vals, "seen": m.group(0).strip()}
    lab = labeled_dims(text)
    if lab and (best is None or _vol(lab["dims_cm"]) > _vol(best["dims_cm"])):
        best = {"dims_cm": lab["dims_cm"], "seen": lab["seen"]}
    return best


def _vol(d) -> float:
    return float(d[0]) * float(d[1]) * float(d[2]) if d and len(d) == 3 else 0.0


def _biggest(cands: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    cands = [c for c in cands if c]
    return max(cands, key=lambda c: _vol(c["dims_cm"])) if cands else None


def same(a, b) -> bool:
    """긴 변부터 맞춰 각 변이 ±2cm 또는 ±5% 안이면 같은 치수."""
    if not (a and b):
        return False
    x, y = sorted(map(float, a), reverse=True), sorted(map(float, b), reverse=True)
    return all(abs(p - q) <= max(2.0, 0.05 * max(p, q)) for p, q in zip(x, y))


def num_iid(url: str) -> str:
    m = re.search(r"[?&]id=(\d{6,15})", str(url or ""))
    return m.group(1) if m else ""


# ── 갈래 ───────────────────────────────────────────────────────────────────────

def from_onebound(url: str, call: Callable = None) -> Dict[str, Any]:
    """`{found, why, calls}` — 규격표 이름 칸이 치수 이름인 줄 + 옵션 값 전부를 읽는다(옵션별이면 가장 큰 것)."""
    iid = num_iid(url)
    if not iid:
        return {"found": None, "why": "타오바오·티몰 상품번호가 아님", "calls": 0}
    if call is None:
        from src.collectors import taobao_provider_onebound as OB
        with OB.as_source("dims"):
            res = OB.call(iid)
    else:
        res = call(iid)
    calls = 0 if res.get("reused") else int(bool(res.get("ok") or res.get("raw")))
    if not res.get("ok"):
        return {"found": None, "why": str(res.get("why") or "온바운드 실패")[:160], "calls": calls}
    item = (res.get("raw") or {}).get("item") or {}
    cands, raw_seen = [], []
    for p in item.get("props") or []:
        if isinstance(p, dict) and any(k in str(p.get("name") or "") for k in SPEC_KEYS):
            raw_seen.append(f"{p.get('name')}:{str(p.get('value'))[:40]}")
            c = parse(f"{p.get('name')}:{p.get('value')}")
            if c:
                cands.append(dict(c, seen=f"{p.get('name')} {c['seen']}"))
    plist = item.get("props_list") if isinstance(item.get("props_list"), dict) else {}
    for v in plist.values():
        c = parse(str(v))
        if c:
            cands.append(dict(c, seen=f"옵션 {str(v)[:40]}"))
    # Y15: 「없음」일 때 무엇을 읽었는지 남긴다(치수 이름 칸이 있었는데 못 읽었나 / 아예 없었나) — 다음 규칙 구멍을 찾는 재료
    why = "" if cands else ("규격에 치수 칸은 있는데 숫자를 못 읽음 — " + " · ".join(raw_seen[:3]) if raw_seen
                            else f"규격·옵션에 치수 없음(규격 {len(item.get('props') or [])}칸 · 옵션 {len(plist)}개)")
    return {"found": _biggest(cands), "why": why[:200], "calls": calls, "reused": bool(res.get("reused")),
            "raw_seen": raw_seen[:5]}


def _page_texts(ex: dict) -> List[tuple]:
    """`[(kind, idx, url, 저장된 글자)]` — 갤러리·상세 원본 순서대로."""
    from src.services.detail_image_plan import entry_text
    from src.services.image_translate_store import originals_of
    out = []
    for kind, key in (("gallery", "images_ko"), ("detail", "detail_images_ko")):
        by_idx = {int(e.get("idx", -1)): e for e in ex.get(key) or [] if isinstance(e, dict)}
        for i, u in enumerate(originals_of(ex, kind)):
            e = by_idx.get(i) or {}
            out.append((kind, i, u, entry_text(e).strip() if e else ""))
    return out


def from_photos(ex: dict, ocr: Callable = None, cache: Optional[dict] = None, max_pages: int = OCR_MAX_PAGES) -> Dict[str, Any]:
    """`{found, why, ocr_pages, ocr_cache}` — 글자가 저장된 장은 그대로, 없는 장만 OCR(번역 아님). 상세부터(치수표가 거기 많다)."""
    cache = dict(cache or {})
    pages = _page_texts(ex)
    pages.sort(key=lambda p: (p[0] != "detail", p[1]))
    cands, done = [], 0
    for kind, idx, url, text in pages:
        k = f"{kind}:{idx}"
        if not text:
            if k in cache:
                text = cache[k]
            elif done < max_pages and url:
                text = (ocr or _ocr_text)(url)
                done += 1
                cache[k] = text
        c = parse(text) if text else None
        if c:
            cands.append(dict(c, seen=f"{'상세' if kind == 'detail' else '사진'} {idx + 1}: {c['seen']}"))
    return {"found": _biggest(cands), "why": "" if cands else "사진 글자에 치수 없음", "ocr_pages": done, "ocr_cache": cache}


def _ocr_text(url: str) -> str:
    from src.services import image_edit as IE
    from src.services import ocr_tencent as O
    raw, _why = IE.work_bytes(url)
    if not raw:
        return ""
    got = O.read_boxes(raw)
    return " ".join(str(b.get("src") or "") for b in got.get("boxes") or [])[:2000] if got.get("ok") else ""


def from_spec_block(ex: dict) -> Dict[str, Any]:
    parts = []
    for sp in ex.get("detail_specs") or []:
        parts.append(":".join(map(str, sp)) if isinstance(sp, (list, tuple)) else str(sp))
    parts += [str(ex.get(k) or "") for k in ("description", "description_ko")]
    cands = [parse(p) for p in parts]
    return {"found": _biggest(cands), "why": "" if any(cands) else "규격 블록·상세 글에 치수 없음"}


# ── 판정 ───────────────────────────────────────────────────────────────────────

def decide(found: Dict[str, Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """`{dims_cm, confidence: 확정|추정|없음, label, agree:[출처]}`."""
    have = {s: f for s, f in found.items() if f}
    if not have:
        return {"dims_cm": None, "confidence": "없음", "label": "세 갈래 모두 치수 없음", "agree": []}
    order = [s for s in ("onebound", "spec", "photo") if s in have]
    for i, a in enumerate(order):
        agree = [a] + [b for b in order[i + 1:] if same(have[a]["dims_cm"], have[b]["dims_cm"])]
        if len(agree) >= 2:
            dims = max((have[s]["dims_cm"] for s in agree), key=_vol)
            return {"dims_cm": dims, "confidence": "확정", "agree": agree,
                    "label": "확정(" + "·".join(SRC_LABEL[s] for s in agree) + " 일치)"}
    if len(have) == 1:
        s = order[0]
        return {"dims_cm": have[s]["dims_cm"], "confidence": "추정", "agree": [s], "label": f"추정({SRC_LABEL[s]})"}
    s = max(order, key=lambda x: _vol(have[x]["dims_cm"]))
    return {"dims_cm": have[s]["dims_cm"], "confidence": "추정", "agree": [s],
            "label": "추정(불일치 — " + " / ".join(f"{SRC_LABEL[x]} {_fmt(have[x]['dims_cm'])}" for x in order) + " · 가장 큰 값)"}


def _fmt(d) -> str:
    return "×".join(f"{float(x):g}" for x in d) + "cm" if d else "—"


def fetch(item: dict, *, ob_call: Callable = None, ocr: Callable = None, onebound: bool = True) -> Dict[str, Any]:
    """한 상품 — `{dims_auto, rows}`(저장은 부르는 쪽). `dims_auto` = {dims_cm, confidence, label, sources, at, ocr_pages, ...}."""
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    prev = ex.get("dims_auto") if isinstance(ex.get("dims_auto"), dict) else {}
    ob = from_onebound(str(item.get("url") or ex.get("url") or ""), call=ob_call) if onebound else \
        {"found": None, "why": "온바운드 안 부름", "calls": 0}
    ph = from_photos(ex, ocr=ocr, cache=prev.get("ocr_cache"))
    sb = from_spec_block(ex)
    found = {"onebound": ob["found"], "photo": ph["found"], "spec": sb["found"]}
    d = decide(found)
    sources = [{"src": s, "label": SRC_LABEL[s], "dims_cm": (r["found"] or {}).get("dims_cm"),
                "seen": (r["found"] or {}).get("seen", ""), "why": r.get("why", ""), "raw_seen": r.get("raw_seen") or []}
               for s, r in (("onebound", ob), ("photo", ph), ("spec", sb))]
    out = dict(d, sources=sources, at=_now(), ocr_pages=ph["ocr_pages"], ocr_cache=ph["ocr_cache"],
               onebound_calls=ob.get("calls", 0))
    return {"dims_auto": out}


def line(da: dict) -> str:
    """사람이 읽는 한 줄 — 「치수 120×80×75cm · 확정(온바운드 규격·사진 글자 일치)」."""
    if not isinstance(da, dict) or not da.get("dims_cm"):
        return "치수 못 찾음 — " + " · ".join(f"{s['label']}: {s.get('why') or '없음'}" for s in (da or {}).get("sources") or [])
    return f"치수 {_fmt(da['dims_cm'])} · {da.get('label')}"


# ── 수집 단계에 넣기(가구·대형) ─────────────────────────────────────────────────

def needed(pd: dict) -> bool:
    """가구 치수 게이트에 걸리는 상품인가(배송비 엔진과 같은 판정) — 치수를 못 읽었고 크기 표가 가구라고 할 때."""
    try:
        from src.seller_console.shipping_ratio import read_size
        sz = read_size(pd)
        return bool(sz.get("need_dims")) and not sz.get("dims_cm")
    except Exception:                                            # noqa: BLE001
        return False


def light_pd(ex: dict) -> dict:
    """수집 기록만으로 크기 판정 재료 — 빌더를 돌리지 않는다(수집 단계에서 가볍게)."""
    from src.services.detail_image_plan import photo_text
    ex = ex or {}
    return {"title_src": ex.get("title") or "", "title": ex.get("title") or "", "title_ko": ex.get("title_ko") or "",
            "description": ex.get("description") or "", "options": ex.get("options") or [],
            "detail_specs": ex.get("detail_specs") or [], "photo_text": photo_text(ex),
            "url": ex.get("url") or ""}


def should_fetch(ex: dict) -> bool:
    """치수 게이트에 걸릴 상품인데 아직 서버 수집도 오너 값도 없다 — 한 번만 돈다(이미 돌았으면 결과가 「없음」이어도 다시 안 함)."""
    ex = ex or {}
    if isinstance(ex.get("dims_auto"), dict):
        return False
    si = ex.get("ship_input")
    if isinstance(si, dict) and any(si.get(k) for k in ("l", "w", "h")):
        return False
    return bool(needed(light_pd(ex)))


def maybe_queue(item_id: str, ex: dict) -> bool:
    """수집·보강이 끝난 뒤 — 가구·대형 치수 게이트에 걸릴 상품이면 `dims_fetch` 일회성 줄을 건다(한 번만 · 오너 값이 있으면 안 함).
    2호 때처럼 「치수 확인 필요」가 사람 손으로 넘어오지 않게(오너 2026-10-21)."""
    if not item_id or not should_fetch(ex):
        return False
    try:
        from src.services import oneshot_ops as O
        return O.enqueue({"op": "dims_fetch", "item_id": str(item_id), "reason": "수집 뒤 가구 치수 자동 수집"})
    except Exception as exc:                                     # noqa: BLE001 — 줄 걸기 실패가 수집을 막지 않는다
        logger.warning("[치수 수집] 줄 걸기 실패 item=%s: %s", str(item_id)[:8], exc)
        return False
