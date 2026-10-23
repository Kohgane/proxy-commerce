"""Y15(오너 2026-10-21 「틱 멈춤 재발 방지」) — 운영 10분 틱이 마지막으로 돈 시각과 리스 나이.

10-21 10:20~12:43 UTC 틱이 2시간 반 안 돌았다. 그동안 남은 신호는 **틱 기록이 비었다**는 것 하나(Render 메일은 12:43에야).
인스턴스가 왜 응답을 못 했는지는 Render 로그 없이 가릴 수 없어 「미확인」 — 여기선 원인을 추정하지 않고 **나이만** 보인다.

- 마지막 틱 = `workers:runs`의 `translate-pilot-tick.last_at`(서비스 중 가장 늦은 것)과 `worker_lease:translate-pilot-tick`
  행의 `updated_at` 중 늦은 쪽. 틱은 시작에 리스를 잡고 끝에 놓으며, 끝에 실행 기록을 쓴다.
- 30분(`TICK_STALE_MIN`)을 넘으면 대시보드 손댈 것 「틱 멈춤 n분」.
- 기록을 한 번도 못 읽었으면(DB 없음·첫 배포) 멈춤이라 단정하지 않는다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TICK = "translate-pilot-tick"
_KST = timezone(timedelta(hours=9))


def stale_min() -> int:
    try:
        return max(1, int(os.getenv("TICK_STALE_MIN", "30")))
    except ValueError:
        return 30


def _parse(ts) -> Optional[datetime]:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(ts or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _lease_rows() -> List[Dict[str, Any]]:
    """`[{name, holder, updated_at}]` — `worker_lease:*` 행. DB가 없으면 빈 목록."""
    from src.db import pg
    if not pg.pg_enabled():
        return []
    out = []
    with pg.query() as cur:
        cur.execute("SELECT key, value, updated_at FROM app_state WHERE key LIKE 'worker_lease:%%'")
        for key, value, upd in cur.fetchall() or []:
            v = value if isinstance(value, dict) else {}
            out.append({"name": str(key).split(":", 1)[-1], "holder": str(v.get("holder") or ""), "updated_at": upd})
    return out


def _q_translate() -> int:
    from src.db import translation_jobs_pg as q
    return int((q.counts() or {}).get("pending") or 0)


def _q_imgko() -> int:
    from src.db import image_translate_queue_pg as q
    return int((q.counts() or {}).get("queued") or 0)


def _q_optko() -> int:
    from src.db import option_translate_queue_pg as q
    return int((q.counts() or {}).get("queued") or 0)


def _q_reject() -> int:
    from src.db import market_registrations_pg as q
    return len(q.watch_queue(account="", limit=500) or [])


#: 순찰 42(오너 2026-10-23) — 리스마다 「돌 게 몇 개 남았나」. 0이고 리스가 오래됐으면 **돌 게 없음**, 0보다 큰데 오래됐으면 **멈춤**.
#:   틱(translate-pilot-tick)은 번역 잡 대기(pending)만 센다 — 틱이 하는 다른 일(파일럿·갱신 큐)은 이 수에 없다.
_QUEUED = {TICK: "_q_translate", "imgko-auto": "_q_imgko", "optko-auto": "_q_optko", "reject-watch": "_q_reject"}


def queued_for(name: str) -> Optional[int]:
    """이 리스가 처리할 대기 수. 모르는 리스·읽기 실패 = None(0이라 단정하지 않는다)."""
    fn = globals().get(_QUEUED.get(str(name or ""), ""))
    if not fn:
        return None
    try:
        return fn()
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[틱 감시] %s 대기 수 못 읽음: %s", name, exc)
        return None


def _runs_last(runs: dict, name: str = TICK) -> Optional[datetime]:
    ats = [_parse((svc or {}).get(name, {}).get("last_at")) for svc in (runs or {}).values() if isinstance(svc, dict)]
    ats = [a for a in ats if a]
    return max(ats) if ats else None


def status(now: Optional[datetime] = None, *, leases: Optional[List[Dict]] = None, runs: Optional[dict] = None) -> Dict[str, Any]:
    """`{seen, last_at, age_min, stale, line, todo, leases:[{name, holder, age_min}]}`."""
    now = now or datetime.now(timezone.utc)
    try:
        if leases is None:
            leases = _lease_rows()
        if runs is None:
            from src.services.workers import _RUNS_KEY, _state
            runs = _state().state_get(_RUNS_KEY) or {}
    except Exception as exc:                                     # noqa: BLE001 — 못 읽으면 단정하지 않는다
        logger.debug("[틱 감시] 기록 읽기 실패: %s", exc)
        return {"seen": False, "line": "", "todo": "", "stale": False, "leases": [], "error": type(exc).__name__}
    ages = []
    for r in leases or []:
        u = _parse(r.get("updated_at"))
        ages.append({"name": r.get("name"), "holder": r.get("holder") or "",
                     "age_min": int((now - u).total_seconds() // 60) if u else None})
    ages.sort(key=lambda a: (a["age_min"] is None, a["age_min"] or 0))
    cands = [_runs_last(runs)] + [_parse(r.get("updated_at")) for r in leases or [] if r.get("name") == TICK]
    cands = [c for c in cands if c]
    if not cands:
        return {"seen": False, "line": "", "todo": "", "stale": False, "leases": ages}
    last = max(cands)
    age = int((now - last).total_seconds() // 60)
    stale = age > stale_min()
    hhmm = last.astimezone(_KST).strftime("%H:%M")
    return {"seen": True, "last_at": last.isoformat(), "age_min": age, "stale": stale, "leases": ages,
            "line": f"마지막 틱 {hhmm}" + (f" · {age}분 전" if stale else ""),
            "todo": f"틱 멈춤 {age}분 — 마지막 틱 {hhmm}(KST) · 원인 미확인 → Render 메일·/health/deep 먼저" if stale else ""}
