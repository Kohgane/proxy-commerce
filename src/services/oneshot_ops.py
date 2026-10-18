"""Y11X(오너 2026-10-17) — 한 장짜리 일회성 작업 줄: 「이 장만 다시 다듬기」 · 「이 장만 OCR 다시 판정」.

버튼(「번역 다듬기(이 상품)」·「OCR 다시 판정(이 상품)」)은 상품 전체를 돈다 — 오너가 **한 장만** 시킬 때(상세 13번만 재다듬,
상세 1번만 다시 판정) 다른 장의 캐시·과금을 건드리지 않으려고 둔다. 줄은 `app_state ops:oneshot:queue`, 결과는 `ops:oneshot:last`.
`/cron/translate-drain` 틱이 꺼내 **한 번만** 돌린다(꺼내자마자 줄에서 뺀다 — 실패해도 다시 돌지 않는다, 결과에 사유).

허용 작업은 둘뿐(그 밖의 줄은 「모르는 작업」으로 버린다):
- `polish_page` {item_id, kind, idx} — 그 장만 `image_polish.polish_job`(다시 만들 다듬음 버전일 때만 새로 그림)
- `ocr_recheck` {item_id, detail_idx:[…]} — 그 상세 장만 `ocr_compare_diag.run`(장당 OCR 4회)
- `attn_backfill` {} — Y12-A: 목록 정렬·「손댈 것」 열(`last_action_at`·`attn_n`)과 `extra.attn`을 등록 기록·등록 보류가 있는
  상품에만 한 번 채운다(그 밖의 칸은 손대지 않는다 · 한 번에 500건). Y12-B: 수집 실패 후보(보강 대기·막힘 · 보강 축 없이
  가격·갤러리 둘 다 빈 상품)도 — 「손댈 것 · 수집 실패」·「재수집 대기」 요약을 옛 행에도 붙인다
- `review_status` {item_id, market} — Y12-A(오너 23:31 Y11W-1): 그 상품·그 마켓 **상태만 1회 조회**(쿠팡 GET, 무료)하고
  성공 값만 등록 기록 `review`에 남긴다(막힌 조회는 덮지 않음 — 결정 8). 결과 원문 = `ops:oneshot:last`
- `prevalidate` {item_id, markets?} — Y13-A(오너 2026-10-18 「두 상품 사전검증 다시 돌려서 결과표」): 그 상품 계정으로
  화면과 **같은 사전검증 잡**을 띄운다(몸통 = 등록 빌더 `build_product`). 결과는 잡 기록 `prevalidate_job:<id>`(화면이 읽는 그것)
- `image_probe` {item_id, kind, idx:[…]} — Y13-A: 실제 주소를 서버에서 받아 형식·크기·base64·정규화 결과를 남기고 텐센트 OCR에
  한 번 보내 응답 코드를 남긴다(장당 OCR 1회 · 최대 6장 · 번역은 안 보냄). `InvalidParameterValue.Data` 재현 로그
- `carry_requeue` {item_ids:[…]} — Y13-A 9(오너 16:41 「12건 이월 대기열로 재투입」): 4013 분류(#45) 전에 `provider_fail`로 적힌
  공유 초안을 `provider_quota`로 바로잡고(5000 등 다른 사유는 사유 그대로) 이월 대기에 넣는다 — 한도가 풀리는 날 워커가 1회씩 부른다.
  수집 원본·다른 칸은 손대지 않는다(`auto_enrich.kind`·`carry_requeued_at`만)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

QUEUE_KEY = "ops:oneshot:queue"
LAST_KEY = "ops:oneshot:last"
OPS = ("polish_page", "ocr_recheck", "attn_backfill", "review_status", "prevalidate", "image_probe", "carry_requeue")


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
    if op == "prevalidate":
        return _prevalidate(item_id, [str(m) for m in (row.get("markets") or []) if m])
    if op == "carry_requeue":
        return _carry_requeue([str(i) for i in (row.get("item_ids") or []) if i][:50])
    if op == "image_probe":
        return _image_probe(item_id, str(row.get("kind") or "detail"), [int(i) for i in (row.get("idx") or [])][:6])
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
    from src.seller_console.attention import _has, last_action, summarize, items as attn_items
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
        if chp.set_attention(item_id, la["at"] or row.get("collected_at"), n, attn if _has(attn) else None):
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


PREVALIDATE_MARKETS = ("coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos")


def _prevalidate(item_id: str, markets: List[str]) -> Dict:
    """화면 「사전검증」과 같은 잡 — 그 상품 계정 세션으로(자격·마켓 키가 그 계정 것). 잡 id만 돌려준다(결과는 잡 기록)."""
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    if not uid:
        return {"ok": False, "why": "상품 계정을 알 수 없어요(세션 없이 돌리지 않는다)"}
    from flask import session
    from src.order_webhook import app
    from src.seller_console import views as V
    from src.seller_console.product_builder import build_product
    mk = [m for m in (markets or PREVALIDATE_MARKETS) if m in PREVALIDATE_MARKETS]
    data = {"product": build_product(item, edits={}, seller_id=uid), "markets": mk, "item_id": str(item.get("id") or item_id)}
    with app.test_request_context("/seller/collect/prevalidate", method="POST"):
        session["user_id"] = uid
        dispatcher = V._get_upload_dispatcher()
        if dispatcher is None:
            return {"ok": False, "why": "업로드 디스패처를 불러오지 못했어요"}
        resp = V._pv_start_job(data, mk, dispatcher)
    body = (resp[0] if isinstance(resp, tuple) else resp).get_json() or {}
    return {"ok": bool(body.get("job_id")), "job_id": body.get("job_id") or "", "markets": mk,
            "why": "" if body.get("job_id") else str(body.get("error") or "잡을 띄우지 못했어요")[:160]}


def _image_probe(item_id: str, kind: str, idxs: List[int]) -> Dict:
    """장마다: 저장 주소 → 정리 주소 → 받기(형식·크기·바이트·base64) → 텐센트 입력 정규화 → OCR 1회 응답 코드."""
    import json
    from src.collectors.image_norm import abs_image_url, image_head
    from src.services import ocr_compare_diag as D
    from src.services import detail_image_plan as P
    from src.services import image_translate_tencent as tc
    from src.services import ocr_tencent as O
    item, _uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    src = {"detail": "detail_images", "gallery": "images"}.get(kind, "detail_images")
    urls = [u for u in (ex.get(src) or []) if isinstance(u, str)]
    rows = []
    for i in idxs:
        if not 0 <= i < len(urls):
            rows.append({"idx": i, "why": "그 번호의 사진이 없어요"})
            continue
        raw_url = urls[i]
        url = P.fix_url(raw_url)
        row = {"idx": i, "stored": raw_url[:160], "url": url[:160], "scheme_fixed": abs_image_url(raw_url) != raw_url.strip(),
               "excluded": P.url_exclusion(url)}
        data, why = tc.fetch_image(url)
        if why:
            row["fetch"] = why
            rows.append(row)
            continue
        fmt, w, h = image_head(data)[:3]
        row.update(fmt=fmt, w=w, h=h, bytes=len(data), b64=int(len(data) * 4 / 3))
        norm, info = P.prepare_for_tencent(data, url=url)
        row["prepare"] = {"sent": "원본 그대로" if norm is data else ("안 보냄" if norm is None else "바꿈"),
                          "note": str(info.get("note") or ""), "bytes": len(norm or b"")}
        if norm is not None:
            r = O.read(norm, max_side=O.AS_IS)
            row["ocr"] = {"ok": bool(r.get("ok")), "code": str(r.get("code") or ""), "why": str(r.get("why") or "")[:160],
                          "lines": len(r.get("lines") or [])}
        rows.append(row)
        data = norm = None
    return {"ok": True, "kind": kind, "rows": rows}


def _carry_requeue(item_ids: List[str]) -> Dict:
    """옛 4013 기록 → `provider_quota` + 이월 대기. 보강 대기(`enrich_state=pending`) 공유 초안만 — 그 밖은 건너뛴 사유를 남긴다."""
    import json
    from src.seller_console import collect_history_store as store
    from src.services import ocr_compare_diag as D
    from src.services import onebound_carry as carry
    rows = []
    for iid in item_ids:
        item, uid = D._item(iid)
        if not item:
            rows.append({"item_id": iid[:8], "why": "상품 없음"})
            continue
        try:
            ex = json.loads(item.get("extra_json") or "{}") or {}
        except Exception:                                        # noqa: BLE001
            ex = {}
        ae = ex.get("auto_enrich") if isinstance(ex.get("auto_enrich"), dict) else {}
        if ex.get("enrich_state") != "pending":
            rows.append({"item_id": iid[:8], "why": f"보강 대기 아님({ex.get('enrich_state') or '없음'})"})
            continue
        reason = str(ae.get("reason") or "")
        kind = "provider_quota" if ("4013" in reason or "已超量" in reason) else str(ae.get("kind") or "")
        now = datetime.now(timezone.utc).isoformat()

        def _fix(fresh, kind=kind, now=now):
            a = fresh.get("auto_enrich") if isinstance(fresh.get("auto_enrich"), dict) else {}
            if a and a.get("kind") != kind:
                fresh["auto_enrich"] = dict(a, kind=kind)
            fresh["carry_requeued_at"] = now
            return True
        store.merge_extra(str(item.get("id") or iid), _fix, seller_ids={uid} if uid else None)
        pos = carry.add(uid, str(item.get("id") or iid), url=str(item.get("url") or ""),
                        share=str(ex.get("share_raw") or ""), kind=kind)
        rows.append({"item_id": iid[:8], "kind": kind, "position": pos})
    return {"ok": True, "queued": sum(1 for r in rows if r.get("position")), "rows": rows, "waiting": carry.count()}
