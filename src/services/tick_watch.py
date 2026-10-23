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


# ── 순찰 43(오너 2026-10-23): 틱 공백 알림 — 틱 자체가 안 오니 서버 안 타이머로 본다 ─────────────────────────
#   10-23 04:00→06:30 UTC 150분 빈칸 = 커스텀 도메인 무응답(04:15~06:25, onrender 주소는 200) — cron이 커스텀 도메인을 쳐서
#   틱이 아예 들어오지 않았다. 코드가 아니라 길이 끊긴 것이라 /cron 안에선 알 수 없다 → 워커 스레드가 DB의 마지막 틱 나이를 본다.
#   인스턴스가 둘이어도 한 번만: 공백 하나(= 마지막 틱 시각)당 `tickgap:alert:<last_at>`을 원자적으로 하나만 잡는다.
GAP_ALERT_PREFIX = "tickgap:alert:"
_GAP_THREAD = {"t": None}


def gap_alert_min() -> int:
    try:
        return max(1, int(os.getenv("TICK_GAP_ALERT_MIN", "30")))
    except ValueError:
        return 30


def check_gap(now: Optional[datetime] = None, *, status_fn=None, take_fn=None, send_fn=None) -> Dict[str, Any]:
    """한 번 본다. `{alert, why, age_min}` — 기록이 없거나(첫 배포·DB 없음) 30분 안이면 알리지 않는다."""
    st = (status_fn or status)(now)
    age, last = st.get("age_min"), st.get("last_at")
    if not st.get("seen") or age is None or not last:
        return {"alert": False, "why": "틱 기록 없음 — 단정하지 않음", "age_min": age}
    if age < gap_alert_min():
        return {"alert": False, "why": "정상", "age_min": age}
    if take_fn is None:
        from src.db import image_translate_queue_pg as _st
        take_fn = _st.take_start
    took, _n = take_fn(GAP_ALERT_PREFIX + str(last), 1)
    if not took:
        return {"alert": False, "why": "이 공백은 이미 알림", "age_min": age}
    hhmm = _parse(last).astimezone(_KST).strftime("%H:%M") if _parse(last) else "?"
    msg = f"틱 {age}분 공백 — 도메인/cron 확인 (마지막 틱 {hhmm} KST)"
    if send_fn is None:
        from src.notifications.telegram import send_telegram as send_fn
    sent = bool(send_fn(msg, "warning"))
    logger.warning("[틱 감시] %s · 텔레그램 %s", msg, "보냄" if sent else "못 보냄(키 없음·실패)")
    return {"alert": True, "sent": sent, "message": msg, "age_min": age}


def start_gap_watch(interval_sec: Optional[int] = None) -> bool:
    """부팅 때 한 번 — 데몬 스레드가 `interval_sec`(기본 300초)마다 `check_gap`. `TICK_GAP_WATCH=0`이면 안 띄운다(테스트 기본)."""
    import threading
    import time as _time
    if str(os.getenv("TICK_GAP_WATCH", "1")).strip().lower() in ("0", "false", "no", "off"):
        return False
    t = _GAP_THREAD.get("t")
    if t is not None and t.is_alive():
        return False
    every = int(interval_sec or int(os.getenv("TICK_GAP_CHECK_SEC", "300") or 300))

    def _loop():
        while True:
            _time.sleep(every)
            try:
                check_gap()
            except Exception as exc:                             # noqa: BLE001 — 감시가 죽지 않는다
                logger.debug("[틱 감시] 공백 확인 실패: %s", exc)

    t = threading.Thread(target=_loop, name="tick-gap-watch", daemon=True)
    _GAP_THREAD["t"] = t
    t.start()
    return True
