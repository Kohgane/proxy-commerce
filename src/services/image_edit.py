"""Y11(오너 2026-10-14) — 사진 편집: 글자 상자·판촉 배지를 탭해서 지우기·고치기.

실측 07:04 VRSUK 대표사진 — 우상단 쿠폰 배지 2개(88VIP SALE 235 / 天猫国际加补券 320), 하단 띠(1元抵88元+赠品 /
国庆狂欢 55%OFF / 静享意式家), 좌상단 브랜드 로고. 예전엔 「프로모션 의심 → 등록에서 뺍니다」로 사진 **전체**를 뺐다.

- 상자: 텐센트 결과의 줄 상자(`images_ko[].boxes` — 이번부터 저장) · 없으면 텐센트 OCR로 한 번 다시 읽는다(`ocr_tencent.read_boxes`)
  + 색 덩어리 배지(쿠폰 스티커처럼 배경과 확 다른 채도 높은 사각) — 작은 미리보기(긴 변 256px)에서 찾는다.
- 분류: 판촉(ko_polish `promo_hits` · 가게 UI 낱말 · 색 배지) / 브랜드 로고(상품 브랜드 이름) / 상표 위험(Y10 토큰) / 일반 글자.
- 지우기 = Cloudinary `gen_remove`(영역 지정) · 글자 고치기 = 같은 자리 gen_remove 뒤 Noto Sans KR 글자 얹기(상자에 맞춰 크기 · 원래 글자색).
  **원본 주소를 Cloudinary가 직접 받아 간다**(원격 업로드 + eager) — 서버는 사진 바이트를 만지지 않는다(메모리 0).
- 편집본은 그 장의 `images_ko[].url`을 바꾼다(`edit.prev_url`·`prev_use`로 되돌린다) · `edit.by` = user | auto · 원본은 그대로.
- 지운 상자의 글자는 판촉·상표 판정에서 빠진다(`image_translate_store.erased_out`) → 「프로모션 의심」이 풀리면 그 장이 등록에 들어간다.
- 자동 1차(사전검증 전): 판촉 상자 중 **제품 영역(대표 피사체 상자) 밖**인 것만 지운다(오너 2026-10-14) — 겹치면 사용자 선택.
- 비용: 편집 한 번(gen_remove 1회 + 글자 얹기) = (50 + 1 + 글자 수) 변환 / 1,000 = 약 0.051 크레딧(D3 실측과 같은 상수).
  하루 상한 `IMAGE_EDIT_DAILY_CAP`(기본 200회, KST 자정 초기화).
"""
from __future__ import annotations

import io
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

ENV_CAP = "IMAGE_EDIT_DAILY_CAP"
DEFAULT_CAP = 200
TX_GEN_REMOVE = 50
TX_BASE = 1
TX_PER_TEXT = 1
TX_PER_CREDIT = 1000
FONT = "Noto Sans KR"
SMALL_SIDE = 256
CLASS_LABEL = {"promo": "판촉", "brand": "브랜드 로고", "risk": "상표 위험", "text": "일반 글자"}


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP)) or DEFAULT_CAP))
    except (TypeError, ValueError):
        return DEFAULT_CAP


def _day_key() -> str:
    from src.services.image_translate_auto import kst_day
    return "imgedit:day:" + kst_day()


def today_count() -> int:
    from src.db import image_translate_queue_pg as q
    try:
        return int(q.day_count(_day_key()) or 0)
    except Exception:                                           # noqa: BLE001
        return 0


def cost(n_text: int = 0) -> Dict:
    tx = TX_GEN_REMOVE + TX_BASE + TX_PER_TEXT * max(0, int(n_text or 0))
    return {"tx": tx, "credits": round(tx / TX_PER_CREDIT, 3)}


def configured() -> Tuple[bool, str]:
    from src.services.image_gen_remove import configured as _c
    return _c()


# ── 상자 ───────────────────────────────────────────────────────────────────────────────────

def _entry(extra: dict, kind: str, idx: int, create: bool = False) -> Optional[dict]:
    key = "images_ko" if kind == "gallery" else "detail_images_ko"
    rows = extra.setdefault(key, []) if create else (extra.get(key) or [])
    for e in rows:
        if isinstance(e, dict) and int(e.get("idx", -1)) == int(idx):
            return e
    if not create:
        return None
    e = {"idx": int(idx), "kind": kind}
    rows.append(e)
    return e


def _original(extra: dict, kind: str, idx: int) -> str:
    src = [u for u in (extra.get("images" if kind == "gallery" else "detail_images") or []) if u]
    return src[idx] if 0 <= idx < len(src) else ""


def base_url(extra: dict, kind: str, idx: int) -> str:
    """편집할 바탕 — 이미 편집했으면 그 바탕 그대로(편집은 매번 바탕에서 다시 — 겹쳐 굽지 않는다), 아니면 지금 나가는 장
    (번역본을 쓰면 번역본 · 아니면 원본)."""
    e = _entry(extra, kind, idx) or {}
    ed = e.get("edit") if isinstance(e.get("edit"), dict) else {}
    if ed.get("base"):
        return str(ed["base"])
    if e.get("use") and e.get("status") == "done" and e.get("url"):
        return str(e["url"])
    return _original(extra, kind, idx)


def _load_small(url: str):
    """`(작은 RGB 그림, (W, H))` — 미리보기·색 판정용(긴 변 256px). 못 받으면 `(None, (0, 0))`."""
    try:
        import requests
        from src.collectors.image_norm import open_small
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.content:
            return None, (0, 0)
        from PIL import Image
        with Image.open(io.BytesIO(r.content)) as im0:
            W, H = im0.size
        im, _f, _w, _h, _why = open_small(r.content, SMALL_SIDE)
        if im is None:
            return None, (W, H)
        return im.convert("RGB"), (W, H)
    except Exception as exc:                                    # noqa: BLE001
        logger.info("[사진 편집] 미리보기 못 받음 %s: %s", url[:80], type(exc).__name__)
        return None, (0, 0)


def _components(mask, w: int, h: int, min_px: int) -> List[Tuple[int, int, int, int, int]]:
    """4-이웃 연결 성분 → `[(x0, y0, x1, y1, 화소수)]`."""
    seen = bytearray(w * h)
    out = []
    for start in range(w * h):
        if not mask[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        x0 = y0 = 10 ** 9
        x1 = y1 = n = 0
        while stack:
            p = stack.pop()
            y, x = divmod(p, w)
            n += 1
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
            for q in ((p - 1) if x > 0 else -1, (p + 1) if x < w - 1 else -1, (p - w) if y > 0 else -1, (p + w) if y < h - 1 else -1):
                if q >= 0 and mask[q] and not seen[q]:
                    seen[q] = 1
                    stack.append(q)
        if n >= min_px:
            out.append((x0, y0, x1, y1, n))
    return out


def subject_bbox(small) -> Optional[Dict]:
    """대표 피사체 상자(작은 그림 좌표) — 가장자리 색(배경)과 다른 화소의 가장 큰 덩어리. 못 잡으면 None(→ 자동 지우기 안 함)."""
    if small is None:
        return None
    w, h = small.size
    px = list(small.getdata())
    border = [px[i] for i in range(w)] + [px[(h - 1) * w + i] for i in range(w)] + \
             [px[j * w] for j in range(h)] + [px[j * w + w - 1] for j in range(h)]
    bg = tuple(sorted(c[k] for c in border)[len(border) // 2] for k in range(3))
    mask = bytearray(1 if max(abs(p[0] - bg[0]), abs(p[1] - bg[1]), abs(p[2] - bg[2])) > 40 else 0 for p in px)
    comps = _components(mask, w, h, max(8, (w * h) // 400))
    if not comps:
        return None
    x0, y0, x1, y1, n = max(comps, key=lambda c: c[4])
    if n > w * h * 0.92 or n < w * h * 0.02:
        return None                                           # 사진 거의 전체가 덩어리(배경을 못 잡음) · 너무 작음
    return {"x": x0, "y": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1, "space": [w, h]}


def color_badges(small) -> List[Dict]:
    """쿠폰 스티커처럼 채도 높은(빨강·주황·노랑) 꽉 찬 사각 — 작은 그림 좌표 `[{x,y,w,h}]`."""
    if small is None:
        return []
    import colorsys
    w, h = small.size
    mask = bytearray(w * h)
    for i, (r, g, b) in enumerate(small.getdata()):
        hh, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0.45 and v > 0.35 and (hh < 0.17 or hh > 0.93):
            mask[i] = 1
    out = []
    for x0, y0, x1, y1, n in _components(mask, w, h, max(6, (w * h) // 600)):
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        area = bw * bh
        if not (w * h * 0.003 <= area <= w * h * 0.15):
            continue
        if n / area < 0.55 or not (0.25 <= bw / bh <= 5):
            continue
        out.append({"x": x0, "y": y0, "w": bw, "h": bh})
    return out


def _brand_names(extra: dict) -> List[str]:
    import re
    names = [str(extra.get("brand") or "").strip()]
    m = re.match(r"\s*([A-Za-z][A-Za-z0-9&\-]{2,})", str(extra.get("title_ko") or extra.get("title") or ""))
    if m:
        names.append(m.group(1))
    return [n for n in names if n and n.upper() not in ("GENERIC", "OTHER", "其他", "无")]


def classify(text: str, extra: dict) -> str:
    t = str(text or "")
    try:
        from src.collectors.ko_polish import promo_hits
        from src.services.detail_image_plan import STORE_UI
        if promo_hits(t) or any(k in t for k in STORE_UI):
            return "promo"
    except Exception:                                           # noqa: BLE001
        pass
    try:
        from src.services import risk_gate as _rg
        for e in _rg._trademark_entries():
            if _rg._find(t, e.get("names") or [], bool(e.get("case"))):
                return "risk"
    except Exception:                                           # noqa: BLE001
        pass
    low = t.lower()
    if any(b.lower() in low for b in _brand_names(extra)):
        return "brand"
    return "text"


def _overlaps(a: Dict, b: Optional[Dict]) -> bool:
    if not b:
        return True                                           # 제품 영역을 모르면 「겹친다」로(자동으로 안 지운다)
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def ensure_boxes(extra: dict, kind: str, idx: int) -> Dict:
    """그 장의 글자 상자 — 저장된 것(`boxes`·`box_size`) · 없으면 텐센트 OCR로 한 번 읽어 저장(`boxes_source: ocr`)."""
    e = _entry(extra, kind, idx) or {}
    if isinstance(e.get("boxes"), list) and e.get("box_size"):
        return {"ok": True, "boxes": e["boxes"], "size": e["box_size"], "source": e.get("boxes_source") or "translate"}
    url = base_url(extra, kind, idx)
    if not url:
        return {"ok": False, "why": "사진 주소가 없어요", "boxes": [], "size": [0, 0]}
    try:
        import requests
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        raw = r.content if r.status_code == 200 else b""
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "why": f"사진을 받지 못했어요({type(exc).__name__})", "boxes": [], "size": [0, 0]}
    from src.services import ocr_tencent as O
    got = O.read_boxes(raw)
    if not got.get("ok"):
        return {"ok": False, "why": got.get("why") or "글자 상자를 읽지 못했어요", "boxes": [], "size": [0, 0]}
    e = _entry(extra, kind, idx, create=True)
    e.update(boxes=got["boxes"], box_size=got["size"], boxes_source="ocr", boxes_at=datetime.now(timezone.utc).isoformat())
    if not e.get("source_text"):
        e["ocr_text"] = " ".join(b["src"] for b in got["boxes"])[:2000]
    return {"ok": True, "boxes": got["boxes"], "size": got["size"], "source": "ocr"}


def plan(extra: dict, kind: str, idx: int, *, small=None, fetch: bool = True) -> Dict:
    """화면·자동 공용 — `{url, size, boxes:[{id,x,y,w,h,text,cls,cls_label,auto,in_subject}], subject, edit, cost, today, cap}`.
    좌표는 바탕 사진(`size`) 기준. `auto` = 판촉 + 제품 영역 밖(자동 지우기 대상)."""
    url = base_url(extra, kind, idx)
    e0 = _entry(extra, kind, idx) or {}
    if fetch or (isinstance(e0.get("boxes"), list) and e0.get("box_size")):
        bx = ensure_boxes(extra, kind, idx)                     # 저장된 상자는 OCR 없이 그대로
    else:
        bx = {"ok": False, "boxes": [], "size": [0, 0]}
    if small is None and fetch and url:
        small, real = _load_small(url)
    else:
        real = (0, 0)
    W, H = (bx.get("size") or [0, 0]) if bx.get("ok") else (0, 0)
    W, H = W or real[0], H or real[1]
    subj = None
    if small is not None and W and H:
        sb = subject_bbox(small)
        if sb:
            kx, ky = W / sb["space"][0], H / sb["space"][1]
            subj = {"x": int(sb["x"] * kx), "y": int(sb["y"] * ky), "w": int(sb["w"] * kx), "h": int(sb["h"] * ky)}
    boxes = []
    for i, b in enumerate(bx.get("boxes") or []):
        text = " ".join(x for x in (str(b.get("src") or ""), str(b.get("tgt") or "")) if x)
        cls = classify(text, extra)
        box = {"x": int(b.get("x") or 0), "y": int(b.get("y") or 0), "w": int(b.get("w") or 0), "h": int(b.get("h") or 0)}
        inside = _overlaps(box, subj)
        boxes.append(dict(box, id=f"t{i}", text=text[:120], src=str(b.get("src") or ""), tgt=str(b.get("tgt") or ""),
                          cls=cls, cls_label=CLASS_LABEL[cls], in_subject=inside, auto=(cls == "promo" and not inside)))
    if small is not None and W and H:
        sw, sh = small.size
        for j, c in enumerate(color_badges(small)):
            box = {"x": int(c["x"] * W / sw), "y": int(c["y"] * H / sh), "w": int(c["w"] * W / sw), "h": int(c["h"] * H / sh)}
            if any(_iou(box, t) > 0.3 for t in boxes):
                continue                                      # 글자 상자와 같은 자리 — 하나만
            inside = _overlaps(box, subj)
            boxes.append(dict(box, id=f"c{j}", text="", src="", tgt="", cls="promo", cls_label="판촉 배지",
                              in_subject=inside, auto=not inside))
    e = _entry(extra, kind, idx) or {}
    ed = e.get("edit") if isinstance(e.get("edit"), dict) else None
    return {"ok": bool(boxes) or bool(bx.get("ok")), "why": bx.get("why", ""), "url": url, "size": [W, H], "boxes": boxes,
            "subject": subj, "edit": ed, "cost": cost(0), "today": today_count(), "cap": daily_cap(),
            "spent": round(sum(float(x.get("credits") or 0) for x in (ed or {}).get("history") or []), 3) if ed else 0.0}


def _iou(a: Dict, b: Dict) -> float:
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    u = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / u if u else 0.0


# ── 적용 ───────────────────────────────────────────────────────────────────────────────────

def _text_color(small, box: Dict, size) -> str:
    """원래 글자색 — 상자 안에서 상자 가장자리 색(바탕)과 가장 먼 화소들의 가운데 값. 못 재면 짙은 회색."""
    if small is None or not size[0] or not size[1]:
        return "333333"
    sw, sh = small.size
    x0, y0 = int(box["x"] * sw / size[0]), int(box["y"] * sh / size[1])
    x1, y1 = max(x0 + 1, int((box["x"] + box["w"]) * sw / size[0])), max(y0 + 1, int((box["y"] + box["h"]) * sh / size[1]))
    pts = [small.getpixel((x, y)) for y in range(y0, min(y1, sh)) for x in range(x0, min(x1, sw))]
    if not pts:
        return "333333"
    edge = [small.getpixel((x, y)) for x in range(x0, min(x1, sw)) for y in (y0, min(y1, sh) - 1)]
    bg = tuple(sorted(p[k] for p in edge)[len(edge) // 2] for k in range(3))
    far = sorted(pts, key=lambda p: -max(abs(p[0] - bg[0]), abs(p[1] - bg[1]), abs(p[2] - bg[2])))[: max(1, len(pts) // 6)]
    med = tuple(sorted(p[k] for p in far)[len(far) // 2] for k in range(3))
    return "%02x%02x%02x" % med


def _text_layer(text: str, box: Dict, color: str) -> str:
    """Noto Sans KR 글자 — 상자 높이의 80%에서 시작해 폭에 맞춰 줄인다(최소 10px). Cloudinary 글자 오버레이 문법."""
    n = max(1, len(text))
    size = int(box["h"] * 0.8)
    if n * size * 0.92 > box["w"]:
        size = int(box["w"] / (n * 0.92))
    size = max(10, size)
    enc = quote(text, safe="").replace("%2C", "%252C").replace("%2F", "%252F")
    font = quote(FONT, safe="")
    return (f"l_text:{font}_{size}_bold:{enc},co_rgb:{color}/"
            f"fl_layer_apply,g_north_west,x_{max(0, box['x'])},y_{max(0, box['y'] + max(0, (box['h'] - size) // 2))}")


def build_transform(erase: List[Dict], texts: List[Tuple[Dict, str, str]], scale: float = 1.0) -> str:
    """`e_gen_remove:region_(…)` + 글자 얹기들 — Cloudinary raw transformation 한 줄. 좌표는 업로드된 사진 크기 기준(`scale`)."""
    from src.services.image_gen_remove import region_param
    sc = lambda b: {k: int(round(b[k] * scale)) for k in ("x", "y", "w", "h")}
    rects = [sc(b) for b in erase] + [sc(b) for b, _t, _c in texts]
    region = region_param([(r["x"], r["y"], r["w"], r["h"]) for r in rects])
    parts = [f"e_gen_remove:{region}"] if region else []
    for b, t, c in texts:
        parts.append(_text_layer(t, sc(b), c))
    return "/".join(parts)


def _ready(url: str) -> Tuple[bool, Optional[int]]:
    """파생본이 준비됐나 — HEAD(본문 안 받음). 420/423이면 짧게 기다린다(D3와 같은 규칙: 3번 · 2초)."""
    import requests
    code = None
    for i in range(3):
        try:
            code = requests.head(url, timeout=20, allow_redirects=True).status_code
        except Exception:                                       # noqa: BLE001
            return False, None
        if code == 200:
            return True, code
        if code in (420, 423) and i < 2:
            time.sleep(2.0)
            continue
        break
    return False, code


def apply(extra: dict, kind: str, idx: int, ops: List[Dict], *, by: str = "user", small=None) -> Dict:
    """`ops=[{id, action: erase|text, text?}]` → 편집본. 바탕에서 **지금까지의 편집 + 이번 편집**을 한 번에 다시 굽는다.
    결과 `{ok, url, credits, erased, error?}`. 저장은 호출부(이 dict를 바꿨으니 extra_json을 저장)."""
    ok_c, why = configured()
    if not ok_c:
        return {"ok": False, "error": "사진 편집을 쓸 수 없어요 — " + why}
    from src.db import image_translate_queue_pg as q
    took, today = q.take_start(_day_key(), daily_cap())
    if not took:
        return {"ok": False, "error": f"오늘 사진 편집 한도({daily_cap()}회)를 다 썼어요 — 내일 다시 해 주세요", "today": today}
    p = plan(extra, kind, idx, small=small)
    by_id = {b["id"]: b for b in p["boxes"]}
    e = _entry(extra, kind, idx, create=True)
    prev = e.get("edit") if isinstance(e.get("edit"), dict) else {}
    keep = [o for o in (prev.get("ops") or []) if o.get("id") not in {x.get("id") for x in ops}]
    all_ops = [o for o in keep + list(ops) if o.get("action") in ("erase", "text") and o.get("id") in by_id]
    if not all_ops:
        return {"ok": False, "error": "고를 상자가 없어요"}
    if small is None:
        small, _ = _load_small(p["url"])
    erase = [by_id[o["id"]] for o in all_ops if o["action"] == "erase"]
    texts = [(by_id[o["id"]], str(o.get("text") or "")[:40], _text_color(small, by_id[o["id"]], p["size"]))
             for o in all_ops if o["action"] == "text" and str(o.get("text") or "").strip()]
    W, H = p["size"]
    from src.media.image_pipeline import remote_max_side, upload_remote
    side = remote_max_side()
    scale = min(1.0, side / max(W, H)) if (W and H and side > 0) else 1.0
    tr = build_transform(erase, texts, scale)
    up = upload_remote(p["url"], folder="edit", eager=[{"raw_transformation": tr}])
    if not up.get("ok"):
        return {"ok": False, "error": "편집 요청 실패 — " + (up.get("error") or "사유 불명")}
    url = ""
    for x in up.get("eager") or []:
        if isinstance(x, dict) and (x.get("secure_url") or x.get("url")):
            url = str(x.get("secure_url") or x.get("url"))
            break
    if not url:
        return {"ok": False, "error": "편집본 주소가 돌아오지 않았어요 — 응답 키: " + ", ".join(up.get("keys") or [])}
    ready, code = _ready(url)
    c = cost(len(texts))
    now = datetime.now(timezone.utc).isoformat()
    if not prev:
        prev = {"base": p["url"], "prev_url": e.get("url") or "", "prev_use": e.get("use"), "prev_status": e.get("status"),
                "created": not bool(e.get("status")), "history": []}
    erased = [x for b in erase + [t[0] for t in texts] for x in (b.get("src"), b.get("tgt")) if x]
    prev.update(url=url, by=by, at=now, ops=all_ops, erased=erased, transform=tr,
                ready=ready, http_status=code, credits=round(sum(float(h.get("credits") or 0) for h in prev.get("history") or []) + c["credits"], 3))
    prev.setdefault("history", []).append({"at": now, "by": by, "credits": c["credits"], "ops": len(all_ops)})
    e["edit"] = prev
    e.update(url=url, use=True, status="done")
    e.setdefault("vendor", "edit")
    return {"ok": True, "url": url, "ready": ready, "credits": c["credits"], "spent": prev["credits"], "erased": erased,
            "today": today, "cap": daily_cap()}


def revert(extra: dict, kind: str, idx: int) -> Dict:
    e = _entry(extra, kind, idx)
    ed = (e or {}).get("edit") if isinstance((e or {}).get("edit"), dict) else None
    if not ed:
        return {"ok": False, "error": "되돌릴 편집이 없어요"}
    if ed.get("created"):
        key = "images_ko" if kind == "gallery" else "detail_images_ko"
        extra[key] = [x for x in extra.get(key) or [] if x is not e]
    else:
        e["url"], e["use"] = ed.get("prev_url") or "", ed.get("prev_use")
        if ed.get("prev_status"):
            e["status"] = ed["prev_status"]
        e.pop("edit", None)
    return {"ok": True}


def auto_promo(extra: dict, *, kinds=("gallery",), max_images: int = 3, small_loader=None) -> List[Dict]:
    """자동 1차 — 판촉 의심 장마다 「판촉 + 제품 영역 밖」 상자만 지운 편집본(by auto). 이미 편집했거나 「그래도 넣기」면 건너뜀.
    결과 `[{kind, idx, url, erased_n, credits} | {kind, idx, skipped: 사유}]`."""
    from src.services.image_translate_store import promo_of
    out = []
    for kind in kinds:
        key = "images_ko" if kind == "gallery" else "detail_images_ko"
        for e in list(extra.get(key) or []):
            if len(out) >= max_images:
                return out
            if not isinstance(e, dict) or e.get("edit") or e.get("promo_include") or not promo_of(e):
                continue
            idx = int(e.get("idx", -1))
            small = small_loader(base_url(extra, kind, idx)) if small_loader else None
            p = plan(extra, kind, idx, small=small)
            auto = [b for b in p["boxes"] if b["auto"]]
            if not auto:
                out.append({"kind": kind, "idx": idx, "skipped": "제품과 겹치는 판촉 상자뿐 — 사용자 선택" if any(
                    b["cls"] == "promo" for b in p["boxes"]) else (p.get("why") or "판촉 상자를 못 찾음")})
                continue
            r = apply(extra, kind, idx, [{"id": b["id"], "action": "erase"} for b in auto], by="auto", small=small)
            out.append({"kind": kind, "idx": idx, "url": r.get("url", ""), "erased_n": len(auto), "credits": r.get("credits", 0),
                        "error": r.get("error", "")} if r.get("ok") else {"kind": kind, "idx": idx, "skipped": r.get("error")})
    return out
