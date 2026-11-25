"""오너 11-25 15:56 ③ — 쿠팡 **승인 결과 지켜보기**(읽기만). 반려되면 그 상품 카드로 가는 푸시를 한 번 보낸다.

쿠팡 반려는 등록 응답이 아니라 **나중에**(검토 뒤) 온다. 예전엔 「마켓 상태」 팝업을 열어야만 알았다 — 폰엔 길이 없었다.
그래서 쿠팡 등록이 성공하면 그 번호를 작은 줄(`app_state coupang_review_watch:rows`)에 세우고, 10분 틱이 최대 10건씩
**검토 상태만 묻는다**(`review_status` — 상품 조회 · 마켓에 쓰는 일 0). 승인·반려가 나오면 줄에서 빠지고, 반려면
`coupang_detail_refresh.notify_rejected`(등록 기록에 반려·사유를 적고 푸시 1번)를 부른다. 7일 넘게 검토 중이면 놓아 준다.

DB를 훑지 않는다(목록 스캔 0) — 등록한 그 순간에 줄을 세우는 것으로 충분하다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

KEY = "coupang_review_watch:rows"
MAX_ROWS = 400
MAX_AGE = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return list((st.state_get(KEY) or {}).get("rows") or [])


def _save(rs: List[dict]) -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(KEY, {"rows": rs[-MAX_ROWS:]})


def add(item_id: str, market: str, sid: str, seller_id: str = "") -> bool:
    """쿠팡 등록 성공 1건을 지켜보기 줄에 세운다(같은 상품·마켓·번호면 그대로). 실패해도 등록을 막지 않는다."""
    if not (item_id and str(market).startswith("coupang") and str(sid).strip()):
        return False
    try:
        rs = [r for r in rows() if not (r.get("item_id") == item_id and r.get("market") == market and r.get("sid") == str(sid))]
        rs.append({"item_id": str(item_id), "market": str(market), "sid": str(sid), "account": str(market).partition(":")[2],
                   "seller_id": str(seller_id or ""), "at": _now().isoformat(), "checks": 0})
        _save(rs)
        return True
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("[쿠팡 승인 지켜보기] 줄 세우기 실패: %s", exc)
        return False


def tick(make_up: Optional[Callable[[str], object]] = None, budget: int = 10) -> Dict:
    """줄 앞에서부터 최대 `budget`건 검토 상태만 묻는다 — `{checked, rejected, approved, left}`."""
    from src.services import coupang_detail_refresh as cdr
    make_up = make_up or cdr._uploader
    rs = rows()
    out = {"checked": 0, "rejected": 0, "approved": 0, "left": len(rs)}
    if not rs:
        return out
    keep, now = [], _now()
    for i, r in enumerate(rs):
        if out["checked"] >= budget:
            keep.extend(rs[i:])
            break
        try:
            at = datetime.fromisoformat(str(r.get("at") or ""))
        except ValueError:
            at = now
        if now - at > MAX_AGE:
            continue                                                # 7일 넘게 검토 중 — 놓아 준다(팝업에서 직접 확인)
        out["checked"] += 1
        try:
            from src.seller_console.market_credentials import job_market_env
            with job_market_env(r.get("seller_id") or ""):
                st = make_up(r.get("account") or "").review_status(r["sid"])
        except Exception as exc:                                    # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            logger.warning("[쿠팡 승인 지켜보기] %s 조회 실패: %s", r.get("sid"), exc)
            keep.append({**r, "checks": int(r.get("checks") or 0) + 1})
            continue
        state = str(st.get("state") or "")
        if state == "rejected":
            cdr.notify_rejected(r, st)
            out["rejected"] += 1
            continue
        if state in ("approved", "deleted"):
            out["approved"] += int(state == "approved")
            continue
        keep.append({**r, "checks": int(r.get("checks") or 0) + 1})
    _save(keep)
    out["left"] = len(keep)
    if out["checked"]:
        logger.info("[쿠팡 승인 지켜보기] %s", out)
    return out
