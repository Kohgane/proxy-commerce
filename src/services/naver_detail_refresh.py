"""Y11-V(오너 2026-10-16 19:12) — 네이버 등록본 상세 본문 **자동 다시 보내기** 큐.

실측(VRSUK 셰고가·고코스모스): 네이버 등록은 10-15 19:19 UTC에 나갔고, 그 뒤 다듬기·소품 판정·판촉 제외가 바뀌었는데
본문은 그대로였다 — 상세 첫 장에 티몰 입점 배너(「天猫国际邀请入驻 …」)가 중국어 그대로 남았다(지금 규칙으론 빠지는 장).
쿠팡은 상세 갱신 큐가 있었고 네이버는 「본문 다시 보내기」 버튼뿐이었다.

규칙(쿠팡 상세 갱신 큐와 같은 모양):
- 번역본·다듬은 버전·사진 편집이 바뀌면 이 상품의 네이버 등록본마다 줄을 **하나** 세운다(`app_state naver_detail_refresh:queue`).
- `/cron/translate-drain` 틱이 큐를 비운다. 이 상품의 이미지 번역·다듬기가 아직 돌고 있으면 기다린다(장마다 보내지 않는다).
- 네이버 상태가 **판매중(승인)** 일 때만 보낸다. 본문(사진 주소·글) 해시가 마지막으로 보낸 것과 같으면 보내지 않는다.
- 결과(네이버 응답 원문)는 `uploaded[].detail_sync`와 `app_state naver_detail_refresh:last`에.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

QUEUE_KEY = "naver_detail_refresh:queue"
LAST_KEY = "naver_detail_refresh:last"
MAX_TRIES = 12
REASON = "번역본·다듬기 바뀜"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(html: str) -> str:
    return hashlib.sha1(str(html or "").encode("utf-8")).hexdigest()[:16]


def naver_uploads(ex: dict) -> List[dict]:
    from src.seller_console import listing_status as MS
    return [r for r in MS.records(ex or {}) if r["market"].startswith("smartstore") and r.get("product_id")]


def queue_rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return list((st.state_get(QUEUE_KEY) or {}).get("rows") or [])


def _queue_set(rows: List[dict]) -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(QUEUE_KEY, {"rows": rows})


def _queue_drop(item_id: str, market: str) -> None:
    _queue_set([r for r in queue_rows() if not (r.get("item_id") == item_id and r.get("market") == market)])


def enqueue_item(item_id: str, extra: dict, seller_id: str = "", reason: str = REASON) -> int:
    """이 상품의 네이버 등록본마다 줄을 세운다(이미 서 있으면 그대로). 세운 줄 수."""
    try:
        recs = naver_uploads(extra)
        if not recs:
            return 0
        rows = queue_rows()
        have = {(r.get("item_id"), r.get("market")) for r in rows}
        n = 0
        for rec in recs:
            if (str(item_id), rec["market"]) in have:
                continue
            rows.append({"item_id": str(item_id), "market": rec["market"], "seller_id": seller_id, "reason": reason,
                         "at": _now(), "tries": 0})
            n += 1
        if n:
            _queue_set(rows)
        return n
    except Exception as exc:                                     # noqa: BLE001 — 줄 세우기는 덤 — 편집 결과는 그대로
        logger.warning("[네이버 본문 갱신] 줄 세우기 실패 item=%s: %s", str(item_id)[:8], exc)
        return 0


def body_payload(item: dict, seller_id: str = "") -> dict:
    """등록과 같은 빌더 → 나갈 갤러리·상세·옵션 사진(번역본 사용 반영 · 우리 서버 주소는 CDN으로, 못 올리면 뺌) →
    네이버 몸통(`_payload_for_market`). 세션이 없는 크론에서도 돈다."""
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import build_dispatch_payload, UploadDispatcher
    from src.services import image_translate_store as _its
    from src.services.coupang_detail_refresh import _effective_detail_images
    pd = build_dispatch_payload(build_product(item, edits={}, seller_id=seller_id), item)
    ex = json.loads(item.get("extra_json") or "{}") or {}
    iid = str(item.get("id") or "")
    gal = _its.effective_images(ex, item_id=iid, originals=pd.get("images") or [])
    if gal:
        pd["images"] = gal
    _effective_detail_images(item, pd)
    pd["item_id"] = iid
    payload, _loc = UploadDispatcher._payload_for_market(dict(pd), "smartstore")
    return payload


def item_busy(item_id: str) -> bool:
    """이 상품의 이미지 번역·다듬기가 아직 줄에 있나(있으면 다음 회전에 — 장마다 보내지 않는다)."""
    try:
        from src.db import image_translate_queue_pg as q
        c = q.counts(item_id) or {}
        return int(c.get("queued") or 0) + int(c.get("running") or 0) > 0
    except Exception:                                            # noqa: BLE001
        return False


def refresh_one(item: dict, rec: dict, *, seller_id: str = "", make_up: Optional[Callable[[], object]] = None,
                status_of: Optional[Callable[[dict], dict]] = None) -> dict:
    """등록본 하나 — `{market, sent, ok, state, same, error, raw, images, dropped}`. 판매중이 아니면 보내지 않는다."""
    from src.seller_console import listing_status as MS
    from src.seller_console import market_credentials as mc
    from src.seller_console.upload_dispatcher import _for_market
    m = rec["market"]
    row = {"market": m, "product_id": rec["product_id"], "channel_product_no": rec.get("channel_product_no") or "",
           "sent": False, "ok": False, "state": "", "same": False, "error": "", "raw": "", "at": _now()}
    with mc.seller_market_env(seller_id, [m]):
        _base, ctx = _for_market(m)
        with ctx:
            st = (status_of or MS._naver)(rec)
            row["state"] = str(st.get("state") or "")
            if row["state"] != "approved":
                row["error"] = f"판매중이 아니라 기다려요({st.get('label') or st.get('error') or '상태 모름'})"
                return row
            payload = body_payload(item, seller_id)
            html = str(payload.get("description_html") or "")
            h = _hash(html)
            ex = json.loads(item.get("extra_json") or "{}") or {}
            last = next((u.get("detail_sync") for u in ex.get("uploaded") or []
                         if isinstance(u, dict) and u.get("market") == m and isinstance(u.get("detail_sync"), dict)), None) or {}
            row["hash"] = h
            if last.get("ok") and last.get("hash") == h:
                row.update(ok=True, same=True, error="같은 본문을 이미 보냈어요")
                return row
            from src.uploaders import naver_detail as _nd
            if make_up is None:
                from src.channel_sync.smartstore_uploader import make_uploader as make_up
            up = make_up()
            v = _nd.judge(html, up, str(payload.get("sku") or item.get("id") or ""))
            row["images"] = len(__import__("re").findall(r"<img\b", v.get("html") or ""))
            from src.services import sent_images as _si
            row["sent_images"] = _si.from_html(v.get("html") or "")         # Y11X: 보낸 사진 주소 목록(쿠팡과 같은 꼴)
            row["dropped"] = [str(d.get("reason") or "")[:160] for d in v.get("dropped") or []]
            if not v.get("ok"):
                row["error"] = "보낼 상세 본문이 비었어요(사진을 하나도 못 올렸고 글도 없음)"
                return row
            res = up.update_detail_content(rec["product_id"], v["html"])
            row["sent"] = True
            row.update(ok=bool(res.get("success")), error=str(res.get("error") or "")[:500],
                       raw=str(res.get("raw") or res.get("body") or json.dumps({k: res[k] for k in res if k not in ("before",)},
                                                                               ensure_ascii=False, default=str))[:2000])
    return row


def store_save(item_id: str, seller_ids: Optional[set] = None) -> Callable[[dict], None]:
    """Y11X — `drain(save_for=…)`용: **이 상품 네이버 등록본의 `detail_sync`만** 지금 DB 값에 덧대 저장한다
    (같은 틱의 쿠팡 갱신 기록·다듬기 결과를 덮지 않는다)."""
    from src.seller_console import collect_history_store as store

    def _save(ex: dict) -> None:
        mine = {u.get("market"): u["detail_sync"] for u in (ex or {}).get("uploaded") or []
                if isinstance(u, dict) and isinstance(u.get("detail_sync"), dict)}

        def _apply(fresh: dict) -> None:
            for u in fresh.get("uploaded") or []:
                if isinstance(u, dict) and u.get("market") in mine:
                    u["detail_sync"] = mine[u["market"]]
        store.merge_extra(str(item_id), _apply, seller_ids=seller_ids)
    return _save


def drain(get_item: Callable[[str, str], Optional[dict]], save_for: Callable[[str, str], Callable[[dict], None]],
          *, budget: int = 6, make_up=None, status_of=None) -> Dict:
    out = {"picked": 0, "sent": 0, "ok": 0, "left": 0, "rows": []}
    for q in queue_rows()[:budget]:
        out["picked"] += 1
        item = get_item(q["item_id"], q.get("seller_id") or "")
        if not item:
            _queue_drop(q["item_id"], q["market"])
            continue
        if int(q.get("tries") or 0) >= MAX_TRIES:
            _queue_drop(q["item_id"], q["market"])
            out["rows"].append({**q, "dropped": "시도 상한"})
            continue
        if item_busy(q["item_id"]):
            out["rows"].append({**q, "waiting": "이미지 번역·다듬기 진행 중"})
            continue
        ex = json.loads(item.get("extra_json") or "{}") or {}
        rec = next((r for r in naver_uploads(ex) if r["market"] == q["market"]), None)
        if not rec:
            _queue_drop(q["item_id"], q["market"])
            continue
        try:
            row = refresh_one(item, rec, seller_id=q.get("seller_id") or "", make_up=make_up, status_of=status_of)
        except Exception as exc:                                 # noqa: BLE001 — 한 등록본 실패가 다른 것을 막지 않는다
            row = {"market": q["market"], "sent": False, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                   "at": _now()}
        out["sent"] += int(bool(row.get("sent")))
        out["ok"] += int(bool(row.get("ok")))
        out["rows"].append(row)
        if row.get("ok"):
            _queue_drop(q["item_id"], q["market"])
        elif str(row.get("state") or "") in ("", "unknown", "approved"):
            # 보냈는데 실패 · 상태를 못 읽음 · 빈 본문 = 시도 1회. 판매중이 아닌 상태(판매대기 등)를 기다리는 건 세지 않는다.
            rows = queue_rows()
            for r in rows:
                if r.get("item_id") == q["item_id"] and r.get("market") == q["market"]:
                    r["tries"] = int(r.get("tries") or 0) + 1
                    r["raw"] = (str(row.get("error") or "") + " " + str(row.get("raw") or ""))[:1500]
            _queue_set(rows)
        if row.get("sent") or row.get("same"):
            for u in ex.get("uploaded") or []:
                if isinstance(u, dict) and u.get("market") == q["market"]:
                    u["detail_sync"] = {k: row.get(k) for k in ("hash", "ok", "at", "error", "images", "same")}
                    if row.get("sent_images"):
                        u["detail_sync"]["sent_images"] = row["sent_images"]
                    u["detail_sync"]["raw"] = str(row.get("raw") or "")[:600]
            try:
                save_for(q["item_id"], q.get("seller_id") or "")(ex)
            except Exception as exc:                             # noqa: BLE001
                logger.warning("[네이버 본문 갱신] 기록 저장 실패: %s", exc)
        logger.info("[네이버 본문 갱신] item=%s %s sent=%s ok=%s state=%s err=%s", q["item_id"][:8], q["market"],
                    row.get("sent"), row.get("ok"), row.get("state"), str(row.get("error") or "")[:200])
    out["left"] = len(queue_rows())
    return out


def record_last(out: dict) -> None:
    try:
        from src.db import image_translate_queue_pg as st
        keep = ("market", "product_id", "channel_product_no", "sent", "ok", "state", "same", "error", "raw", "images",
                "dropped", "waiting", "reason", "tries", "at", "sent_images")
        rows = [{k: r.get(k) for k in keep if k in r} for r in (out.get("rows") or [])][:10]
        st.state_set(LAST_KEY, {"at": _now(), **{k: out.get(k) for k in ("picked", "sent", "ok", "left")}, "rows": rows})
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[네이버 본문 갱신] 마지막 결과 기록 실패: %s", exc)
