"""Y11(오너 2026-10-14) — 사진 편집: 글자 상자를 탭해서 지우기·고치기. Y11-B·Y11-E 규칙이 우선한다.

Y11-B 실측 14:49 VRSUK: 색 덩어리 검출기가 의자 등받이·좌판을 「판촉 배지」로 잡았고 지우기가 적용돼 **제품 일부가 지워졌다**.
Y11-E 실측 17:36 VRSUK 갤러리 3: 거꾸로 놓인 책등 글자의 상자가 **180° 돌린 자리(빈 벽)**에 떠서 그 벽을 지웠다
(텐센트가 돌려 세운 그림 기준 좌표를 줬다 — `box_frame`). 원본은 그대로였다(수집 원본 사본·픽셀 비교로 확인).

- **버전**(Y11-E): 사진마다 「수집 원본 / 번역본 / 편집본 n」. 수집 원본(`extra.images[idx]`)은 어떤 코드도 덮어쓰지 않는다.
  번역본 주소는 `translated_url`에 따로 남고, 편집은 **고른 버전 위에** 새 편집본을 하나 더 만든다(`edits[]`).
  「원본으로」 = 수집 원본을 연다(나가는 사진도 원본) · 「되돌리기」 = 바로 전 버전(그 편집본을 만든 바탕).
- **상자는 버전에 붙는다**: 번역본 상자 = 번역 결과의 줄 상자(좌표 틀 확인 끝난 것) · 원본·편집본 상자 = 그 그림을 OCR로 읽은 것.
  상자 기록에는 잰 그림 주소(`img`)가 있고, 그림이 바뀌면 그 상자는 쓰지 않는다(빈 벽에 상자 금지).
- **자동 픽셀 변경 없음**(Y11-E): 자동 지우기·`IMAGE_EDIT_AUTO`는 없앴다. 자동은 번역(별도 버전)뿐 —
  지우기·고치기는 사람이 상자를 탭해서 적용할 때만.
- 지울 영역 = 글자 상자 + 상자 높이의 10% 여유(사방) — 그 밖은 건드리지 않는다. 화면이 적용 전에 그 영역을 빨갛게 보여 주고 한 번 더 묻는다.
- 지우기 = Cloudinary `gen_remove`(영역 지정) · 글자 고치기 = 같은 자리 지운 뒤 Noto Sans KR 글자(상자에 맞춰 크기 · 원래 글자색).
- 비용: 편집 한 번 = (50 + 1 + 글자 수) 변환 / 1,000 = 약 0.051 크레딧. 하루 상한 `IMAGE_EDIT_DAILY_CAP`(기본 200회).
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
#: 지울 영역 여유 — 상자 높이의 10%(사방). 그 밖은 절대 안 건드린다(오너 2026-10-14).
PAD_RATIO = 0.10
NO_TEXT_WHY = "이 사진에서 글자를 못 찾았어요 — 지울 것이 없어요"
#: Y11-C2: 건당 상한을 넘어 번역을 보내지 않은 장(원본) — 편집은 OCR 상자로
CAPPED_LABEL = "상한 — 번역 안 됨(원본)"
#: Y11-E 버전 이름
V_ORIGINAL, V_TRANSLATED = "original", "translated"
V_LABEL = {V_ORIGINAL: "수집 원본", V_TRANSLATED: "번역본"}


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


# ── 장 · 버전 ───────────────────────────────────────────────────────────────────────────────

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
    """수집 원본 — `extra.images`(상세면 `detail_images`)의 그 장. **읽기만 한다**(Y11-E: 원본 불변)."""
    src = [u for u in (extra.get("images" if kind == "gallery" else "detail_images") or []) if u]
    return src[idx] if 0 <= idx < len(src) else ""


def _is_edit_url(u: str) -> bool:
    return "/proxy-commerce/edit/" in str(u or "") or "e_gen_remove" in str(u or "")


def translated_url(e: Optional[dict]) -> str:
    """번역본 주소 — 새 장은 `translated_url`, 옛 장은 편집 전 주소(`edit.prev_url`)나 지금 주소에서."""
    e = e or {}
    if e.get("translated_url"):
        return str(e["translated_url"])
    ed = e.get("edit") if isinstance(e.get("edit"), dict) else None
    if ed:
        pu = str(ed.get("prev_url") or "")
        return pu if ed.get("prev_status") == "done" and pu and not _is_edit_url(pu) else ""
    if e.get("status") == "done" and e.get("url") and not _is_edit_url(e["url"]):
        return str(e["url"])
    return ""


def edits(e: Optional[dict]) -> List[Dict]:
    """편집본 목록 `[{n, url, base, base_key, at, by, ops, erased, credits, ready, transform}]` — 옛 장(`edit` 하나)은 1개로."""
    e = e or {}
    if isinstance(e.get("edits"), list):
        return [x for x in e["edits"] if isinstance(x, dict)]
    ed = e.get("edit") if isinstance(e.get("edit"), dict) else None
    url = (ed or {}).get("url") or (e.get("url") if ed and _is_edit_url(e.get("url")) else "")
    if not ed or not url:
        return []
    tu = translated_url(e)
    return [{"n": 1, "url": url, "base": ed.get("base") or "",
             "base_key": V_TRANSLATED if tu and ed.get("base") == tu else V_ORIGINAL,
             "at": ed.get("at") or "", "by": ed.get("by") or "", "ops": list(ed.get("ops") or []),
             "erased": list(ed.get("erased") or []), "credits": ed.get("credits") or 0,
             "ready": ed.get("ready"), "transform": ed.get("transform") or ""}]


def current_key(e: Optional[dict]) -> str:
    """지금 고른(= 나가는) 버전 — 늘 `use`·`url`에서 읽는다(번역본 켜기·끄기 토글이 `use`만 바꿔도 맞게)."""
    e = e or {}
    if not e.get("use") or e.get("status") != "done" or not e.get("url"):
        return V_ORIGINAL
    for x in edits(e):
        if x["url"] == e["url"]:
            return f"edit:{x['n']}"
    return V_TRANSLATED if translated_url(e) else V_ORIGINAL


def versions(extra: dict, kind: str, idx: int) -> List[Dict]:
    """`[{key, label, url, at?, by?}]` — 수집 원본 · 번역본(있으면) · 편집본 n."""
    e = _entry(extra, kind, idx) or {}
    out = [{"key": V_ORIGINAL, "label": V_LABEL[V_ORIGINAL], "url": _original(extra, kind, idx)}]
    tu = translated_url(e)
    if tu:
        out.append({"key": V_TRANSLATED, "label": V_LABEL[V_TRANSLATED], "url": tu, "at": e.get("at") or ""})
    for x in edits(e):
        out.append({"key": f"edit:{x['n']}", "label": f"편집본 {x['n']}", "url": x["url"], "at": x.get("at") or "",
                    "by": x.get("by") or "", "base_key": x.get("base_key") or V_ORIGINAL, "ready": x.get("ready")})
    return out


def _version(extra: dict, kind: str, idx: int, key: str) -> Optional[Dict]:
    return next((v for v in versions(extra, kind, idx) if v["key"] == key), None)


def _normalize(e: dict) -> None:
    """옛 모양(`edit` 하나) → 버전 모양으로 적어 둔다(번역본 주소·편집본 목록·지금 버전)."""
    tu, eds, cur = translated_url(e), edits(e), current_key(e)
    if tu:
        e["translated_url"] = tu
    e["edits"] = eds
    e["current"] = cur


def select(extra: dict, kind: str, idx: int, key: str) -> Dict:
    """그 버전을 고른다(= 나가는 사진). 수집 원본은 **읽기만** — 원본을 고르면 번역본·편집본을 안 쓸 뿐이다."""
    v = _version(extra, kind, idx, key)
    if not v or not v.get("url"):
        return {"ok": False, "error": "그 버전이 없어요"}
    e = _entry(extra, kind, idx)
    if e is None:
        if key == V_ORIGINAL:
            return {"ok": True, "current": key}                # 손댄 적 없는 장 — 원래 원본
        return {"ok": False, "error": "그 버전이 없어요"}
    _normalize(e)
    if key == V_ORIGINAL:
        e["use"] = False
        e.pop("edit", None)
    elif key == V_TRANSLATED:
        e.update(url=v["url"], use=True, status="done")
        e.pop("edit", None)
    else:
        ed = next(x for x in e["edits"] if f"edit:{x['n']}" == key)
        e.update(url=ed["url"], use=True, status="done")
        e["edit"] = dict(ed)                                    # 지금 나가는 편집본(지운 글자 → 판촉·상표 검사에서 뺀다)
    e["current"] = key
    return {"ok": True, "current": key}


def revert(extra: dict, kind: str, idx: int) -> Dict:
    """「되돌리기」 = 바로 전 버전 — 편집본이면 그것을 만든 바탕, 번역본이면 수집 원본."""
    e = _entry(extra, kind, idx)
    cur = current_key(e)
    if cur.startswith("edit:"):
        ed = next((x for x in edits(e) if f"edit:{x['n']}" == cur), {})
        back = ed.get("base_key") or V_ORIGINAL
        if not _version(extra, kind, idx, back):
            back = V_ORIGINAL
    elif cur == V_TRANSLATED:
        back = V_ORIGINAL
    else:
        return {"ok": False, "error": "더 되돌릴 버전이 없어요 — 지금이 수집 원본이에요"}
    r = select(extra, kind, idx, back)
    return dict(r, back=back)


def base_url(extra: dict, kind: str, idx: int) -> str:
    """편집할 바탕 = 지금 고른 버전의 그림."""
    v = _version(extra, kind, idx, current_key(_entry(extra, kind, idx)))
    return (v or {}).get("url") or _original(extra, kind, idx)


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


def erase_rect(box: Dict, size) -> Dict:
    """지울 영역 = 글자 상자 + 상자 높이의 10% 여유(사방), 사진 밖은 자른다. **이 밖은 절대 안 건드린다.**"""
    W, H = (size or [0, 0])[:2]
    pad = max(1, int(round(box["h"] * PAD_RATIO)))
    x0, y0 = max(0, box["x"] - pad), max(0, box["y"] - pad)
    x1, y1 = box["x"] + box["w"] + pad, box["y"] + box["h"] + pad
    if W:
        x1 = min(W, x1)
    if H:
        y1 = min(H, y1)
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}



# ── 상자(버전마다) ─────────────────────────────────────────────────────────────────────────

def _fetch(url: str) -> bytes:
    """그림 바이트 — 우리 번역본 주소(내부)도 읽는다. 못 받으면 b""."""
    try:
        from src.services.coupang_image_check import _bytes_for
        raw, _why = _bytes_for(url)
        return raw or b""
    except Exception:                                           # noqa: BLE001
        return b""


def _verify_translated(extra: dict, kind: str, idx: int, e: dict) -> bool:
    """옛 번역본 상자(좌표 틀을 확인한 적 없는 것) — 수집 원본↔번역본 차이로 틀을 확인해 고친다. 확인 못 하면 상자를 버린다."""
    from src.services import box_frame as BF
    tu = translated_url(e)
    orig, trans = _fetch(_original(extra, kind, idx)), _fetch(tu) if tu else b""
    got = BF.pick(orig, trans, e.get("boxes") or []) if (orig and trans) else {"frame": "unknown", "boxes": [], "scores": {}}
    if got["frame"] == "unknown":
        logger.info("[사진 편집] 옛 번역본 상자 틀 확인 못 함 → 버림(빈 벽 상자 방지) idx=%s %s", idx, got.get("scores"))
        e["box_frame"] = "unknown"
        e["boxes_dropped"] = {"n": len(e.get("boxes") or []), "at": datetime.now(timezone.utc).isoformat(),
                              "why": got.get("why") or "원본·번역본을 받지 못해 상자 자리를 확인 못 함"}
        e.pop("boxes", None)
        e.pop("box_size", None)
        return False
    if got["frame"] != "identity":
        logger.info("[사진 편집] 옛 번역본 상자 틀 %s 로 바로잡음 idx=%s %s", got["frame"], idx, got.get("scores"))
        e["boxes"] = [{k: b[k] for k in b if k != "i"} for b in got["boxes"]]
    e["box_frame"], e["boxes_img"] = got["frame"], tu
    return True


def _ocr_version(url: str) -> Dict:
    """그 그림을 OCR로 읽은 상자 `{ok, boxes, size, why, code}` — 기록 모양으로."""
    from src.services import ocr_tencent as O
    if O.unopened():
        return {"ok": False, "why": O.UNOPEN_WHY, "code": "ocr_unopened", "boxes": [], "size": [0, 0]}
    try:
        import requests
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        raw = r.content if r.status_code == 200 else b""
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "why": f"사진을 받지 못했어요({type(exc).__name__})", "boxes": [], "size": [0, 0]}
    if not raw:
        raw = _fetch(url)
    got = O.read_boxes(raw)
    del raw
    return got


def ensure_boxes(extra: dict, kind: str, idx: int) -> Dict:
    """**지금 고른 버전**의 글자 상자 — `{ok, boxes, size, source, why, need_translate, capped, version}`.

    번역본: 번역 결과의 줄 상자(틀 확인된 것만 · 옛 것은 확인 → 못 하면 버리고 OCR). 수집 원본·편집본: 그 그림을 OCR로(한 번 읽어 저장).
    상자 기록의 `img`가 지금 그림과 다르면 쓰지 않는다 — 그림이 바뀌면 상자도 다시."""
    e = _entry(extra, kind, idx) or {}
    key = current_key(e)
    url = base_url(extra, kind, idx)
    from src.services.image_translate_auto import _is_pwt, per_item_cap
    if key == V_ORIGINAL and e.get("status") in ("failed", "skipped") and _is_pwt(e):
        return {"ok": True, "boxes": [], "size": [0, 0], "source": "translate", "why": NO_TEXT_WHY, "version": key}
    capped = int(idx) >= per_item_cap(kind) and not translated_url(e)
    if key == V_TRANSLATED and isinstance(e.get("boxes"), list) and e.get("box_size"):
        ok_frame = e.get("box_frame") not in (None, "", "unknown") or _verify_translated(extra, kind, idx, e)
        img = e.get("boxes_img") or translated_url(e)
        if ok_frame and img == url:
            return {"ok": True, "boxes": e["boxes"], "size": e["box_size"], "source": e.get("boxes_source") or "translate",
                    "why": "" if e["boxes"] else NO_TEXT_WHY, "version": key, "frame": e.get("box_frame")}
    if key == V_ORIGINAL and not capped and not translated_url(e):
        # 번역이 먼저(Y11-B) — 번역 전 장은 「번역해서 글자 상자 받기」. (상한을 넘은 장·번역본이 있는데 원본을 고른 장은 OCR)
        return {"ok": False, "boxes": [], "size": [0, 0], "need_translate": True, "version": key,
                "why": "아직 이 사진을 번역하지 않았어요 — 번역하면 글자 상자를 받아요(번역이 먼저예요)"}
    rec = (e.get("vboxes") or {}).get(key) if isinstance(e.get("vboxes"), dict) else None
    if isinstance(rec, dict) and rec.get("img") == url and isinstance(rec.get("boxes"), list):
        return {"ok": True, "boxes": rec["boxes"], "size": rec.get("size") or [0, 0], "source": "ocr", "capped": capped,
                "why": "" if rec["boxes"] else NO_TEXT_WHY, "version": key}
    if not url:
        return {"ok": False, "why": "사진 주소가 없어요", "boxes": [], "size": [0, 0], "capped": capped, "version": key}
    got = _ocr_version(url)
    if not got.get("ok"):
        why = got.get("why") or "글자 상자를 읽지 못했어요"
        if capped:
            return {"ok": False, "why": CAPPED_LABEL + " · " + why, "boxes": [], "size": [0, 0], "capped": True, "version": key}
        if key != V_TRANSLATED and (key.startswith("edit:") or translated_url(e)):
            # 편집본·(번역본이 있는) 수집 원본 — 번역을 다시 보낼 일이 아니다. 번역본을 고르면 그 상자를 쓴다.
            tail = " · 「번역본」을 고르면 번역 결과의 글자 상자를 써요" if translated_url(e) else ""
            what = "이 편집본" if key.startswith("edit:") else "수집 원본"
            return {"ok": False, "why": f"{what}의 글자 상자를 읽지 못했어요({why})" + tail, "boxes": [], "size": [0, 0],
                    "version": key}
        tail = " · 개통 전에는 다시 번역하면 번역 결과의 글자 상자를 써요" if got.get("code") == "ocr_unopened" else \
               " · 다시 번역하면 번역 결과의 글자 상자를 써요"
        return {"ok": False, "why": why + tail, "boxes": [], "size": [0, 0], "need_translate": True, "version": key}
    e = _entry(extra, kind, idx, create=True)
    vb = e.setdefault("vboxes", {}) if isinstance(e.get("vboxes"), dict) else e.setdefault("vboxes", {})
    vb[key] = {"boxes": got["boxes"], "size": got["size"], "img": url, "source": "ocr",
               "at": datetime.now(timezone.utc).isoformat(), "angle": got.get("angle", 0)}
    if not e.get("source_text"):
        e["ocr_text"] = " ".join(b["src"] for b in got["boxes"])[:2000]
    return {"ok": True, "boxes": got["boxes"], "size": got["size"], "source": "ocr", "capped": capped,
            "why": "" if got["boxes"] else NO_TEXT_WHY, "version": key}


def _cap_of(kind: str) -> int:
    from src.services.image_translate_auto import per_item_cap
    return per_item_cap(kind)


def legacy_ops(ed: Optional[dict]) -> bool:
    """Y11 첫판의 색 덩어리(`c#`) 상자로 만든 편집인가 — Y11-B 실측에서 제품을 지웠다."""
    return any(str(o.get("id") or "").startswith("c") for o in ((ed or {}).get("ops") or []) if isinstance(o, dict))


def drop_legacy_edits(extra: dict) -> List[Dict]:
    """색 덩어리 검출로 만든 편집본을 **버전 목록에서 빼고** 그 바탕으로 돌린다. 되돌린 장 `[{kind, idx, at}]` — 기록도 남긴다."""
    out = []
    for kind, key in (("gallery", "images_ko"), ("detail", "detail_images_ko")):
        for e in list(extra.get(key) or []):
            if not isinstance(e, dict):
                continue
            bad = [x for x in edits(e) if legacy_ops(x)]
            if not bad:
                continue
            idx = int(e.get("idx", -1))
            cur = current_key(e)
            _normalize(e)
            back = bad[0].get("base_key") or V_ORIGINAL
            e["edits"] = [x for x in e["edits"] if not legacy_ops(x)]
            if cur in {f"edit:{x['n']}" for x in bad}:
                select(extra, kind, idx, back if _version(extra, kind, idx, back) else V_ORIGINAL)
            out.append({"kind": kind, "idx": idx, "at": datetime.now(timezone.utc).isoformat()})
    if out:
        extra.setdefault("image_edit_reverted", []).extend(out)
        logger.info("[사진 편집] 색 덩어리 편집 되돌림 %s장", len(out))
    return out


def plan(extra: dict, kind: str, idx: int, *, small=None, fetch: bool = True, real=None) -> Dict:
    """화면 공용 — `{url, size, real, boxes:[{id,x,y,w,h,er,text,cls,cls_label}], why, need_translate, edit, versions,
    current, cost, today, cap}`. 좌표는 상자 공간(`size` = 그 버전 그림) 기준, `er` = 지울 영역(여유 포함)."""
    url = base_url(extra, kind, idx)
    e0 = _entry(extra, kind, idx) or {}
    if fetch or (isinstance(e0.get("boxes"), list) and e0.get("box_size")) or e0.get("vboxes"):
        bx = ensure_boxes(extra, kind, idx)                     # 저장된 상자는 OCR 없이 그대로
    else:
        bx = {"ok": False, "boxes": [], "size": [0, 0]}
    real = tuple(real or (0, 0))
    if small is None and fetch and url and (bx.get("boxes") or []):
        small, real = _load_small(url)                          # 글자색·바탕 크기 — 상자가 있을 때만 받는다
    W, H = (bx.get("size") or [0, 0]) if bx.get("ok") else (0, 0)
    W, H = W or real[0], H or real[1]
    boxes = []
    for i, b in enumerate(bx.get("boxes") or []):
        text = " ".join(x for x in (str(b.get("src") or ""), str(b.get("tgt") or "")) if x)
        cls = classify(text, extra)
        box = {"x": int(b.get("x") or 0), "y": int(b.get("y") or 0), "w": int(b.get("w") or 0), "h": int(b.get("h") or 0)}
        if box["w"] <= 0 or box["h"] <= 0:
            continue
        boxes.append(dict(box, id=f"t{i}", er=erase_rect(box, [W, H]), text=text[:120], src=str(b.get("src") or ""),
                          tgt=str(b.get("tgt") or ""), cls=cls, cls_label=CLASS_LABEL[cls]))
    e = _entry(extra, kind, idx) or {}
    cur = current_key(e)
    ed = next((x for x in edits(e) if f"edit:{x['n']}" == cur), None)
    why = bx.get("why") or ("" if boxes else NO_TEXT_WHY)
    capped = bool(bx.get("capped")) or (int(idx) >= _cap_of(kind) and not translated_url(e))
    return {"ok": True, "why": why, "need_translate": bool(bx.get("need_translate")), "source": bx.get("source", ""),
            "capped": capped, "capped_label": CAPPED_LABEL if capped else "",
            "url": url, "size": [W, H], "real": [int(real[0] or 0), int(real[1] or 0)], "boxes": boxes,
            "versions": versions(extra, kind, idx), "current": cur, "edit": ed,
            "cost": cost(0), "today": today_count(), "cap": daily_cap(),
            "spent": round(sum(float(x.get("credits") or 0) for x in edits(e)), 3)}


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
    """`e_gen_remove:region_(…)` + 글자 얹기들 — Cloudinary raw transformation 한 줄. 좌표는 업로드된 사진 크기 기준(`scale`).
    지울 영역은 상자의 `er`(상자 + 높이 10% 여유) — 그 밖은 영역에 넣지 않는다. 글자는 원래 상자 자리에."""
    from src.services.image_gen_remove import region_param
    sc = lambda b: {k: int(round(b[k] * scale)) for k in ("x", "y", "w", "h")}
    rects = [sc(b.get("er") or b) for b in erase] + [sc(b.get("er") or b) for b, _t, _c in texts]
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
    """`ops=[{id, action: erase|text, text?}]` → **새 편집본 하나**(지금 고른 버전 위에). 결과 `{ok, url, credits, erased, error?}`.
    사람이 상자를 탭해서 적용할 때만 부른다(자동 픽셀 변경 없음 — Y11-E). 저장은 호출부."""
    ok_c, why = configured()
    if not ok_c:
        return {"ok": False, "error": "사진 편집을 쓸 수 없어요 — " + why}
    p = plan(extra, kind, idx, small=small)
    by_id = {b["id"]: b for b in p["boxes"]}               # 지금 버전의 글자 상자(t#)만
    todo = [o for o in ops or [] if isinstance(o, dict) and o.get("action") in ("erase", "text") and o.get("id") in by_id]
    if not todo:
        return {"ok": False, "error": (p.get("why") or "지울 상자를 탭해서 골라 주세요") if not p["boxes"] else "지울 상자를 탭해서 골라 주세요"}
    from src.db import image_translate_queue_pg as q
    took, today = q.take_start(_day_key(), daily_cap())          # 한도는 실제로 보낼 때만 센다
    if not took:
        return {"ok": False, "error": f"오늘 사진 편집 한도({daily_cap()}회)를 다 썼어요 — 내일 다시 해 주세요", "today": today}
    if small is None and any(o["action"] == "text" for o in todo):
        small, _ = _load_small(p["url"])                    # 글자색 재기(글자 고치기가 있을 때만)
    erase = [by_id[o["id"]] for o in todo if o["action"] == "erase"]
    texts = [(by_id[o["id"]], str(o.get("text") or "")[:40], _text_color(small, by_id[o["id"]], p["size"]))
             for o in todo if o["action"] == "text" and str(o.get("text") or "").strip()]
    W, H = p["size"]
    RW, RH = (p.get("real") or [0, 0])[:2]
    if not (RW and RH):
        RW, RH = W, H                                          # 바탕 크기를 못 쟀으면 상자 공간 = 바탕
    from src.media.image_pipeline import remote_max_side, upload_remote
    side = remote_max_side()
    k = (RW / W) if W else 1.0                                 # 상자 공간 → 바탕 사진(바탕이 더 크면 키운다)
    scale = k * (min(1.0, side / max(RW, RH)) if (RW and RH and side > 0) else 1.0)
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
    e = _entry(extra, kind, idx, create=True)
    base_key = current_key(e) if e.get("status") or e.get("current") else V_ORIGINAL
    _normalize(e)
    prev = next((x for x in e["edits"] if f"edit:{x['n']}" == base_key), None)
    erased = list((prev or {}).get("erased") or []) + [x for b in erase + [t[0] for t in texts] for x in (b.get("src"), b.get("tgt")) if x]
    n = max([int(x.get("n") or 0) for x in e["edits"]] + [0]) + 1
    now = datetime.now(timezone.utc).isoformat()
    e["edits"].append({"n": n, "url": url, "base": p["url"], "base_key": base_key, "at": now, "by": by, "ops": todo,
                       "erased": erased, "credits": c["credits"], "ready": ready, "http_status": code, "transform": tr})
    if not e.get("status"):
        e["status"] = "done"
    e.setdefault("vendor", "edit")
    select(extra, kind, idx, f"edit:{n}")
    spent = round(sum(float(x.get("credits") or 0) for x in e["edits"]), 3)
    return {"ok": True, "url": url, "ready": ready, "credits": c["credits"], "spent": spent, "erased": erased,
            "version": f"edit:{n}", "today": today, "cap": daily_cap()}
