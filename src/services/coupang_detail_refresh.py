"""Y11-Q(오너 2026-10-16 00:38) — 이미 쿠팡에 등록된 상품의 **상세(contents)를 다시 보낸다**(상품 수정 API).

계기: VRSUK 첫 등록(쿠팡 고가네 16415921785 · 우주대행 16415921921) 때 텐센트 텍스트 번역이 전부 실패해(RequestLimitExceeded·
InvalidParameterValue) 규격 51칸이 빠진 상세로 나갔다. 번역이 성공하면 그 상세로 등록본을 갱신한다.

- 새 상세 = 등록과 **같은 빌더**(`build_dispatch_payload` → `prepared_input` → `prepare_product` → `_build_contents`).
  나갈 상세에 번역 실패 칸이 남아 있으면(규격이 빠진다) 보내지 않고 「번역 대기」로 큐에 둔다.
- 몸통 = 쿠팡 조회 원문(`get_product`)에서 **items[].contents만** 바꾼 것(가격·재고·옵션·이미지는 그대로) — U1b와 같은 방식.
- 수정은 쿠팡 「승인필요」 API — 판매중 상품도 다시 심사. 검토 중이라 막히면 **그 응답 원문**을 기록하고
  「승인 후 자동 갱신」 큐(`app_state coupang_detail_refresh:queue`)에 넣는다. `/cron/coupang-detail-refresh`가 승인되면 다시 보낸다.
- 같은 상세(해시)를 이미 보냈으면 다시 보내지 않는다(쿠팡 재심사를 두 번 부르지 않게).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

QUEUE_KEY = "coupang_detail_refresh:queue"
MAX_TRIES = 48                      # 크론이 30분마다면 하루 — 그 뒤엔 큐에서 빼고 사유를 남긴다


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(contents) -> str:
    return hashlib.sha1(json.dumps(contents, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def coupang_uploads(ex: dict) -> List[dict]:
    out = []
    for u in (ex or {}).get("uploaded") or []:
        if isinstance(u, dict) and str(u.get("market") or "").startswith("coupang") and str(u.get("product_id") or "").strip():
            out.append({"market": u["market"], "account": u.get("account") or u["market"].partition(":")[2],
                        "sid": str(u["product_id"]).strip()})
    return out


def _uploader(account: str):
    from src.seller_console.market_cred_view import coupang_account
    from src.channel_sync.coupang_uploader import make_uploader
    with coupang_account(account):
        return make_uploader()[0]


def target(item: dict, up, seller_id: str = "") -> Dict:
    """`{ready, contents, hash, translated, failed, why}` — 지금 등록하면 나갈 상세(등록과 같은 빌더)."""
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    from src.channel_sync.coupang_uploader import prepared_input
    from src.channel_sync._channel_bridge import to_collected
    pd = build_dispatch_payload(build_product(item, edits={}, seller_id=seller_id), item)
    failed = int(pd.get("detail_translate_failed") or 0)
    prepared = up.prepare_product(to_collected(prepared_input(pd)))
    contents = up._build_contents(prepared)
    return {"ready": failed == 0, "contents": contents, "hash": _hash(contents),
            "translated": int(pd.get("detail_auto_translated") or 0), "failed": failed,
            "why": str(pd.get("detail_translate_why") or "")}


def _queue_put(entry: dict) -> None:
    from src.db import image_translate_queue_pg as st
    cur = st.state_get(QUEUE_KEY) or {}
    rows = [r for r in (cur.get("rows") or []) if not (r.get("item_id") == entry["item_id"] and r.get("market") == entry["market"])]
    st.state_set(QUEUE_KEY, {"rows": rows + [entry]})


def _queue_drop(item_id: str, market: str) -> None:
    from src.db import image_translate_queue_pg as st
    cur = st.state_get(QUEUE_KEY) or {}
    st.state_set(QUEUE_KEY, {"rows": [r for r in (cur.get("rows") or [])
                                      if not (r.get("item_id") == item_id and r.get("market") == market)]})


def queue_rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return list((st.state_get(QUEUE_KEY) or {}).get("rows") or [])


def refresh_item(item: dict, *, seller_id: str = "", markets: Optional[List[str]] = None,
                 make_up: Optional[Callable[[str], object]] = None, save: Optional[Callable[[dict], None]] = None) -> List[dict]:
    """이 상품의 쿠팡 등록본마다 상세 갱신 시도 — 줄마다 `{market, sid, sent, ok, state, error, market_status, body}`.
    결과는 `extra.coupang_detail_sync[market]`에 남기고(`save(extra)`), 못 보냈으면 큐에 넣는다."""
    make_up = make_up or _uploader
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    item_id = str(item.get("id") or "")
    sync = ex.get("coupang_detail_sync") if isinstance(ex.get("coupang_detail_sync"), dict) else {}
    out: List[dict] = []
    for u in coupang_uploads(ex):
        if markets and u["market"] not in markets:
            continue
        row = {"market": u["market"], "sid": u["sid"], "sent": False, "ok": False, "state": "", "error": "",
               "market_status": None, "body": "", "at": _now()}
        try:
            up = make_up(u["account"])
            tg = target(item, up, seller_id)
            if (sync.get(u["market"]) or {}).get("hash") == tg["hash"] and (sync.get(u["market"]) or {}).get("ok"):
                row.update(ok=True, state="same", error="이미 같은 상세를 보냈어요")
                out.append(row)
                continue
            if not tg["ready"]:
                row.update(state="translate_wait", error=f"상세 번역 실패 {tg['failed']}칸({tg['why']}) — 번역되면 보내요")
                _queue_put({"item_id": item_id, "market": u["market"], "sid": u["sid"], "account": u["account"],
                            "seller_id": seller_id, "reason": "번역 대기", "raw": row["error"], "at": _now(),
                            "tries": int((sync.get(u["market"]) or {}).get("tries") or 0)})
                out.append(row)
                continue
            live = up.get_product(u["sid"])
            if "error" in live:
                row.update(error=f"쿠팡 상품 조회 실패 — {live['error']}")
            else:
                raw_state = str(live.get("statusName") or live.get("status") or "")
                row["state"] = raw_state
                body = json.loads(json.dumps(live))
                for it in body.get("items") or []:
                    it["contents"] = tg["contents"]
                body["requested"] = True
                res = up.modify_product(body)
                row["sent"] = True
                row.update(ok=bool(res.get("success")), error=str(res.get("error") or "")[:500],
                           market_status=res.get("market_status"), body=str(res.get("body") or "")[:2000])
            if row["ok"]:
                _queue_drop(item_id, u["market"])
            else:
                tries = int((sync.get(u["market"]) or {}).get("tries") or 0) + 1
                row["tries"] = tries
                _queue_put({"item_id": item_id, "market": u["market"], "sid": u["sid"], "account": u["account"],
                            "seller_id": seller_id, "reason": "승인 후 자동 갱신" if row["state"] else "조회 실패",
                            "raw": (row["error"] + " " + row["body"])[:1500], "market_status": row["market_status"],
                            "state": row["state"], "at": _now(), "tries": tries})
            sync[u["market"]] = {"hash": tg["hash"], "ok": row["ok"], "at": row["at"], "state": row["state"],
                                 "error": row["error"][:300], "market_status": row["market_status"],
                                 "lines": tg["translated"], "tries": row.get("tries", 0)}
        except Exception as exc:                                  # noqa: BLE001 — 한 마켓 실패가 다른 마켓을 막지 않는다
            row["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.warning("[쿠팡 상세 갱신] %s %s 실패: %s", item_id[:8], u["market"], row["error"])
        logger.info("[쿠팡 상세 갱신] item=%s %s sid=%s sent=%s ok=%s state=%s err=%s", item_id[:8], u["market"], u["sid"],
                    row["sent"], row["ok"], row["state"], row["error"][:200])
        out.append(row)
    ex["coupang_detail_sync"] = sync
    if save and out:
        save(ex)
    return out


def drain(get_item: Callable[[str, str], Optional[dict]], save_for: Callable[[str, str], Callable[[dict], None]],
          make_up: Optional[Callable[[str], object]] = None, budget: int = 10) -> Dict:
    """큐를 비운다 — 번역 대기는 다시 만들어 보고, 승인 대기는 상태를 물어 승인됐으면 보낸다. `{picked, sent, ok, left, rows}`."""
    make_up = make_up or _uploader
    rows = queue_rows()
    out = {"picked": 0, "sent": 0, "ok": 0, "left": len(rows), "rows": []}
    for q in rows[:budget]:
        out["picked"] += 1
        item = get_item(q["item_id"], q.get("seller_id") or "")
        if not item:
            _queue_drop(q["item_id"], q["market"])
            continue
        if int(q.get("tries") or 0) >= MAX_TRIES:
            _queue_drop(q["item_id"], q["market"])
            out["rows"].append({**q, "dropped": "시도 상한"})
            continue
        if q.get("reason") != "번역 대기":
            st = make_up(q["account"]).review_status(q["sid"])
            if st.get("state") not in ("approved", "saved", "rejected"):
                out["rows"].append({**q, "waiting": st.get("state") or "unknown"})
                continue                                          # 아직 검토 중 — 다음 회전에
        res = refresh_item(item, seller_id=q.get("seller_id") or "", markets=[q["market"]], make_up=make_up,
                           save=save_for(q["item_id"], q.get("seller_id") or ""))
        for r in res:
            out["sent"] += int(bool(r.get("sent")))
            out["ok"] += int(bool(r.get("ok")))
            out["rows"].append(r)
    out["left"] = len(queue_rows())
    return out
