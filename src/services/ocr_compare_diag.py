"""Y11-H(오너 2026-10-14) — OCR 사전검사 「한자 0」 실측 · Y11-J5 대표 사진 상자 값.

VRSUK 상세 3·6·7번(idx 2·5·6): 사진에 한자 문장이 크게 있는데 사전검사가 「한자 0」(읽은 글자는 라틴만)으로 건너뛰었다.
장마다 같은 원본을 네 가지로 GeneralBasicOCR에 보내 한자·라틴 글자 수를 잰다 — 장당 OCR 4회(과금):

- `1024·auto` = 예전 사전검사(Z10-B 축소 · LanguageType auto)
- `원본·auto` = 축소만 끔
- `1600·zh`  = 오너 제안 하한
- `원본·zh`  = 지금 사전검사(Y11-H — 텐센트 번역에 보내는 바이트 그대로 · 중영 혼합)

대표 사진(쿠팡 노출 첫 장)은 상자마다 확신·기울기·면적·소품 판정·안 걸린 조건을 적는다(OCR 1회).
결과는 `app_state`의 `diag:ocr_compare`에 남는다(요청이 끝나도 읽을 수 있게 — 키 값은 적지 않는다).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

STATE_KEY = "diag:ocr_compare"
_HAN = re.compile("[㐀-䶿一-鿿]")
_LATIN = re.compile("[A-Za-z]")
_RUNNING = threading.Lock()


def variants():
    from src.services.ocr_tencent import AS_IS
    return (("1024·auto", 1024, "auto"), ("원본·auto", AS_IS, "auto"), ("1600·zh", 1600, "zh"), ("원본·zh", AS_IS, "zh"))


def count(text: str) -> Dict[str, int]:
    return {"han": len(_HAN.findall(text or "")), "latin": len(_LATIN.findall(text or ""))}


def measure_page(raw: bytes) -> List[Dict]:
    """한 장 → 변형마다 `{name, ok, han, latin, text, why, ms}`."""
    from src.services import ocr_tencent as O
    out = []
    for name, side, lang in variants():
        t0 = time.monotonic()
        res = O.read(raw, max_side=side, lang=lang)
        txt = "".join(t for t, _c in res.get("lines") or [])
        out.append(dict(name=name, ok=bool(res.get("ok")), text=txt[:120], why=str(res.get("why") or "")[:120],
                        ms=int((time.monotonic() - t0) * 1000), **count(txt)))
    return out


def explain_boxes(raw: bytes, *, exempt: bool = False) -> Dict:
    """대표 사진 상자마다 소품 판정 값 — `{ok, why, angle, frame, size, boxes:[{src, conf, tilt, area_pct, prop, miss}], minor}`.
    `miss` = 소품이 아닌 상자에서 **안 걸린 조건**(면적 ≥0.5% / 기울기 <20° / 확신 ≥70 / 워터마크 낱말)."""
    from src.services import ocr_tencent as O
    from src.services import prop_text as PT
    from src.services import coupang_image_check as C
    got = O.read_boxes(raw)
    if not got.get("ok"):
        return {"ok": False, "why": got.get("why") or "", "boxes": []}
    W, H = (got.get("size") or [0, 0])[:2]
    ang = float(got.get("angle") or 0.0)
    frame = "rot180" if abs(ang) > 135 else ("rot90a" if abs(ang) > 45 else "")
    boxes = got.get("boxes") or []
    PT.mark(boxes, [W, H], frame=frame, off=exempt)
    rows = []
    for b in boxes:
        area = (max(0, b.get("w", 0)) * max(0, b.get("h", 0))) / float(W * H) if W and H else 0.0
        tilt = b.get("tilt")
        miss = []
        if not b.get("prop"):
            if exempt:
                miss.append("상품이 곧 글자(소품 규칙 끔)")
            if area >= PT.MAX_AREA:
                miss.append(f"면적 {area * 100:.2f}% ≥ {PT.MAX_AREA * 100:.1f}%")
            if tilt is None:
                miss.append("기울기 모름(꼭짓점 없음)")
            elif min(float(tilt), 360 - float(tilt)) < PT.MIN_TILT:
                miss.append(f"기울기 {tilt}° < {PT.MIN_TILT:.0f}°")
            if b.get("conf") is not None and float(b["conf"]) >= PT.MIN_CONF:
                miss.append(f"확신 {b['conf']} ≥ {PT.MIN_CONF:.0f}")
            if PT._watermark_word(str(b.get("src") or "")):
                miss.append("워터마크·상표 낱말")
        rows.append({"src": str(b.get("src") or "")[:60], "conf": b.get("conf"), "tilt": tilt,
                     "area_pct": round(area * 100, 3), "prop": bool(b.get("prop")), "miss": miss})
    real = [b for b in boxes if not b.get("prop")]
    area = sum(max(0, b.get("w", 0)) * max(0, b.get("h", 0)) for b in real) / float(W * H) if W and H and real else 0.0
    confs = [float(b["conf"]) for b in real if b.get("conf") is not None]
    avg = round(sum(confs) / len(confs), 1) if confs else None
    minor = bool(real) and area < C.MINOR_AREA and (avg if avg is not None else 100.0) < C.MINOR_CONF \
        and not C.real_word_hit(" ".join(str(b.get("src") or "") for b in real))
    return {"ok": True, "why": "", "angle": ang, "frame": frame or "identity", "size": [W, H], "boxes": rows,
            "real_area_pct": round(area * 100, 3), "real_conf_avg": avg, "minor": minor,
            "minor_rule": f"Y11-D 「소품 글자(작음)」 줄 = 소품 아닌 상자 합계 면적 < {C.MINOR_AREA * 100:.1f}% 그리고 평균 확신 < {C.MINOR_CONF:.0f}"}


def _item(item_id: str):
    from src.db import pg as _pg
    from src.seller_console import collect_history_store as store
    uid = ""
    if _pg.pg_enabled():
        with _pg.query() as cur:
            cur.execute("SELECT user_id FROM collect_history WHERE id::text=%s", (item_id,))
            r = cur.fetchone()
        uid = r[0] if r else ""
    row = store.get(item_id, seller_ids={uid}) if uid else None
    return row, uid


def run(item_id: str, detail_idx: List[int]) -> Dict:
    """실측 한 번 — 결과 dict(저장은 호출자)."""
    from src.services import image_translate_tencent as tc
    from src.services import detail_image_plan as dip
    from src.services import coupang_image_check as C
    from src.services import prop_text as PT
    row, uid = _item(item_id)
    out = {"item": item_id, "at": datetime.now(timezone.utc).isoformat(), "pages": [], "rep": {}}
    if not row:
        out["error"] = "상품을 찾지 못했어요"
        return out
    ex = json.loads(row.get("extra_json") or "{}") or {}
    details = [u for u in ex.get("detail_images") or [] if u]
    for i in detail_idx:
        url = details[i] if 0 <= i < len(details) else ""
        page = {"idx": i, "no": i + 1, "url": url}
        raw, why = tc.fetch_image(url) if url else (b"", "주소 없음")
        if raw:
            data, info = dip.prepare_for_tencent(raw)
            page["size"] = [info.get("w"), info.get("h")]
            page["variants"] = measure_page(data) if data else []
            page["why"] = "" if data else str(info.get("note") or "")
        else:
            page["why"] = why
        out["pages"].append(page)
    try:
        from src.seller_console.product_builder import build_product
        pd = build_product(row, seller_id=uid)
        rep = C.rep_url(dict(pd), "coupang") or ((pd.get("images_effective") or pd.get("images") or [""])[0])
    except Exception as exc:                                     # noqa: BLE001
        rep = ""
        out["rep"] = {"why": f"대표 사진 주소를 못 구함({type(exc).__name__})"}
    if rep:
        raw, why = C._bytes_for(rep)
        out["rep"] = dict(url=rep[:200], **(explain_boxes(raw, exempt=PT.exempt(ex)) if raw else {"ok": False, "why": why}))
    return out


def start(item_id: str, detail_idx: List[int]) -> bool:
    """백그라운드로 한 번 — 이미 도는 중이면 False."""
    from src.db import image_translate_queue_pg as q
    if not _RUNNING.acquire(blocking=False):
        return False

    def _go():
        try:
            q.state_set(STATE_KEY, {"item": item_id, "running": True, "at": datetime.now(timezone.utc).isoformat()})
            res = run(item_id, detail_idx)
        except Exception as exc:                                 # noqa: BLE001
            logger.exception("[OCR 비교 진단] 실패")
            res = {"item": item_id, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        finally:
            _RUNNING.release()
        q.state_set(STATE_KEY, res)

    threading.Thread(target=_go, daemon=True, name="ocr-compare").start()
    return True


CENSUS_KEY = "diag:ocr_recheck"
OCR_SKIP_MARK = "OCR 판정 — 한자 0"


def ocr_skipped_pages(limit: int = 300) -> List[tuple]:
    """운영 전수 — 「OCR 판정 — 한자 0」으로 건너뛴 장 `(item_id, kind, idx, url)`. 읽기만 한다."""
    from src.db import pg as _pg
    if not _pg.pg_enabled():
        return []
    out = []
    with _pg.query() as cur:
        cur.execute("SELECT id::text, extra_json FROM collect_history WHERE deleted_at IS NULL AND extra_json::text LIKE %s",
                    ("%" + OCR_SKIP_MARK + "%",))
        rows = cur.fetchall()
    for iid, ex in rows:
        ex = ex if isinstance(ex, dict) else (json.loads(ex) if ex else {})
        for src_key, ko_key, kind in (("images", "images_ko", "gallery"), ("detail_images", "detail_images_ko", "detail")):
            urls = [u for u in ex.get(src_key) or [] if u]
            for e in ex.get(ko_key) or []:
                if isinstance(e, dict) and e.get("status") == "skipped" and OCR_SKIP_MARK in str(e.get("reason") or ""):
                    i = int(e.get("idx", -1))
                    if 0 <= i < len(urls):
                        out.append((iid, kind, i, urls[i]))
    return out[:limit]


def census(limit: int = 300) -> Dict:
    """전수 재판정 — 지금 사전검사(원본 크기·zh·라틴 규칙)로 다시 보면 한자 있음/모름(번역으로)/없음 몇 장인가. 장당 OCR 1회."""
    from src.services import detail_image_plan as dip
    from src.services import image_text_precheck as P
    from src.services import image_translate_tencent as tc
    pages = ocr_skipped_pages(limit)
    cnt = {"total": len(pages), "han": 0, "send": 0, "none": 0, "unknown": 0, "fetch_fail": 0}
    by_item: Dict[str, Dict[str, int]] = {}
    hits = []
    for iid, kind, i, url in pages:
        raw, _why = tc.fetch_image(url)
        data = dip.prepare_for_tencent(raw)[0] if raw else None
        if not data:
            cnt["fetch_fail"] += 1
            continue
        has, seen = P.han_text(data)
        key = "han" if has is True else ("none" if has is False else ("unknown" if not seen else "send"))
        cnt[key] += 1
        b = by_item.setdefault(iid, {"han": 0, "send": 0, "none": 0})
        if key in b:
            b[key] += 1
        if key in ("han", "send"):
            hits.append({"item": iid, "kind": kind, "idx": i, "no": i + 1, "seen": str(seen or "")[:40], "how": key})
    return {"at": datetime.now(timezone.utc).isoformat(), "count": cnt, "by_item": by_item, "hits": hits[:200]}


def start_census() -> bool:
    from src.db import image_translate_queue_pg as q
    if not _RUNNING.acquire(blocking=False):
        return False

    def _go():
        try:
            q.state_set(CENSUS_KEY, {"running": True, "at": datetime.now(timezone.utc).isoformat()})
            res = census()
        except Exception as exc:                                 # noqa: BLE001
            logger.exception("[OCR 전수 재판정] 실패")
            res = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        finally:
            _RUNNING.release()
        q.state_set(CENSUS_KEY, res)

    threading.Thread(target=_go, daemon=True, name="ocr-recheck").start()
    return True


def last_census() -> Dict:
    from src.db import image_translate_queue_pg as q
    return q.state_get(CENSUS_KEY)


def last() -> Dict:
    from src.db import image_translate_queue_pg as q
    return q.state_get(STATE_KEY)
