"""순찰 73(오너 2026-10-24) — 워커가 바뀐 까닭을 운영 DB에 남긴다(`rss:restart`, 최근 `KEEP`줄).

10-24 실측: 03:17 프로세스 교체 · 01:20~01:50 틱 29분 공백 — 재시작 사유(우리 RSS 상한 · Render 재시작 · 배포)와 걸린 시간을
Render 로그 없이는 가를 수 없었다. 세 가지를 적는다:

- `exit`  — `gunicorn.conf.post_request`가 이 워커를 내리기로 한 순간: 사유(워커 RSS / 인스턴스 합계) · 워커 MB · 합계 MB · 상한 · pid.
- `boot`  — 새 워커가 뜬 순간(`post_worker_init`): pid · MB · 직전 `exit`에서 몇 초(= 재시작에 걸린 시간).
            직전 `exit`이 없거나 오래됐으면 `outside=True` — 우리 상한이 아닌 재시작(배포 · Render 재시작 · 강제 종료).
- `quiet` — 프로세스는 살아 있는데 요청이 `QUIET_MIN`분 넘게 하나도 안 끝났다(틱 감시 스레드가 5분마다 본다):
            그 순간 처리 중인 요청(경로·경과)과 스레드 이름·맨 위 줄. 공백 하나에 한 줄.

기록 실패는 일을 막지 않는다.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KEY = "rss:restart"
KEEP = 60
#: 직전 `exit` 기록이 이 초보다 오래면 이번 부팅은 우리 상한 탓이 아니다(배포·Render 재시작·강제 종료)
EXIT_MATCH_SEC = 600

_LAST_REQ = {"at": time.monotonic(), "quiet_noted": False, "n": 0}
_BOOT_AT = {"at": time.monotonic(), "noted": False}     # noted = gunicorn 워커로 떴다(`note_boot`) — 503 판정은 그때만
#: 순찰 106-F: 이 프로세스에서 마지막 틱이 끝난 시각(monotonic, 0 = 부팅 뒤 아직) — `/health`가 DB 없이 본다
_LAST_TICK = {"at": 0.0}
#: 부팅 뒤 이 초 안에 요청이 하나도 안 끝났으면 `no_traffic` 한 줄(10-25 19:34 부팅 뒤 159분 무응답 — 밖에서 안 닿았다)
NO_TRAFFIC_SEC = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def quiet_min() -> int:
    try:
        return max(1, int(os.getenv("HTTP_QUIET_MIN", "10") or 10))
    except ValueError:
        return 10


def append(kind: str, **kw) -> None:
    row = {"at": _now(), "kind": kind, **kw}
    try:
        from src.db import image_translate_queue_pg as st
        st.state_update(KEY, lambda cur: dict(cur, rows=[r for r in cur.get("rows") or [] if isinstance(r, dict)][-(KEEP - 1):]
                                              + [row]))
    except Exception as exc:                                     # noqa: BLE001 — 기록 실패가 재시작·부팅을 막지 않는다
        logger.debug("[재시작 기록] %s 실패: %s", kind, exc)


def rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return [r for r in (st.state_get(KEY) or {}).get("rows") or [] if isinstance(r, dict)]


def _parse(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def note_exit(reason: str, *, pid: int, worker_mb: int, inst_mb: int = -1, worker_limit: int = 0, inst_limit: int = 0) -> None:
    append("exit", reason=str(reason)[:120], pid=pid, worker_mb=worker_mb, inst_mb=inst_mb,
           worker_limit=worker_limit, inst_limit=inst_limit, up_min=round((time.monotonic() - _BOOT_AT["at"]) / 60, 1))


def note_boot(pid: int, mb: int, now: Optional[datetime] = None, **cfg) -> Dict[str, Any]:
    """새 워커가 떴다 — 직전 `exit`과 짝지어 재시작 시간(초)을 적는다. 적은 줄을 돌려준다(테스트용)."""
    now = now or datetime.now(timezone.utc)
    _BOOT_AT.update(at=time.monotonic(), noted=True)
    _LAST_REQ.update(at=time.monotonic(), quiet_noted=False, n=0)
    _LAST_TICK["at"] = 0.0
    prev = None
    try:
        prev = next((r for r in reversed(rows()) if r.get("kind") in ("exit", "boot")), None)
    except Exception:                                            # noqa: BLE001
        pass
    row: Dict[str, Any] = {"pid": pid, "mb": mb, **cfg}           # 순찰 77: 실제로 뜬 gunicorn 값(스레드·timeout·워커 종류)
    t = _parse(prev.get("at")) if prev else None
    if prev and prev.get("kind") == "exit" and t and (now - t).total_seconds() <= EXIT_MATCH_SEC:
        row.update(after_exit_sec=round((now - t).total_seconds(), 1), reason=prev.get("reason"), prev_pid=prev.get("pid"))
    else:
        row.update(outside=True, reason="우리 상한 기록 없음 — 배포·Render 재시작·강제 종료")
    append("boot", **row)
    return row


def arm_no_traffic(delay: Optional[float] = None) -> None:
    """부팅 직후 한 번 — `delay`(기본 60초) 뒤 `check_no_traffic`(데몬 타이머 · 실패해도 부팅은 그대로)."""
    try:
        t = threading.Timer(NO_TRAFFIC_SEC if delay is None else delay, check_no_traffic)
        t.daemon = True
        t.name = "no-traffic-check"
        t.start()
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[재시작 기록] no_traffic 타이머 실패: %s", exc)


def check_no_traffic(now_mono: Optional[float] = None) -> Optional[dict]:
    """부팅 뒤 끝난 요청이 0이면 `no_traffic` 한 줄(적은 줄) — 헬스체크(/health)도 요청이라 0이면 밖에서 아예 안 닿은 것."""
    now_mono = time.monotonic() if now_mono is None else now_mono
    if int(_LAST_REQ.get("n") or 0) > 0:
        return None
    row = {"pid": os.getpid(), "since_boot_sec": round(now_mono - _BOOT_AT["at"], 1), "requests": 0}
    append("no_traffic", **row)
    logger.warning("[요청 없음] 부팅 %.0f초 동안 끝난 요청 0 — 헬스체크도 안 닿음(pid %s)", row["since_boot_sec"], row["pid"])
    return row


def touch_request() -> None:
    """요청 하나가 끝났다(after_request) — 값만 바꾼다(DB 없음)."""
    _LAST_REQ["at"] = time.monotonic()
    _LAST_REQ["quiet_noted"] = False
    _LAST_REQ["n"] = int(_LAST_REQ.get("n") or 0) + 1


def note_tick() -> None:
    """틱 하나가 끝났다 — 값만(DB 없음). `/health`의 틱 나이."""
    _LAST_TICK["at"] = time.monotonic()


def tick_stale_min() -> int:
    """`/health`가 503을 내는 틱 공백(분) — `HEALTH_TICK_STALE_MIN`(기본 20). 0이면 끈다(나이만 보인다)."""
    try:
        return max(0, int(os.getenv("HEALTH_TICK_STALE_MIN", "20") or 0))
    except ValueError:
        return 20


def health_snapshot(now_mono: Optional[float] = None) -> Dict[str, Any]:
    """`/health`에 싣는 값(DB 없음) — pid · 부팅 뒤 요청 수 · 마지막 틱(없으면 부팅 시각부터 잰 공백) · 503 여부.
    503(`stale`)은 gunicorn 워커로 뜬 프로세스만(개발 서버·테스트는 틱이 안 돈다 — 나이만 보인다)."""
    now_mono = time.monotonic() if now_mono is None else now_mono
    ticked = _LAST_TICK["at"] > 0
    base = _LAST_TICK["at"] if ticked else _BOOT_AT["at"]
    gap_min = round((now_mono - base) / 60, 1)
    lim = tick_stale_min()
    try:
        from src.utils.rss import under_gunicorn
        live = bool(_BOOT_AT.get("noted")) and under_gunicorn()
    except Exception:                                            # noqa: BLE001
        live = False
    last_at = None
    if ticked:
        last_at = datetime.fromtimestamp(time.time() - (now_mono - _LAST_TICK["at"]), timezone.utc).isoformat()
    return {"pid": os.getpid(), "requests": int(_LAST_REQ.get("n") or 0),
            "up_min": round((now_mono - _BOOT_AT["at"]) / 60, 1),
            "last_tick_at": last_at, "tick_gap_min": gap_min, "ticked_since_boot": ticked,
            "stale_after_min": lim, "stale": bool(lim and live and gap_min >= lim)}


def _threads_line() -> List[str]:
    import sys
    import traceback
    out = []
    frames = sys._current_frames()
    for t in threading.enumerate():
        f = frames.get(t.ident)
        top = ""
        if f is not None:
            st = traceback.extract_stack(f)
            if st:
                fr = st[-1]
                top = f"{os.path.basename(fr.filename)}:{fr.lineno} {fr.name}"
        out.append(f"{t.name}@{top}"[:120])
    return out[:30]


def request_threads() -> int:
    """gunicorn 요청 스레드 수 — `gunicorn.conf.py`와 같은 값(`GUNICORN_THREADS`, 기본 8)."""
    try:
        return max(1, int(os.getenv("GUNICORN_THREADS", "8") or 8))
    except ValueError:
        return 8


def _top_of(tid: int) -> str:
    import sys
    import traceback
    f = sys._current_frames().get(tid)
    if f is None:
        return ""
    st = traceback.extract_stack(f)
    if not st:
        return ""
    fr = st[-1]
    return f"{os.path.basename(fr.filename)}:{fr.lineno} {fr.name} — {(fr.line or '').strip()[:80]}"


def _self_exit(row: dict) -> None:
    """이 워커만 내린다(SIGTERM → gunicorn 정상 종료 → `worker_exit`의 강제 종료) — 마스터가 새 워커를 띄운다."""
    import signal
    os.kill(os.getpid(), signal.SIGTERM)


def check_quiet(now_mono: Optional[float] = None, *, exit_fn=None) -> Optional[dict]:
    """요청이 `quiet_min()`분 넘게 안 끝났으면 한 번 적는다(공백 하나에 한 줄). 적은 줄 또는 None.

    순찰 77: gthread 워커는 요청 스레드가 전부 묶여도 본 스레드가 마스터에 살아 있다고 알린다 — gunicorn `timeout`(120초)은
    **이 경우 워커를 죽이지 않는다**. 그래서 여기서 본다: 요청이 0건 끝났고 처리 중인 HTTP 요청이 요청 스레드 수 이상이면
    (= 스레드 풀이 통째로 묶임) `exit`(사유 「요청 스레드 전부 묶임」)를 적고 이 워커만 내린다. `QUIET_EXIT=0`이면 적기만."""
    now_mono = time.monotonic() if now_mono is None else now_mono
    idle = now_mono - _LAST_REQ["at"]
    if idle < quiet_min() * 60 or _LAST_REQ["quiet_noted"]:
        return None
    _LAST_REQ["quiet_noted"] = True
    active = []
    try:
        from src.utils import stall_guard as _sg
        with _sg._LOCK:
            snap = list(_sg._ACTIVE.items())
        active = [{"path": v.get("path"), "sec": round(now_mono - float(v.get("start") or now_mono)), "top": _top_of(tid)}
                  for tid, v in snap][:12]
    except Exception:                                            # noqa: BLE001
        pass
    http_busy = sum(1 for a in active if str(a.get("path") or "").startswith("/"))
    row = {"idle_min": round(idle / 60, 1), "active": active, "http_busy": http_busy, "threads_cfg": request_threads(),
           "threads": _threads_line(), "pid": os.getpid()}
    append("quiet", **row)
    logger.warning("[요청 없음] %.1f분 동안 끝난 요청 0 — 처리 중 HTTP %d건(스레드 %d) · 잡 %d건", idle / 60, http_busy,
                   request_threads(), len(active) - http_busy)
    if http_busy >= request_threads() and str(os.getenv("QUIET_EXIT", "1")).strip().lower() not in ("0", "false", "no", "off"):
        note_exit("요청 스레드 전부 묶임", pid=os.getpid(), worker_mb=_rss_mb(), worker_limit=0, inst_limit=0)
        row["exit"] = True
        (exit_fn or _self_exit)(row)
    return row


def _rss_mb() -> int:
    try:
        from src.utils import rss as _rss
        return int(_rss.read_mb()[0])
    except Exception:                                            # noqa: BLE001
        return -1
