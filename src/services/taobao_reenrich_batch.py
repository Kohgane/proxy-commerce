"""오너 11-26 진단 4 — 타오바오 재보강 「N건 다시 가져오기」(오너 탭으로만).

관리자 화면에서 두 번 눌러 확인하면 한 건씩 차례로 `taobao_auto.run`(지금 켜진 경로 — 온바운드/mtop)을 돌린다.
진행·결과는 `app_state taobao_reenrich:batch`에 — 화면이 n/N과 성공·실패 사유 표를 그린다. 마켓 전송 0(우리 수집 행만 채움).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

KEY = "taobao_reenrich:batch"
ONEBOUND_YUAN_PER_CALL = 0.023        # taobao_provider_onebound 독스트링의 단가(응답 api_info로 확인한 값)


def status() -> Dict:
    from src.db import image_translate_queue_pg as st
    return dict(st.state_get(KEY) or {})


def _save(rec: Dict) -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(KEY, rec)


def estimate(n: int, route: str) -> Dict:
    """예상 비용 — 온바운드는 건당 단가 × n(자료가 24시간 넘게 묵었으면 1회 더 부를 수 있어 최대 ×2), mtop은 과금 없음."""
    if route == "onebound":
        lo, hi = round(n * ONEBOUND_YUAN_PER_CALL, 3), round(n * ONEBOUND_YUAN_PER_CALL * 2, 3)
        return {"route": route, "yuan_min": lo, "yuan_max": hi,
                "line": f"온바운드 {n}회 × {ONEBOUND_YUAN_PER_CALL}元 = 약 {lo}元(오래된 자료면 최대 {hi}元) · 일일 한도 안에서만"}
    return {"route": route, "yuan_min": 0, "yuan_max": 0, "line": f"{route or '경로 없음'} — 호출 과금 없음(막히면 그 건만 실패로 남아요)"}


def start(rows: List[Dict], by: str, *, runner=None) -> Dict:
    """`rows=[{item_id, seller_id, title}]` — 이미 돌고 있으면 시작하지 않는다."""
    cur = status()
    if cur.get("state") == "running":
        return {"ok": False, "error": f"이미 도는 중이에요({len(cur.get('done') or [])}/{cur.get('total')})."}
    rec = {"state": "running", "total": len(rows), "by": str(by or "")[:200],
           "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "rows": [{"item_id": r["item_id"], "seller_id": r["seller_id"], "title": str(r.get("title") or "")[:60]} for r in rows],
           "done": []}
    _save(rec)
    from src.utils import bg_job
    started, _st = bg_job.start("taobao-reenrich-batch", lambda: _run(runner))
    if not started:
        rec["state"] = "refused"
        rec["error"] = "서버 메모리 여유가 없어 지금은 못 돌려요 — 잠시 뒤 다시 눌러 주세요." if _st.get("busy_memory") else "다른 잡이 도는 중이에요."
        _save(rec)
        return {"ok": False, "error": rec["error"]}
    return {"ok": True, "total": rec["total"]}


def _run(runner=None) -> Dict:
    from src.services import taobao_auto as TA
    runner = runner or (lambda uid, iid: TA.run(uid, iid, src="reenrich"))
    rec = status()
    for r in rec.get("rows") or []:
        try:
            out = runner(r["seller_id"], r["item_id"]) or {}
        except Exception as exc:                                  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            out = {"state": "error", "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}
        rec.setdefault("done", []).append({"item_id": r["item_id"], "title": r.get("title", ""), "state": str(out.get("state") or ""),
                                           "ok": out.get("state") == "done", "reason": str(out.get("reason") or "")[:200]})
        _save(rec)
    rec["state"] = "finished"
    rec["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec["ok_count"] = sum(1 for d in rec["done"] if d["ok"])
    _save(rec)
    logger.info("[타오바오 재보강 묶음] %d/%d 성공", rec["ok_count"], rec["total"])
    return {"ok": True, "ok_count": rec["ok_count"], "total": rec["total"]}
