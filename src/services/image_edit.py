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

import functools
import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENV_CAP = "IMAGE_EDIT_DAILY_CAP"
DEFAULT_CAP = 200
TX_BASE = 1
TX_PER_CREDIT = 1000
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
    """Y11-M: 지우기·글자는 우리 쪽에서 그린다 — Cloudinary엔 다 그린 그림을 일반 업로드 1번(변환·gen_remove 없음)."""
    tx = TX_BASE
    return {"tx": tx, "credits": round(tx / TX_PER_CREDIT, 3)}


def configured() -> Tuple[bool, str]:
    from src.services.image_gen_remove import configured as _c
    return _c()


# ── 장 · 버전 ───────────────────────────────────────────────────────────────────────────────

def _entry(extra: dict, kind: str, idx: int, create: bool = False) -> Optional[dict]:
    from src.services.image_translate_store import keys_of
    key = keys_of(kind)[1]
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
    from src.services.image_translate_store import originals_of
    src = originals_of(extra, kind)                               # Y11-U: SKU 사진 포함
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
        lab = "번역본(다듬음)" if x.get("by") == "polish" else f"편집본 {x['n']}"     # Y11-I: 자동 다듬기 버전
        out.append({"key": f"edit:{x['n']}", "label": lab, "url": x["url"], "at": x.get("at") or "",
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
    if v.get("ready") is False:
        # Y11-G(오너 19:16 캡처): 아직 만드는 중인 편집본을 고르면 빈 칸 + 「이미지 바이트 없음」이었다 — 고르지 않는다
        return {"ok": False, "pending": True, "error": "아직 만드는 중이에요 — 다 되면 칩이 켜져요"}
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
    if key != e.get("pending_select"):
        e.pop("pending_select", None)                            # 사람이 다른 버전을 골랐다 — 다 돼도 넘어가지 않는다
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
        from src.collectors.image_norm import abs_image_url, open_small
        r = requests.get(abs_image_url(url), timeout=15, headers={"User-Agent": "Mozilla/5.0"})
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
        from src.collectors.image_norm import abs_image_url
        r = requests.get(abs_image_url(url), timeout=20, headers={"User-Agent": "Mozilla/5.0"})
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
    if key == V_ORIGINAL and e.get("prop_only"):
        from src.services import prop_text as _pt
        if not _pt.exempt(extra):
            # Y11-G: 소품 글자뿐인 사진 — 글자가 아니다. 다시 번역(과금)을 권하지 않는다.
            return {"ok": True, "boxes": [], "size": [0, 0], "source": "translate", "version": key,
                    "why": "소품 글자뿐이에요(책등·표지 등) — 원본 그대로 나가요. 지울 글자가 없어요"}
    capped = int(idx) >= per_item_cap(kind) and not translated_url(e)
    if key == V_TRANSLATED and isinstance(e.get("boxes"), list) and e.get("box_size"):
        ok_frame = e.get("box_frame") not in (None, "", "unknown") or _verify_translated(extra, kind, idx, e)
        img = e.get("boxes_img") or translated_url(e)
        if ok_frame and img == url:
            return {"ok": True, "boxes": e["boxes"], "size": e["box_size"], "source": e.get("boxes_source") or "translate",
                    "why": "" if e["boxes"] else NO_TEXT_WHY, "version": key, "frame": e.get("box_frame")}
    if key == V_ORIGINAL and not capped and not translated_url(e) and not e.get("upside_down"):
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
        if key != V_TRANSLATED and (key.startswith("edit:") or translated_url(e) or e.get("upside_down")):
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


def _version_frame(extra: dict, kind: str, idx: int) -> str:
    """지금 버전 상자의 사진 회전 틀 — 번역본은 `box_frame`, OCR로 읽은 버전은 그때 OCR 각도(±45° 밖이면 돌아간 사진)."""
    e = _entry(extra, kind, idx) or {}
    key = current_key(e)
    if key == V_TRANSLATED:
        return str(e.get("box_frame") or "")
    rec = (e.get("vboxes") or {}).get(key) if isinstance(e.get("vboxes"), dict) else None
    try:
        ang = abs(float((rec or {}).get("angle") or 0.0))
    except (TypeError, ValueError):
        ang = 0.0
    return "rot180" if ang > 135 else ("rot90a" if ang > 45 else "")


def _cap_of(kind: str) -> int:
    from src.services.image_translate_auto import per_item_cap
    return per_item_cap(kind)


def legacy_ops(ed: Optional[dict]) -> bool:
    """Y11 첫판의 색 덩어리(`c#`) 상자로 만든 편집인가 — Y11-B 실측에서 제품을 지웠다."""
    return any(str(o.get("id") or "").startswith("c") for o in ((ed or {}).get("ops") or []) if isinstance(o, dict))


def drop_legacy_edits(extra: dict) -> List[Dict]:
    """색 덩어리 검출로 만든 편집본을 **버전 목록에서 빼고** 그 바탕으로 돌린다. 되돌린 장 `[{kind, idx, at}]` — 기록도 남긴다."""
    out = []
    for kind, key in (("gallery", "images_ko"), ("detail", "detail_images_ko"), ("sku", "sku_images_ko")):
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
    # Y11-G(오너): 소품(책등·책 표지·포장) 글자는 글자가 아니다 — 편집 상자에서 빼고(적용 개수에 안 듦) 「소품 글자 n개 보기」로만 회색 점선.
    from src.services import prop_text as PT
    prop_off = PT.exempt(extra)
    frame = _version_frame(extra, kind, idx)
    boxes, prop_boxes = [], []
    for i, b in enumerate(bx.get("boxes") or []):
        text = " ".join(x for x in (str(b.get("src") or ""), str(b.get("tgt") or "")) if x)
        box = {"x": int(b.get("x") or 0), "y": int(b.get("y") or 0), "w": int(b.get("w") or 0), "h": int(b.get("h") or 0)}
        if box["w"] <= 0 or box["h"] <= 0:
            continue
        if not prop_off and (b.get("prop") or PT.is_prop(dict(b), [W, H], frame=frame)):
            prop_boxes.append(dict(box, id=f"p{i}", text=text[:120]))
            continue
        cls = classify(text, extra)
        boxes.append(dict(box, id=f"t{i}", er=erase_rect(box, [W, H]), text=text[:120], src=str(b.get("src") or ""),
                          tgt=str(b.get("tgt") or ""), cls=cls, cls_label=CLASS_LABEL[cls]))
    e = _entry(extra, kind, idx) or {}
    cur = current_key(e)
    ed = next((x for x in edits(e) if f"edit:{x['n']}" == cur), None)
    why = bx.get("why") or ("" if boxes else NO_TEXT_WHY)
    if not boxes and prop_boxes and not bx.get("why"):
        why = "소품 글자만 있어요(책등·표지 등) — 지울 글자가 없어요"
    capped = bool(bx.get("capped")) or (int(idx) >= _cap_of(kind) and not translated_url(e))
    # Y11-H: 거꾸로 번역돼 원본으로 둔 장 — 「글자 고치기」 대상(머리글 상자를 탭해 한국어를 넣는다)
    fix_note = ("텐센트가 이 사진을 거꾸로 번역해 원본이 나가요 — 머리글 상자를 탭해 「글자 고치기」로 한국어를 넣어 주세요"
                if (e.get("upside_down") and cur == V_ORIGINAL) else "")
    return {"ok": True, "why": why, "need_translate": bool(bx.get("need_translate")), "source": bx.get("source", ""),
            "fix_text": bool(fix_note), "fix_note": fix_note,
            "polish": _polish_view(e),
            "capped": capped, "capped_label": CAPPED_LABEL if capped else "",
            "url": url, "size": [W, H], "real": [int(real[0] or 0), int(real[1] or 0)], "boxes": boxes, "prop_boxes": prop_boxes,
            "versions": versions(extra, kind, idx), "current": cur, "edit": ed,
            "cost": cost(0), "today": today_count(), "cap": daily_cap(),
            "spent": round(sum(float(x.get("credits") or 0) for x in edits(e)), 3)}


def _polish_view(e: dict) -> Optional[Dict]:
    """Y11-I 다듬기 기록 — 바뀐 상자·버린 상자만(그대로인 상자는 안 보인다)."""
    pl = e.get("polish") if isinstance(e.get("polish"), dict) else None
    if not pl:
        return None
    rows = [r for r in pl.get("rows") or [] if isinstance(r, dict) and (r.get("ko") != r.get("tgt") or r.get("why") or r.get("suggest_erase"))]
    return {"rows": rows[:20], "why": str(pl.get("why") or ""), "changed": int(pl.get("changed") or 0)}


# ── 적용 ───────────────────────────────────────────────────────────────────────────────────

#: Y11-M(오너 02:12 캡처): 렌더는 **우리 쪽에서 직접** 그린다 — 상자 테두리 띠 색으로 상자를 먼저 메우고(Cloudinary gen_remove 안 씀 —
#   상자당 과금), 텐센트가 그린 글자의 색·굵기를 재서 같은 모양으로 Noto Sans KR을 앉힌 뒤, 다 그린 그림을 **일반 업로드**한다.
#   옛 길(변환 주소 조립 + 글자 오버레이)은 지우기 영역이 비거나 글꼴이 거부되면 텐센트 글자 위에 겹쳐 그려 번졌다(21번).
#: 텐센트 글자(같은 상자)보다 이 비율 밑으로 작아지면 「안 들어감」 — 다듬기는 그 상자를 텐센트 글자로 둔다.
FIT_KEEP = 0.8
#: 기준 글자가 없을 때(사람이 넣은 글자) — 상자 높이 기준 옛 규칙
MIN_FIT_RATIO = 0.45
MIN_PX = 11
#: 테두리 띠가 이 값(밝기 10~90% 폭) 안이면 「한 색 바탕」 — 중앙값으로 메운다. 넘으면 글자 픽셀만 inpaint(그라데이션에 네모 방지).
FLAT_SPREAD = 8
_WIDE = re.compile("[ᄀ-ᇿ㄰-㆏가-힯　-鿿＀-￯]")
_WIDE_HAN = re.compile("[\u3400-\u4dbf\u4e00-\u9fff]")


def _units(text: str) -> float:
    """글자 폭(글자 크기 1 기준) — 한글·한자·전각 1.0, 그 밖 0.58. 폰트가 없을 때만 쓴다."""
    return sum(1.0 if _WIDE.match(c) else 0.58 for c in text) or 1.0


#: 재는 글꼴은 굵기마다 100px 한 벌 — 폭은 크기에 비례한다. 크기마다 글꼴을 열면 한 장 렌더에 글꼴 20여 벌(~100MB)이
#   메모리에 남았다(Y11-M 실측 +78MB/96벌 — 인스턴스 합계 가드 420MB 근처라 위험).
_MEASURE_PX = 100


@functools.lru_cache(maxsize=2)
def _measure_font(weight: str):
    from src.services.image_render_font import load
    return load(_MEASURE_PX, weight)


def _font(size: int, weight: str):
    """그릴 글꼴(그 크기 한 벌) — 캐시하지 않는다(그리고 버린다)."""
    from src.services.image_render_font import load
    return load(int(size), weight)


def _len(text: str, size: int, weight: str) -> float:
    f = _measure_font(weight)
    return f.getlength(text) * size / _MEASURE_PX


def _wrap(text: str, size: int, weight: str, max_w: int, max_lines: int) -> Optional[List[str]]:
    """띄어쓰기 단위로 줄을 나눈다(낱말이 넘치면 글자 단위). `max_lines` 넘거나 한 글자도 안 들어가면 None."""
    lines, cur = [], ""
    for word in str(text).split():
        trial = f"{cur} {word}".strip()
        if _len(trial, size, weight) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        if _len(word, size, weight) <= max_w:
            cur = word
            continue
        for ch in word:
            if _len(cur + ch, size, weight) <= max_w:
                cur += ch
            elif not cur:
                return None
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines if lines and len(lines) <= max_lines else None


def fit_box(text: str, w: int, h: int, *, weight: str = "bold", max_lines: int = 2, max_px: int = 0) -> Optional[Dict]:
    """상자(w×h px) 안에 들어가는 가장 큰 `{size, lines, line_h}`(`max_px` 이하) — 실제 글꼴로 잰다. 못 넣으면 None."""
    text = str(text or "").strip()
    if not text or w < 4 or h < MIN_PX:
        return None
    lo, hi, best = MIN_PX, max(MIN_PX, min(int(h * 0.9), int(max_px) if max_px else 10 ** 6)), None
    if _measure_font(weight) is None:
        return None
    while lo <= hi:                                              # 크기가 클수록 줄·폭이 늘어난다 — 이분 탐색
        mid = (lo + hi) // 2
        lines = _wrap(text, mid, weight, int(w * 0.96), max_lines)
        if lines is not None and int(mid * 1.22) * len(lines) <= h:
            best, lo = {"size": mid, "lines": lines, "line_h": int(mid * 1.22)}, mid + 1
        else:
            hi = mid - 1
    return best


def _font_ok() -> bool:
    try:
        from src.services.image_render_font import available
        return bool(available()[0])
    except Exception:                                           # noqa: BLE001
        return False


def text_fit(text: str, box: Dict, ref: str = "") -> Dict:
    """`{size, lines, fits, ref_size}` — 이 글자를 상자에 넣을 때의 크기·줄. `ref`(텐센트가 그 상자에 그린 글자)가 있으면
    **그 글자를 같은 상자에 넣은 크기**가 기준이다: 그 줄 수(최소 2줄)까지 허용, 크기가 기준의 FIT_KEEP 이상이면 들어감."""
    w, h = max(1, int(box.get("w") or 1)), max(1, int(box.get("h") or 1))
    text = str(text or "").strip()
    if not _font_ok():                                           # 폰트가 없으면 어림셈(옛 규칙)
        ideal = h * 0.8
        one = min(ideal, w * 0.96 / _units(text))
        return {"size": max(10, int(one)), "lines": [text], "fits": one >= max(10, ideal * MIN_FIT_RATIO), "ref_size": 0}
    rf = fit_box(ref, w, h, max_lines=8) if str(ref or "").strip() else None
    n = max(2, len((rf or {}).get("lines") or []))
    f = fit_box(text, w, h, max_lines=n)
    if f is None:
        return {"size": 0, "lines": [text], "fits": False, "ref_size": (rf or {}).get("size", 0)}
    need = (rf["size"] * FIT_KEEP) if rf else max(MIN_PX, h * 0.8 * MIN_FIT_RATIO)
    return {"size": f["size"], "lines": f["lines"], "fits": f["size"] >= min(need, h * 0.8), "ref_size": (rf or {}).get("size", 0)}


def _rect_px(b: Dict, k: float, W: int, H: int) -> Tuple[int, int, int, int]:
    x0, y0 = max(0, int(b["x"] * k)), max(0, int(b["y"] * k))
    x1, y1 = min(W, int(round((b["x"] + b["w"]) * k))), min(H, int(round((b["y"] + b["h"]) * k)))
    return x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)


def _band(np, img, rect, bw: int):
    """상자 **바깥** 테두리 띠 화소(N×3)."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = rect
    X0, Y0, X1, Y1 = max(0, x0 - bw), max(0, y0 - bw), min(W, x1 + bw), min(H, y1 + bw)
    parts = [img[Y0:y0, X0:X1], img[y1:Y1, X0:X1], img[y0:y1, X0:x0], img[y0:y1, x1:X1]]
    px = [p.reshape(-1, 3) for p in parts if p.size]
    return np.concatenate(px) if px else img[y0:y1, x0:x1].reshape(-1, 3)


#: 렌더 판 — 올리면 기계 다듬음 버전은 다음 「번역 다듬기」 때 다시 그린다(Y11-N: 겹친 상자 묶음·획 기준 세로 자리·판 유령)
RENDER_V = 2
#: Y11-N(오너): 탭 지우기 뒤 남은 잉크가 원래 잉크의 이 비율을 넘으면(6번 「톱1」 같은 큰 글자) 상자 전체를 바탕으로 메운다
RESIDUAL_MAX = 0.15
#: 텐센트 판 위 「유령」(희미하게 남은 원문 획) — 상자 안 글자 아닌 픽셀이 바깥 바탕과 이만큼(밝기 98%) 안이면 판·유령째 바탕으로 메운다
GHOST_DIFF = 28


#: Y11-N2(오너 3번 메모): 상자 안 **사진 성분** — 글자 아닌 픽셀의 밝기 표준편차 · 에지 밀도. 넘으면 잔여 잉크 폴백(통째 메움)을 하지 않는다
PHOTO_STD = 22.0
PHOTO_EDGE = 0.05
PHOTO_WARN = "이 상자는 사진 위라 지우기 품질 보장 못 함 — 마음에 안 들면 되돌리기"


def _photo_like(cv2, np, img, rect, mask) -> bool:
    """상자 안이 사진(사람·상품·배경 무늬)인가 — 글자 획(넓혀서)을 뺀 픽셀로 잰다. 6번 「톱1」 상자(사람 위) 실측."""
    x0, y0, x1, y1 = rect
    gray = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    keep = np.ones(gray.shape, bool) if mask is None else cv2.dilate(mask[y0:y1, x0:x1], np.ones((9, 9), np.uint8)) == 0
    if int(keep.sum()) < 50:
        return False
    edges = cv2.Canny(gray, 60, 160) > 0
    return float(gray[keep].std()) > PHOTO_STD or float(edges[keep].mean()) > PHOTO_EDGE


def _ink_px(cv2, np, img, rect) -> int:
    from src.services.image_text_render import _glyph_mask
    m, _w = _glyph_mask(cv2, np, img, rect, 0)
    return 0 if m is None else int((m > 0).sum())


def _fill_box(cv2, np, img, rect, bw: int) -> str:
    """상자 통째로 바탕 — 한 색이면 테두리 띠 중앙값, 아니면 상자 전체를 둘레에서 메운다(inpaint).
    Y11-N 실측: 네 변 잇기(쿤스)는 사진 위 큰 상자(6번 「톱1」 864×452)에서 세로 줄무늬가 났다 — 통째 inpaint가 덜 거칠다."""
    x0, y0, x1, y1 = rect
    band = _band(np, img, rect, bw)
    lum = band.astype(np.int32).sum(axis=1) / 3.0
    if float(np.percentile(lum, 90) - np.percentile(lum, 10)) > FLAT_SPREAD:
        m = np.zeros(img.shape[:2], np.uint8)
        m[y0:y1, x0:x1] = 255
        img[:] = cv2.inpaint(img, m, 9, cv2.INPAINT_TELEA)
        return "inpaint-box"
    img[y0:y1, x0:x1] = np.median(band, axis=0).astype(np.uint8)
    return "fill-box"


def erase_local(cv2, np, img, rect, *, strict: bool = False) -> str:
    """상자 글자를 지운다(제자리). `rect` = 상자(또는 겹친 상자 묶음)를 사방으로 조금 넓힌 자리(이웃 상자 쪽은 안 넓힘).
    돌려주는 값 = 쓴 방법. 지우는 픽셀은 **그 자리 글자 획만** — 넓힌 자리 테두리에 닿는 획(이웃 줄 글자가 삐져 들어온 것)은 남긴다.
    - `fill`: 바탕이 한 색(흰 바탕 등) — 그 **중앙값으로** 글자 획을 메운다(오너 Y11-M). 표본은 상자 안 글자 아닌 픽셀.
    - `fill-ghost`: 한 색 바탕인데 상자 안이 텐센트 옅은 판·희미한 원문 획뿐 — 자리 전체를 바깥 바탕으로(22번 유령 글자, Y11-N).
    - `inpaint`: 무늬·그라데이션 바탕 — 상자를 통째 칠하면 네모가 보인다(VRSUK 21번 실측). 획만 주변으로 메운다.
    - `fill-box`/`inpaint-box`: 획을 못 고르면, 또는 `strict`(사람이 탭한 지우기)인데 남은 잉크가 원래의 15%를 넘으면 상자 통째로."""
    x0, y0, x1, y1 = rect
    bw = max(2, min(12, int((y1 - y0) * 0.15)))
    from src.services.image_text_render import _glyph_mask
    mask, _why = _glyph_mask(cv2, np, img, rect, 3)
    if mask is None:
        return _fill_box(cv2, np, img, rect, bw)
    before = _ink_px(cv2, np, img, rect) if strict else 0
    photo = _photo_like(cv2, np, img, rect, mask) if strict else False
    # 바탕 표본 = 상자 안 **글자 아닌 픽셀**(획 둘레 더 넓게 뺀 것) — 텐센트는 글자 뒤에 옅은 판을 깐다. 상자 밖 색으로
    #   메우면 그 판 위에 글자 모양 「유령」이 남았다(22번 실측).
    roi = img[y0:y1, x0:x1]
    far = cv2.dilate(mask[y0:y1, x0:x1], np.ones((7, 7), np.uint8)) == 0
    bg = roi[far] if int(far.sum()) >= 30 else _band(np, img, rect, bw)
    lum = bg.astype(np.int32).sum(axis=1) / 3.0
    if float(np.percentile(lum, 90) - np.percentile(lum, 10)) <= FLAT_SPREAD:
        band = _band(np, img, rect, bw)
        blum = band.astype(np.int32).sum(axis=1) / 3.0
        bmed = np.median(band, axis=0)
        if (float(np.percentile(blum, 90) - np.percentile(blum, 10)) <= FLAT_SPREAD
                and float(np.percentile(np.abs(lum - float(np.median(blum))), 98)) <= GHOST_DIFF):
            img[y0:y1, x0:x1] = bmed.astype(np.uint8)          # 판·유령째 — 안쪽이 바깥 바탕과 같은 색 계열일 때만
            how = "fill-ghost"
        else:
            img[mask > 0] = np.median(bg, axis=0).astype(np.uint8)
            how = "fill"
    else:
        img[:] = cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)
        how = "inpaint"
    if strict and before:
        left = _ink_px(cv2, np, img, rect)
        if left > before * RESIDUAL_MAX:
            if photo:
                # 사진 위 큰 글자 — 통째로 메우면 사람·상품까지 뭉갠다(6번 실측). 메우지 않고 경고(되돌리기로 돌아갈 수 있다).
                logger.info("[사진 편집] 지운 뒤 잉크 %s/%s — 사진 위라 통째 메움 안 함", left, before)
                return how + f"(사진 위·잔여 {round(100.0 * left / before)}%)"
            logger.info("[사진 편집] 지운 뒤 잉크 %s/%s(%.0f%%) — 상자 통째로 바탕", left, before, 100.0 * left / before)
            return _fill_box(cv2, np, img, rect, bw) + f"(잔여 {round(100.0 * left / before)}%)"
    return how


def _typo(raw: bytes, rect, tgt: str) -> Dict:
    """텐센트가 그린 글자의 색·굵기·정렬(D3 측정기) — 못 재면 기본(굵게·가운데·먹)."""
    try:
        from src.services.image_text_render import sample_typography
        x0, y0, x1, y1 = rect
        t = sample_typography(raw, {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}, source=tgt)
        return {"color": tuple(t.get("color") or (26, 23, 20)), "weight": t.get("weight") or "bold",
                "align": t.get("align") or "center", "why": t.get("reason") or ""}
    except Exception as exc:                                    # noqa: BLE001
        return {"color": (26, 23, 20), "weight": "bold", "align": "center", "why": type(exc).__name__}


def _expand(rect, others, W: int, H: int, pad: int):
    """지울 자리를 사방 `pad`만큼 넓힌다 — 단 **다른 글자 상자 쪽으로는** 그 상자 앞에서 멈춘다(겹친 상자면 그 경계까지 줄인다).
    넓히는 까닭: 텐센트 글자가 상자 테두리에 붙어 있으면 글자 고르기가 그 획을 「바탕 도형」으로 보고 남겼다(21번 「서 잘」)."""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    for o in others:
        ox0, oy0, ox1, oy1 = o
        if tuple(o) == tuple(rect) or not (ox0 < X1 and ox1 > X0 and oy0 < Y1 and oy1 > Y0):
            continue
        if oy1 <= cy and oy1 < y1:                              # 위쪽 이웃(겹쳐도 — 「중단」 상자 위 「EHILÀ」)
            Y0 = max(Y0, min(oy1, y1 - 1))
        elif oy0 >= cy and oy0 > y0:
            Y1 = min(Y1, max(oy0, y0 + 1))
        elif ox1 <= cx and ox1 < x1:
            X0 = max(X0, min(ox1, x1 - 1))
        elif ox0 >= cx and ox0 > x0:
            X1 = min(X1, max(ox0, x0 + 1))
    return X0, Y0, max(X0 + 1, X1), max(Y0 + 1, Y1)


#: 이 각도(도) 넘게 기운 글자 줄은 「기운 글자」 — 우리는 똑바로만 그린다(쿠폰 상세 4 회원 카드 실측)
TILT_DEG = 6.0


def _tilted(cv2, np, img, rect) -> bool:
    """상자 안 글자 획이 기울었나 — 획 픽셀의 최소 외접 사각형 각도."""
    from src.services.image_text_render import _glyph_mask
    m, _w = _glyph_mask(cv2, np, img, rect, 0)
    if m is None:
        return False
    ys, xs = np.nonzero(m)
    if xs.size < 40:
        return False
    (_cx, _cy), (rw, rh), ang = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    a = abs(float(ang)) % 90.0
    return min(a, 90.0 - a) > TILT_DEG


def _ink(cv2, np, img, rect):
    """상자 안 텐센트 글자 잉크의 외접 `(w, h, x, y)` — 못 고르면 None."""
    from src.services.image_text_render import _glyph_mask
    m, _why = _glyph_mask(cv2, np, img, rect, 0)
    if m is None:
        return None
    ys, xs = np.nonzero(m)
    if not xs.size:
        return None
    return (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1), int(xs.min()), int(ys.min()))


def render_local(raw: bytes, k: float, erase: List[Dict], texts: List[Tuple[Dict, str]], others: Optional[List[Dict]] = None,
                 skip_tilted: bool = False, restore: Optional[List[Dict]] = None, orig_raw: bytes = b"") -> Dict:
    """`{ok, bytes, size, how, drawn, skipped, why}` — 바탕 그림 위에서 상자를 지우고 글자를 그린다. 좌표는 상자 공간 × `k`.
    `others` = 이 사진의 글자 상자 전부(지울 자리를 넓힐 때 이웃 상자를 피한다)."""
    from src.services.image_text_render import _load_cv2
    cv2, np, why = _load_cv2()
    if why:
        return {"ok": False, "why": why}
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "why": "바탕 그림을 열지 못했어요"}
    H, W = img.shape[:2]
    near = [_rect_px(o, k, W, H) for o in (others or [])]

    def _area(b):
        r = _rect_px(b, k, W, H)
        return r, _expand(r, near, W, H, max(3, int((r[3] - r[1]) * 0.15)))

    # Y11-N(오너 22번 좌하단): 겹치거나 맞붙은 상자는 **묶어서** 한 번에 지우고 한 번에 그린다 — 따로 지우면 텐센트 판끼리 겹친
    #   자리에 원문 획(유령)이 남았다. 묶음에 끼는 손 안 댄 상자는 지금 글자(tgt) 그대로 다시 그린다(한자 남은 상자는 안 끼움).
    tilted_skip = []
    if skip_tilted:
        # 다듬기(기계)는 기운 글자를 다시 그리지 않는다 — 똑바로 그리면 모양이 바뀐다(텐센트 글자 그대로)
        keep = []
        for b, t in texts:
            if _tilted(cv2, np, img, _area(b)[1]):
                tilted_skip.append(t)
            else:
                keep.append((b, t))
        texts = keep
    edit_b = [(b, None) for b in erase] + [(b, t) for b, t in texts]
    #   손 안 댄 상자는 **번역된 글자**만 낀다 — 원문 그대로인 브랜드·로고(EHILÀ)·숫자는 다시 그리지 않는다(글꼴이 바뀐다).
    pool = [(b, None) for b in (others or []) if not any(b is e for e, _t in edit_b)
            and str(b.get("tgt") or "").strip() and str(b.get("tgt") or "").strip() != str(b.get("src") or "").strip()
            and not _WIDE_HAN.search(str(b.get("tgt") or "")) and not _tilted(cv2, np, img, _area(b)[1])]
    allb = edit_b + pool
    rects = [_rect_px(b, k, W, H) for b, _t in allb]

    def _touch(a, c):
        ha, hc = a[3] - a[1], c[3] - c[1]
        if max(ha, hc) > 3 * max(1, min(ha, hc)):
            return False                                         # 글자 크기가 크게 다르면(작은 줄 ↔ 큰 로고) 묶지 않는다
        gap = max(6, int(0.15 * min(ha, hc)))
        return not (a[2] + gap <= c[0] or c[2] + gap <= a[0] or a[3] + gap <= c[1] or c[3] + gap <= a[1])

    n_erase = len(erase)

    def _joins(j, m):
        # 지우기만 하는 상자는 묶지 않는다 — 글자 상자와 묶으면 지운 자리 둘레 글자까지 다시 그리게 된다(6번 실측)
        return j >= n_erase and m >= n_erase and _touch(rects[j], rects[m])

    group, seen = [], set()
    for i in range(len(edit_b)):
        if i in seen:
            continue
        comp, stack = [], [i]
        seen.add(i)
        while stack:
            j = stack.pop()
            comp.append(j)
            for m in range(len(allb)):
                if m not in seen and _joins(j, m):
                    seen.add(m)
                    stack.append(m)
        comp = sorted(comp)
        if len(comp) > 1:
            u = (min(rects[j][0] for j in comp), min(rects[j][1] for j in comp),
                 max(rects[j][2] for j in comp), max(rects[j][3] for j in comp))
            band = _band(np, img, u, 8)
            lum = band.astype(np.int32).sum(axis=1) / 3.0
            if float(np.percentile(lum, 90) - np.percentile(lum, 10)) > FLAT_SPREAD:
                # 묶음은 한 색 바탕(텐센트 판이 겹친 자리)에서만 — 사진·그라데이션 위에서 묶으면 큰 글자(6번 「톱1」)까지
                #   반쯤 지우고 다시 그렸다(Y11-N 실측). 그런 자리는 상자 하나씩(손 안 댄 상자는 안 건드림).
                group.extend([[j] for j in comp if j < len(edit_b)])
                continue
        group.append(comp)
    typos, how, merged = [], [], 0
    for comp in group:
        members = [allb[j] for j in comp]
        mrect = [rects[j] for j in comp]
        for (b, t), r in zip(members, mrect):
            if t is None and any(b is e for e, _t in edit_b):
                continue                                         # 지우기만 한 상자는 다시 그리지 않는다
            ext = _area(b)[1]
            ty = _typo(raw, ext, str(b.get("tgt") or ""))
            ty["keep"] = t is None                               # 손 안 댄 상자 — 텐센트 크기 그대로(키우지 않는다)
            typos.append((b, t if t is not None else str(b.get("tgt") or ""), r, ext, ty, _ink(cv2, np, img, ext)))
        u = (min(r[0] for r in mrect), min(r[1] for r in mrect), max(r[2] for r in mrect), max(r[3] for r in mrect))
        outside = [n for jn, n in enumerate(rects) if jn not in comp] + \
                  [n for n in near if n not in mrect]
        ext = _expand(u, outside, W, H, max(3, int(min(r[3] - r[1] for r in mrect) * 0.15)))
        strict = any(t is None for b, t in members if any(b is e for e, _t in edit_b))
        how.append(erase_local(cv2, np, img, ext, strict=strict))
        merged += len(comp) - 1
    from PIL import Image, ImageDraw
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    drawn, skipped, sizes = 0, [], []
    for b, text, rect, _ext, ty, ink in typos:
        x0, y0, x1, y1 = rect
        w_key = ty["weight"] if ty["weight"] in ("regular", "bold") else "bold"
        tgt = str(b.get("tgt") or "")
        rf = fit_box(tgt, x1 - x0, y1 - y0, weight=w_key, max_lines=8)
        # 텐센트 글자 크기 = 그 글자를 잉크 외접 안에 넣은 크기 — 새 글자는 그보다 크게 그리지 않는다(위계 유지)
        tf = fit_box(tgt, ink[0] + 6, int(ink[1] * 1.3) + 6, weight=w_key, max_lines=8) if ink else None
        cap = int(tf["size"] * (1.0 if ty.get("keep") else 1.1)) if tf else 0
        f = None
        for n in range(1, max(2, len((rf or {}).get("lines") or [])) + 1):   # 줄은 적게 — 텐센트 크기의 85%가 나오는 가장 적은 줄
            g = fit_box(text, x1 - x0, y1 - y0, weight=w_key, max_lines=n, max_px=cap)
            if g and (f is None or g["size"] > f["size"]):
                f = g
            if g and cap and g["size"] >= cap * 0.85:
                break
        if f is None:
            skipped.append(text)
            continue
        font = _font(f["size"], w_key)
        sizes.append(f["size"])
        align = ty["align"]
        if align == "center" and len(f["lines"]) > 1 and len((rf or {}).get("lines") or []) > 1:
            align = "left"                                       # 텐센트 글자도 여러 줄(문단) — 문단은 왼쪽 정렬
        # 자리 = 텐센트 글자가 실제로 있던 곳(잉크 외접) — 상자는 글자보다 클 때가 많다(21번 제목: 상자 아래쪽이 비어 있음)
        bx0, bx1 = (ink[2], ink[2] + ink[0]) if ink else (x0, x1)
        cy = (ink[3] + ink[1] // 2) if ink else (y0 + y1) // 2
        # 세로 자리는 **실제 글자 획** 기준 — Pillow는 글꼴 윗선(ascent)부터 그려 획이 0.2em쯤 아래로 내려앉았다(Y11-N 실측).
        _gl, gt, _gr, gb = font.getbbox("가")
        ink_h = (len(f["lines"]) - 1) * f["line_h"] + (gb - gt)
        itop = min(max(y0, cy - ink_h // 2), max(y0, y1 - ink_h))
        for i, line in enumerate(f["lines"]):
            l, _t, r, _b = font.getbbox(line)
            lw = r - l
            want = bx0 if align == "left" else (bx1 - lw) if align == "right" else (bx0 + bx1 - lw) // 2
            cx = min(max(x0, want), max(x0, x1 - lw)) - l
            draw.text((cx, itop + i * f["line_h"] - gt), line, font=font, fill=ty["color"])
        drawn += 1
    restored = 0
    if restore and orig_raw:
        # Y11-W(오너 2026-10-16 23:58): **원본 픽셀 되살리기** — 텐센트가 한국어로 칠한 자리를 원문으로 되돌릴 땐 글자를 다시 그리지 않고
        #   수집 원본의 그 자리를 붙인다(서명 낙서 위 작은 이탈리아어 「디센·세콜로…」 · 장식 글자 「ISURE에」). 틀이 같은 장(identity)만.
        try:
            from PIL import Image as _Im
            with _Im.open(io.BytesIO(orig_raw)) as o0:
                orig = o0.convert("RGB")
                if orig.size != pil.size:
                    orig = orig.resize(pil.size)
                for b in restore:
                    x0, y0, x1, y1 = _rect_px(b, k, W, H)
                    pad = max(3, int((y1 - y0) * 0.35))
                    box = (max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad))
                    pil.paste(orig.crop(box), box[:2])
                    restored += 1
        except Exception as exc:                                # noqa: BLE001 — 되살리기 실패면 그 상자는 텐센트 그대로
            logger.warning("[사진 편집] 원본 되살리기 실패: %s", exc)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=92)
    del draw                                                     # Y11-O: 장마다 화소 버퍼를 바로 놓는다(워커가 gc·malloc_trim)
    pil.close()
    img = None                                                  # noqa: F841 — 바탕 배열 참조를 놓는다
    return {"ok": True, "bytes": buf.getvalue(), "size": [W, H], "how": how, "drawn": drawn, "skipped": skipped, "sizes": sizes,
            "restored": restored,
            "merged": merged, "tilted": tilted_skip, "warn": PHOTO_WARN if any("사진 위" in h for h in how) else "",
            "colors": ["%02x%02x%02x" % tuple(x[4]["color"]) for x in typos], "weights": [x[4]["weight"] for x in typos]}


def apply(extra: dict, kind: str, idx: int, ops: List[Dict], *, by: str = "user", small=None) -> Dict:
    """`ops=[{id, action: erase|text, text?}]` → **새 편집본 하나**(지금 고른 버전 위에). 결과 `{ok, url, credits, erased, error?}`.
    사람이 상자를 탭해서 적용할 때(그리고 다듬기)만 부른다(자동 픽셀 변경 없음 — Y11-E). 저장은 호출부.
    Y11-M: 우리 쪽에서 그린다(`render_local`) → 다 그린 그림을 Cloudinary에 **일반 업로드**(변환 없음)."""
    ok_c, why = configured()
    if not ok_c:
        return {"ok": False, "error": "사진 편집을 쓸 수 없어요 — " + why}
    p = plan(extra, kind, idx, small=small)
    by_id = {b["id"]: b for b in p["boxes"]}               # 지금 버전의 글자 상자(t#)만
    todo = [o for o in ops or [] if isinstance(o, dict) and o.get("action") in ("erase", "text", "restore") and o.get("id") in by_id]
    if not todo:
        return {"ok": False, "error": (p.get("why") or "지울 상자를 탭해서 골라 주세요") if not p["boxes"] else "지울 상자를 탭해서 골라 주세요"}
    raw = _fetch(p["url"])
    if not raw:
        return {"ok": False, "error": "편집할 사진을 받지 못했어요 — 잠시 뒤 다시 해 주세요"}
    from src.db import image_translate_queue_pg as q
    took, today = q.take_start(_day_key(), daily_cap())          # 한도는 실제로 그릴 때만 센다
    if not took:
        return {"ok": False, "error": f"오늘 사진 편집 한도({daily_cap()}회)를 다 썼어요 — 내일 다시 해 주세요", "today": today}
    erase = [by_id[o["id"]] for o in todo if o["action"] == "erase"]
    texts = [(by_id[o["id"]], str(o.get("text") or "")[:60]) for o in todo if o["action"] == "text" and str(o.get("text") or "").strip()]
    restore = [by_id[o["id"]] for o in todo if o["action"] == "restore"]
    orig_raw = b""
    if restore:
        _e0 = _entry(extra, kind, idx) or {}
        if _e0.get("box_frame") == "identity":                  # 틀이 같은 장만 — 좌표가 다르면 엉뚱한 자리를 붙인다
            orig_raw = _fetch(_original(extra, kind, idx))
        if not orig_raw:
            restore = []                                         # 원본을 못 받았다 — 그 상자는 텐센트 그대로
    W = p["size"][0]
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im0:
            RW = im0.size[0]
    except Exception:                                           # noqa: BLE001
        return {"ok": False, "error": "편집할 사진을 열지 못했어요"}
    k = (RW / W) if W else 1.0                                 # 상자 공간 → 바탕 사진
    try:
        # Y11-O(오너): 그리기는 요청·다듬기 스레드가 아니라 **사진 그리기 워커 하나**에서(한 번에 한 장 · 장마다 gc·malloc_trim)
        from src.utils import render_worker as _rw
        rr = _rw.run(render_local, raw, k, erase, texts, others=p["boxes"], skip_tilted=(by == "polish"),
                     restore=restore, orig_raw=orig_raw, _name=f"{by}:{kind}{idx}")
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("[사진 편집] 그리기 실패 %s idx=%s: %s", kind, idx, exc)
        rr = {"ok": False, "why": type(exc).__name__}
    if not rr.get("ok"):
        return {"ok": False, "error": "편집본을 그리지 못했어요 — " + (rr.get("why") or "사유 불명")}
    if not erase and not rr.get("drawn") and not rr.get("restored"):
        # 바뀔 상자가 전부 기운 글자라 건너뛰었다 — 같은 그림을 새 버전으로 올리지 않는다(텐센트 글자 그대로)
        return {"ok": False, "error": f"바꿀 상자가 없어요 — 기운 글자 {len(rr.get('tilted') or [])}곳은 텐센트 글자 그대로 둬요",
                "tilted": rr.get("tilted") or []}
    from src.media.image_pipeline import upload_bytes
    up = upload_bytes(rr["bytes"], folder="edit")
    url = str(up.get("secure_url") or "") if up.get("ok") else ""
    if not url:
        return {"ok": False, "error": "편집본을 올리지 못했어요 — " + (up.get("error") or "주소를 받지 못했어요")}
    c = cost(len(texts))
    e = _entry(extra, kind, idx, create=True)
    base_key = current_key(e) if e.get("status") or e.get("current") else V_ORIGINAL
    _normalize(e)
    prev = next((x for x in e["edits"] if f"edit:{x['n']}" == base_key), None)
    erased = list((prev or {}).get("erased") or []) + [x for b in erase + [t[0] for t in texts] for x in (b.get("src"), b.get("tgt")) if x]
    n = max([int(x.get("n") or 0) for x in e["edits"]] + [0]) + 1
    now = datetime.now(timezone.utc).isoformat()
    e["edits"].append({"n": n, "url": url, "base": p["url"], "base_key": base_key, "at": now, "by": by, "ops": todo,
                       "erased": erased, "credits": c["credits"], "ready": True, "render": "local", "render_v": RENDER_V,
                       "how": rr.get("how"), "colors": rr.get("colors"), "weights": rr.get("weights"), "skipped": rr.get("skipped"),
                       "tilted": rr.get("tilted"), "warn": rr.get("warn") or ""})
    if not e.get("status"):
        e["status"] = "done"
    e.setdefault("vendor", "edit")
    select(extra, kind, idx, f"edit:{n}")
    spent = round(sum(float(x.get("credits") or 0) for x in e["edits"]), 3)
    return {"ok": True, "url": url, "ready": True, "credits": c["credits"], "spent": spent, "erased": erased,
            "version": f"edit:{n}", "pending": False, "today": today, "cap": daily_cap(), "skipped": rr.get("skipped") or [],
            "warn": rr.get("warn") or ""}


def _head_ok(url: str) -> bool:
    """파생본이 준비됐나 — HEAD 한 번(기다리지 않는다)."""
    try:
        import requests
        return requests.head(url, timeout=8, allow_redirects=True).status_code == 200
    except Exception:                                           # noqa: BLE001
        return False


def refresh_pending(extra: dict, kind: str, idx: int) -> bool:
    """만드는 중이던 편집본을 다시 본다 — 다 됐으면 `ready`로 바꾸고(칩이 켜진다), 그걸 기다리던 장이면 그 편집본으로 넘어간다.
    지금 버전이 만드는 중인 편집본이면(옛 기록) 바탕 버전을 보여 준다. 바꾼 것이 있으면 True."""
    e = _entry(extra, kind, idx)
    if not e:
        return False
    eds = edits(e)
    if not any(x.get("ready") is False for x in eds):
        return False
    _normalize(e)
    changed = False
    for x in e["edits"]:
        if x.get("ready") is False and _head_ok(x["url"]):
            x.update(ready=True, http_status=200)
            changed = True
    cur = current_key(e)
    ed = next((x for x in e["edits"] if f"edit:{x['n']}" == cur), None)
    if ed and ed.get("ready") is False:                          # 지금 나가는 게 아직 없는 그림 — 바탕으로
        select(extra, kind, idx, ed.get("base_key") or V_ORIGINAL)
        e["pending_select"] = cur                                 # (select가 지우므로 뒤에 적는다)
        changed = True
    want = e.get("pending_select")
    if want:
        wv = next((x for x in e["edits"] if f"edit:{x['n']}" == want), None)
        if wv and wv.get("ready") and current_key(e) == (wv.get("base_key") or V_ORIGINAL):
            e.pop("pending_select", None)
            select(extra, kind, idx, want)
            changed = True
    return changed
