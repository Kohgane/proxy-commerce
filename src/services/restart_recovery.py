"""src/services/restart_recovery.py — P0-운영(오너 2026-10-23 「os._exit 강제 종료 뒤 남는 running 줄」).

강제 종료(`shutdown.arm_hard_exit`)·OOM으로 프로세스가 도중에 죽으면 두 가지가 「running」으로 남는다.
- 사전검증 잡 `prevalidate_job:<id>` — 화면 폴링이 마감 지나 닫아 주지만, 줄 서 있던 잡(`queued`)과 아무도 안 보는 잡(일회성 줄이 띄움)은
  영영 「running」.
- 일회성 작업 줄 — `drain`이 줄에서 먼저 빼므로 **조용히 사라진다**(`ops:oneshot:inflight:<인스턴스:pid>`에만 남음).

`sweep()`이 둘을 닫는다. **다른 인스턴스가 아직 돌리는 중일 수 있으니**(Render는 새 인스턴스를 띄운 뒤 옛 것을 내린다) 시간으로만 판정한다:
- 사전검증 잡: 시작 + 마감 + AI 연장 + 줄 대기 + 여유가 지났는데 「running」 → `done` · 남은 마켓 「검증 못 함 — 서버가 다시 시작돼 끊겼어요」.
  일회성 줄이 띄운 잡이고 그 줄이 다시 돌려도 되는 작업이면 한 번 다시 넣는다(`restarts` 1회 — 같은 일이 또 죽이면 멈춘다).
- 일회성 진행 기록: 마지막 갱신이 `ONESHOT_INFLIGHT_STALE_SEC`(20분) 넘게 지났으면 — 시작 못 한 줄은 그대로 다시 넣고, 돌던 줄은
  읽기 작업(`REQUEUE_SAFE_OPS`)만 한 번 다시 넣는다. 등록·전송·결정 적용은 다시 넣지 않고 `ops:oneshot:interrupted`에 「중단됨」으로 남긴다.

부팅 부가 작업(`order_webhook._boot_chores`)이 부팅 때 한 번, 판정 창이 지난 뒤 한 번 더 부른다(멈춤 신호면 기다리지 않는다).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

INTERRUPTED_CAP = 50


def _env_sec(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def inflight_stale_sec() -> float:
    return _env_sec("ONESHOT_INFLIGHT_STALE_SEC", 1200.0)


def pv_window_sec() -> float:
    """사전검증 잡이 살아 있으면 반드시 끝났을 시간 — 마감 + AI 연장 + 줄 대기 + 여유 60초."""
    from src.seller_console import views as V
    return float(V._PV_JOB_DEADLINE_SEC) + float(V._PV_AI_EXTRA_SEC) + float(V._PV_QUEUE_WAIT_SEC) + 60.0


def _ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(str(iso)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _requeue(row: dict, why: str) -> bool:
    from src.services import oneshot_ops as O
    clean = {k: v for k, v in (row or {}).items() if not str(k).startswith("_") and k not in ("queued_at", "started_at")}
    return O.enqueue(dict(clean, reason=f"{why} · {str(row.get('reason') or '')}".strip(" ·")[:200]))


def _interrupted(row: dict, why: str, holder: str) -> None:
    from src.db import image_translate_queue_pg as st
    from src.services import oneshot_ops as O
    cur = (st.state_get(O.INTERRUPTED_KEY) or {}).get("rows") or []
    keep = {k: row.get(k) for k in ("op", "item_id", "markets", "reason") if row.get(k) is not None}
    st.state_set(O.INTERRUPTED_KEY, {"rows": (cur + [dict(keep, why=why, holder=holder, at=datetime.now(timezone.utc).isoformat())])
                                     [-INTERRUPTED_CAP:]})
    logger.warning("[재시작 회수] 중단됨 — %s item=%s (%s)", row.get("op"), str(row.get("item_id") or "")[:8], why)


def _sweep_oneshot(now: float, me: str) -> Dict:
    from src.db import image_translate_queue_pg as st
    from src.services import oneshot_ops as O
    out = {"records": 0, "requeued": 0, "interrupted": 0}
    for key, rec in st.state_scan(O.INFLIGHT_PREFIX):
        holder = str(rec.get("holder") or key[len(O.INFLIGHT_PREFIX):])
        if holder == me or now - _ts(rec.get("at")) < inflight_stale_sec():
            continue                                             # 지금 이 프로세스 것 · 아직 돌고 있을 수 있다
        out["records"] += 1
        for row in rec.get("rows") or []:
            state, restarts = row.get("_state"), int(row.get("restarts") or 0)
            if state == "pending":                               # 시작도 못 했다 — 그대로 다시
                out["requeued"] += _requeue(row, "재시작으로 시작 못 해 다시 넣음")
            elif state == "running" and row.get("op") in O.REQUEUE_SAFE_OPS and restarts < 1:
                out["requeued"] += _requeue(dict(row, restarts=restarts + 1), "재시작으로 끊겨 다시 넣음(1회)")
            elif state == "running":
                why = ("서버가 다시 시작돼 끊겼어요 — 등록·전송 작업이라 다시 넣지 않았어요" if row.get("op") not in O.REQUEUE_SAFE_OPS
                       else "서버가 다시 시작돼 또 끊겼어요 — 다시 넣지 않았어요")
                _interrupted(row, why, holder)
                out["interrupted"] += 1
        st.state_delete(key)
    return out


def _sweep_prevalidate(now: float, me: str) -> Dict:
    from src.db import image_translate_queue_pg as st
    from src.seller_console import views as V
    from src.services import oneshot_ops as O
    out = {"closed": 0, "requeued": 0}
    for key, cur in st.state_scan(V._PV_JOB_KEY, field="state", equals="running"):
        started = float(cur.get("started_ts") or 0) or _ts(cur.get("started_at"))
        if now - started < pv_window_sec() + float(cur.get("ai_extend") or 0):
            continue
        if str(cur.get("holder") or "") == me:
            why = f"검증 못 함 — {int(V._PV_JOB_DEADLINE_SEC)}초 안에 끝나지 않았어요"
        else:
            why = "검증 못 함 — 서버가 다시 시작돼 검증이 끊겼어요(다시 눌러 주세요)"
        res = dict(cur.get("results") or {})
        for m in cur.get("markets") or []:
            if m not in res:
                res[m] = V._pv_transport_fail(m, "interrupted", why)
        cur.update(state="done", queued=False, results=res, interrupted=True,
                   finished_at=datetime.now(timezone.utc).isoformat())
        st.state_set(key, cur)
        out["closed"] += 1
        origin = cur.get("oneshot") or {}
        if origin.get("op") in O.REQUEUE_SAFE_OPS and int(origin.get("restarts") or 0) < 1:
            out["requeued"] += _requeue(dict(origin, restarts=int(origin.get("restarts") or 0) + 1),
                                        "재시작으로 끊긴 사전검증 다시 넣음(1회)")
    return out


def sweep(now: Optional[float] = None) -> Dict:
    from src.utils.instance import holder
    now = time.time() if now is None else float(now)
    me = holder()
    out = {}
    for name, fn in (("oneshot", _sweep_oneshot), ("prevalidate", _sweep_prevalidate)):
        try:
            out[name] = fn(now, me)
        except Exception as exc:                                 # noqa: BLE001 — 회수 실패가 부팅을 막지 않는다
            logger.warning("[재시작 회수] %s 건너뜀(계속): %s", name, exc)
            out[name] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if any(v.get("records") or v.get("closed") for v in out.values()):
        logger.warning("[재시작 회수] %s", out)
    return out


def boot_sweep() -> None:
    """부팅 때 한 번 + 판정 창이 지난 뒤 한 번 더(옛 인스턴스가 내려간 뒤 남긴 줄까지). 멈춤 신호면 바로 끝."""
    from src.utils import shutdown as sd
    sweep()
    if sd.wait(max(inflight_stale_sec(), pv_window_sec()) + 30):
        return
    sweep()
