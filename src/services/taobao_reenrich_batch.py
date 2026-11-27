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


_RUNNER_OVERRIDE: dict = {}                    # 시험만 — 줄에는 함수를 저장할 수 없다


def start(rows: List[Dict], by: str, *, runner=None, by_uid: str = "") -> Dict:
    """`rows=[{item_id, seller_id, title}]` — 오너 11-27 ②④: 서버 줄(`durable_job`)에서 돈다. 이미 돌면 시작하지 않고,
    재시작에 끊긴 실행(하트비트 멈춤·예전 스레드 기록)이면 처음부터가 아니라 끝낸 데서 잇는다."""
    from src.services import durable_job as DJ
    cur = DJ.status(KEY)
    if cur.get("state") == "running":
        if cur.get("stalled") or not cur.get("kind"):
            cur["kind"] = "taobao_reenrich"
            DJ.save(KEY, cur)
            r = DJ.resume(KEY)
            return {"ok": True, "resumed": True, "total": cur.get("total"), "started": r.get("started")}
        return {"ok": False, "error": f"이미 도는 중이에요({len(cur.get('done') or [])}/{cur.get('total')})."}
    if runner is not None:
        _RUNNER_OVERRIDE["run"] = runner
    else:
        _RUNNER_OVERRIDE.pop("run", None)
    rec = {"total": len(rows), "by": str(by or "")[:200], "stop": False,
           "rows": [{"item_id": r["item_id"], "seller_id": r["seller_id"], "title": str(r.get("title") or "")[:60]} for r in rows],
           "done": []}
    r = DJ.begin(KEY, "taobao_reenrich", rec, by_uid=by_uid)
    if not r["started"]:
        return {"ok": True, "total": rec["total"], "queued": True,
                "note": "서버 메모리 여유가 없어 바로 못 시작했어요 — 줄에 세워 뒀고 10분 안에 저절로 시작해요."}
    return {"ok": True, "total": rec["total"]}


def stop() -> bool:
    rec = status()
    if rec.get("state") != "running":
        return False
    rec["stop"] = True
    _save(rec)
    return True


def _step(key: str, rec: Dict, deadline: float, *, runner=None) -> Dict:
    """한 걸음 — 끝낸 행은 건너뛰고(재시작 뒤 이어서) 한 건씩 · 한 건마다 저장."""
    import time as _time
    from src.services import taobao_auto as TA
    runner = runner or _RUNNER_OVERRIDE.get("run") or (lambda uid, iid: TA.run(uid, iid, src="reenrich"))
    rows = rec.get("rows") or []
    while _time.time() < deadline:
        cur = status()
        if cur.get("stop") or len(cur.get("done") or []) >= len(rows):
            cur["state"] = "stopped" if cur.get("stop") and len(cur.get("done") or []) < len(rows) else "finished"
            cur["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cur["ok_count"] = sum(1 for d in cur.get("done") or [] if d.get("ok"))
            cur["push"] = {"title": f"타오바오 재보강 {'멈춤' if cur['state'] == 'stopped' else '완료'} — 성공 {cur['ok_count']}/{cur.get('total')}",
                           "body": "실패한 건은 사유와 함께 남겼어요.", "path": "/seller/admin/taobao-reenrich"}
            _save(cur)
            logger.info("[타오바오 재보강 묶음] %d/%d 성공", cur["ok_count"], cur.get("total"))
            return cur
        r = rows[len(cur.get("done") or [])]
        try:
            out = runner(r["seller_id"], r["item_id"]) or {}
        except Exception as exc:                                  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            out = {"state": "error", "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}
        cur = status()                                            # 그 사이 눌린 「멈춤」을 덮지 않게 다시 읽고 덧붙인다
        cur.setdefault("done", []).append({"item_id": r["item_id"], "title": r.get("title", ""), "state": str(out.get("state") or ""),
                                           "ok": out.get("state") == "done", "reason": str(out.get("reason") or "")[:200]})
        cur["progress"] = {"n": len(cur["done"]), "total": len(rows), "label": f"도는 중 {len(cur['done'])}/{len(rows)}"}
        cur["heartbeat_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _save(cur)
        rec = cur
    return rec


def _run(runner=None) -> Dict:
    """한 번에 끝까지(시험용) — 운영은 durable_job 걸음."""
    import time as _time
    rec = status()
    while rec.get("state") == "running":
        rec = _step(KEY, rec, _time.time() + 3600, runner=runner)
    return {"ok": True, "ok_count": rec.get("ok_count"), "total": rec.get("total")}


def _register():
    from src.services import durable_job as DJ
    DJ.register("taobao_reenrich", lambda key, rec, deadline: _step(key, rec, deadline))


_register()
