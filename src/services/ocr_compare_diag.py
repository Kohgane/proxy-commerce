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
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_KEY = "diag:ocr_compare"
OCR_SKIP_MARK = "OCR 판정 — 한자 0"
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
    else:                                                        # 인메모리(개발·테스트)
        r = next((x for x in store._in_memory if x.get("id") == item_id), None)
        uid = str((r or {}).get("seller_id") or "")
    row = store.get(item_id, seller_ids={uid}) if (uid or item_id) else None
    return row, uid


def resolve(q: str, limit: int = 20) -> List[Dict]:
    """Y11-K(오너 2026-10-14): 사람은 상품 ID를 모른다 — 상품 ID(앞 6자 이상도) · SKU(상품번호) · 상품명 일부 · 수집 URL 무엇이든.
    `[{id, sku, title, collected_at, user_id}]` 최근 수집 순. 읽기만 한다."""
    q = str(q or "").strip()
    if len(q) < 2:
        return []
    from src.db import pg as _pg
    from src.collectors.product_key import vendor_sku
    rows = []
    if _pg.pg_enabled():
        like = "%" + q.replace("%", "").replace("_", "\\_") + "%"
        with _pg.query() as cur:
            cur.execute("SELECT id::text, user_id, title, url, extra_json->>'title_ko', created_at FROM collect_history "
                        "WHERE deleted_at IS NULL AND (id::text = %s OR (length(%s) >= 6 AND id::text LIKE %s) "
                        "OR url ILIKE %s OR title ILIKE %s OR extra_json->>'title_ko' ILIKE %s) "
                        "ORDER BY created_at DESC LIMIT %s",
                        (q, q, q.lower() + "%", like, like, like, int(limit)))
            rows = cur.fetchall()
    else:
        from src.seller_console import collect_history_store as store
        for r in reversed(store._in_memory):
            iid = str(r.get("id") or "")
            ex = {}
            try:
                ex = json.loads(r.get("extra_json") or "{}") or {}
            except Exception:                                    # noqa: BLE001
                pass
            hay = " ".join(str(x or "") for x in (r.get("url"), r.get("title"), ex.get("title_ko"))).lower()
            if iid == q or (len(q) >= 6 and iid.startswith(q.lower())) or q.lower() in hay:
                rows.append((iid, r.get("seller_id"), r.get("title"), r.get("url"), ex.get("title_ko"), r.get("collected_at")))
        rows = rows[:limit]
    out = []
    for iid, uid, title, url, title_ko, at in rows:
        try:
            sku = vendor_sku(url or "") or ""
        except Exception:                                        # noqa: BLE001
            sku = ""
        out.append({"id": iid, "user_id": uid or "", "sku": str(sku), "title": str(title_ko or title or "")[:60],
                    "collected_at": at.isoformat() if hasattr(at, "isoformat") else str(at or "")})
    return out


def item_key(item_id: str) -> str:
    return f"{STATE_KEY}:{item_id}"


#: 이 상품 「OCR 다시 판정」 — 「한자 0」으로 건너뛴 장마다 4방식(장당 OCR 4회). 상한(과금 보호).
ITEM_PAGE_CAP = int(os.getenv("OCR_RECHECK_ITEM_CAP", "20") or 20)


def _skipped_of(ex: dict) -> List[tuple]:
    out = []
    for src_key, ko_key, kind in (("images", "images_ko", "gallery"), ("detail_images", "detail_images_ko", "detail")):
        urls = [u for u in ex.get(src_key) or [] if u]
        for e in ex.get(ko_key) or []:
            if isinstance(e, dict) and e.get("status") == "skipped" and OCR_SKIP_MARK in str(e.get("reason") or ""):
                i = int(e.get("idx", -1))
                if 0 <= i < len(urls):
                    out.append((kind, i, urls[i]))
    return out


def verdict(variants: List[Dict]) -> str:
    """지금 사전검사(원본·zh) 값으로 판정 — han(한자 나옴) · send(라틴 있어 번역으로) · none(글자 거의 없음) · unknown."""
    from src.services.image_text_precheck import LATIN_MIN
    v = next((x for x in variants or [] if x.get("name") == "원본·zh"), None)
    if not v or not v.get("ok"):
        return "unknown"
    return "han" if v["han"] else ("send" if v["latin"] >= LATIN_MIN else "none")


def run(item_id: str, detail_idx: Optional[List[int]] = None) -> Dict:
    """실측 한 번 — 결과 dict(저장은 호출자). `detail_idx`가 없으면 이 상품의 「한자 0」 장 전부(상한 ITEM_PAGE_CAP)."""
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
    if detail_idx is None:
        targets = _skipped_of(ex)
        out["skipped_total"] = len(targets)
        targets = targets[:ITEM_PAGE_CAP]
    else:
        details = [u for u in ex.get("detail_images") or [] if u]
        targets = [("detail", i, details[i] if 0 <= i < len(details) else "") for i in detail_idx]
    for kind, i, url in targets:
        url = dip.fix_url(url) if url else url                 # Y11-L: 「//img…」 같은 주소(번역 경로는 고쳐서 받는다 — 진단도 같게)
        page = {"kind": kind, "idx": i, "no": i + 1, "url": url}
        raw, why = tc.fetch_image(url) if url else (b"", "주소 없음")
        if raw:
            data, info = dip.prepare_for_tencent(raw)
            page["size"] = [info.get("w"), info.get("h")]
            page["variants"] = measure_page(data) if data else []
            page["why"] = "" if data else str(info.get("note") or "")
        else:
            page["why"] = why
        page["verdict"] = verdict(page.get("variants") or [])
        out["pages"].append(page)
    cnt = {"han": 0, "send": 0, "none": 0, "unknown": 0}
    for p in out["pages"]:
        cnt[p["verdict"]] += 1
    out["count"] = cnt
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


def run_at(res: Dict) -> str:
    """Y11X: 결과를 잰 시각(KST 「10-14 22:02」) — 오래된 결과를 지금 결과로 읽지 않게 결과줄 끝에 붙인다. 못 읽으면 ""."""
    from datetime import timedelta
    raw = str((res or {}).get("at") or "").strip()
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M") + " KST"


def line(res: Dict) -> str:
    """결과줄 — 「OCR 다시 판정 14장: 한자 나옴 n · … — 「다시 번역」을 누르면 접수 · 10-14 22:02 KST」(끝 = 잰 시각)."""
    s = _line(res)
    when = run_at(res) if s and not (res or {}).get("running") else ""
    return f"{s} · {when}" if when else s


def _line(res: Dict) -> str:
    if not res:
        return ""
    if res.get("running"):
        return "OCR 다시 판정 중… (1~2분)"
    if res.get("error"):
        return "OCR 다시 판정 실패 — " + str(res["error"])
    c = res.get("count") or {}
    n = len(res.get("pages") or [])
    if not n:
        return "OCR 다시 판정: 「한자 0」으로 건너뛴 사진이 없어요"
    tail = f" (이번엔 {n}장만 — 상한)" if int(res.get("skipped_total") or n) > n else ""
    s = (f"OCR 다시 판정 {n}장{tail}: 한자 나옴 {c.get('han', 0)} · 라틴 있어 번역으로 {c.get('send', 0)} · "
         f"글자 거의 없음 {c.get('none', 0)}")
    if c.get("unknown"):
        whys = [str(p.get("why") or next((v.get("why") for v in p.get("variants") or [] if v.get("why")), "") or "")
                for p in res.get("pages") or [] if p.get("verdict") == "unknown"]
        whys = [w for w in whys if w]
        s += f" · 판정 못 함 {c['unknown']}" + (f"({max(set(whys), key=whys.count)[:40]})" if whys else "")
    if c.get("han") or c.get("send"):
        s += " — 「다시 번역」을 누르면 접수돼요"
    return s


def start(item_id: str, detail_idx: Optional[List[int]] = None) -> Dict:
    """`{ok, why?, item}` — 상품을 **먼저** 찾고(못 찾으면 시작하지 않는다 — Y11-K 순서 버그) 백그라운드로 한 번."""
    from src.db import image_translate_queue_pg as q
    row, _uid = _item(item_id)
    if not row:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    if not _RUNNING.acquire(blocking=False):
        return {"ok": False, "why": "다른 OCR 판정이 도는 중이에요 — 끝나면 다시 눌러 주세요"}

    def _go():
        res = {}
        try:
            run_at = {"item": item_id, "running": True, "at": datetime.now(timezone.utc).isoformat()}
            q.state_set(STATE_KEY, run_at)
            q.state_set(item_key(item_id), run_at)
            res = run(item_id, detail_idx)
        except Exception as exc:                                 # noqa: BLE001
            logger.exception("[OCR 비교 진단] 실패")
            res = {"item": item_id, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        finally:
            _RUNNING.release()
        q.state_set(STATE_KEY, res)
        q.state_set(item_key(item_id), res)

    threading.Thread(target=_go, daemon=True, name="ocr-compare").start()
    return {"ok": True, "item": item_id}


def last_item(item_id: str) -> Dict:
    from src.db import image_translate_queue_pg as q
    return q.state_get(item_key(item_id))


CENSUS_KEY = "diag:ocr_recheck"


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
        raw, _why = tc.fetch_image(dip.fix_url(url))
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
