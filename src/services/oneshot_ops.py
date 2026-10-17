"""Y11X(오너 2026-10-17) — 한 장짜리 일회성 작업 줄: 「이 장만 다시 다듬기」 · 「이 장만 OCR 다시 판정」.

버튼(「번역 다듬기(이 상품)」·「OCR 다시 판정(이 상품)」)은 상품 전체를 돈다 — 오너가 **한 장만** 시킬 때(상세 13번만 재다듬,
상세 1번만 다시 판정) 다른 장의 캐시·과금을 건드리지 않으려고 둔다. 줄은 `app_state ops:oneshot:queue`, 결과는 `ops:oneshot:last`.
`/cron/translate-drain` 틱이 꺼내 **한 번만** 돌린다(꺼내자마자 줄에서 뺀다 — 실패해도 다시 돌지 않는다, 결과에 사유).

허용 작업은 둘뿐(그 밖의 줄은 「모르는 작업」으로 버린다):
- `polish_page` {item_id, kind, idx} — 그 장만 `image_polish.polish_job`(다시 만들 다듬음 버전일 때만 새로 그림)
- `ocr_recheck` {item_id, detail_idx:[…]} — 그 상세 장만 `ocr_compare_diag.run`(장당 OCR 4회)
- `attn_backfill` {} — Y12-A: 목록 정렬·「손댈 것」 열(`last_action_at`·`attn_n`)과 `extra.attn`을 등록 기록·등록 보류가 있는
  상품에만 한 번 채운다(그 밖의 칸은 손대지 않는다 · 한 번에 500건)
- `review_status` {item_id, market} — Y12-A(오너 23:31 Y11W-1): 그 상품·그 마켓 **상태만 1회 조회**(쿠팡 GET, 무료)하고
  성공 값만 등록 기록 `review`에 남긴다(막힌 조회는 덮지 않음 — 결정 8). 결과 원문 = `ops:oneshot:last`
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

QUEUE_KEY = "ops:oneshot:queue"
LAST_KEY = "ops:oneshot:last"
OPS = ("polish_page", "ocr_recheck", "attn_backfill", "review_status")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue_rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return [r for r in (st.state_get(QUEUE_KEY) or {}).get("rows") or [] if isinstance(r, dict)]


def _run(row: dict) -> Dict:
    op = str(row.get("op") or "")
    item_id = str(row.get("item_id") or "")
    if op not in OPS:
        return {"ok": False, "why": f"모르는 작업({op[:30]})"}
    if op == "attn_backfill":
        return _attn_backfill()
    if op == "review_status":
        return _review_status(item_id, str(row.get("market") or ""))
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    item_id = str(item.get("id") or item_id)
    if op == "polish_page":
        from src.services import image_polish as IP
        kind, idx = str(row.get("kind") or "detail"), int(row.get("idx"))
        res = IP.polish_job(item_id, uid, kind, idx) or {}
        return {"ok": bool(res.get("ok")), "changed": res.get("changed", 0), "version": res.get("version") or "",
                "calls": res.get("calls", 0), "why": str(res.get("why") or "")[:160],
                "rows": [{k: r.get(k) for k in ("id", "src", "tgt", "ko", "from", "why")} for r in res.get("rows") or []][:20]}
    idx = [int(i) for i in row.get("detail_idx") or []][:6]
    if not idx:
        return {"ok": False, "why": "판정할 장 번호가 없어요"}
    res = D.run(item_id, idx)
    from src.db import image_translate_queue_pg as st
    st.state_set(D.STATE_KEY, res)                               # 화면(진단·드로어 줄)이 이 결과를 읽는다
    st.state_set(D.item_key(item_id), res)
    return {"ok": not res.get("error"), "count": res.get("count"), "line": D.line(res), "at": res.get("at"),
            "pages": [{k: p.get(k) for k in ("no", "idx", "verdict", "why", "url")} for p in res.get("pages") or []]}


def drain() -> Dict:
    """줄을 통째로 꺼내(먼저 비운다 — 한 번만) 차례로 돌린다. `{picked, rows}`."""
    from src.db import image_translate_queue_pg as st
    rows = queue_rows()
    if not rows:
        return {"picked": 0, "rows": []}
    st.state_set(QUEUE_KEY, {"rows": []})
    out = []
    for r in rows[:5]:
        try:
            res = _run(r)
        except Exception as exc:                                 # noqa: BLE001 — 한 줄 실패가 다른 줄을 막지 않는다
            logger.warning("[일회성 작업] %s 실패: %s", r.get("op"), exc)
            res = {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
        out.append({**{k: r.get(k) for k in ("op", "item_id", "kind", "idx", "detail_idx", "reason")}, "result": res, "at": _now()})
        logger.info("[일회성 작업] %s item=%s ok=%s why=%s", r.get("op"), str(r.get("item_id") or "")[:8], res.get("ok"),
                    str(res.get("why") or "")[:120])
    st.state_set(LAST_KEY, {"at": _now(), "rows": out})
    return {"picked": len(out), "rows": out}


def _attn_backfill() -> Dict:
    import json
    from src.db import collect_history_pg as chp
    from src.seller_console.attention import last_action, summarize, items as attn_items
    done = 0
    for item_id, uid in chp.ids_for_attention_backfill():
        row = chp.get(item_id, seller_ids={uid} if uid else None) or {}
        try:
            ex = json.loads(row.get("extra_json") or "{}") or {}
        except Exception:                                        # noqa: BLE001
            continue
        attn = summarize(ex, row.get("title") or "")
        n = len(attn_items(ex, row.get("title") or "", fresh=True))
        la = last_action(ex, row.get("collected_at") or "")
        has = bool(int(attn.get("erase") or 0) or attn.get("check"))
        if chp.set_attention(item_id, la["at"] or row.get("collected_at"), n, attn if has else None):
            done += 1
    return {"ok": True, "done": done}


def _review_status(item_id: str, market: str) -> Dict:
    """한 상품·한 마켓 상태 1회 조회 → 성공 값만 기록(`listing_status.remember`). 화면 팝업 「마켓 상태」와 같은 길."""
    import json
    from src.seller_console import collect_history_store as store
    from src.seller_console import listing_status as MS
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    item_id = str(item.get("id") or item_id)
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        return {"ok": False, "why": "상품 기록을 읽지 못했어요"}
    recs = [r for r in MS.records(ex) if r["market"] == market]
    if not recs:
        return {"ok": False, "why": f"등록 기록 없음({market[:30]})"}
    MS.reset_cache()
    row = MS.query(recs[-1])
    saved = False
    if MS.remember(ex, row):
        saved = store.merge_extra(item_id, lambda fresh: MS.remember(fresh, row), seller_ids={uid} if uid else None)
    return {"ok": not row.get("error"), "market": market, "state": row.get("state"), "label": row.get("label"),
            "status_raw": row.get("status_raw"), "comment": str(row.get("comment") or "")[:200],
            "checked_at": row.get("checked_at"), "stale": bool(row.get("stale")),
            "why": str(row.get("stale_note") or row.get("error") or "")[:200], "saved": bool(saved)}
