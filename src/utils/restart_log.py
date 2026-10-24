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

_LAST_REQ = {"at": time.monotonic(), "quiet_noted": False}
_BOOT_AT = {"at": time.monotonic()}


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


def note_boot(pid: int, mb: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    """새 워커가 떴다 — 직전 `exit`과 짝지어 재시작 시간(초)을 적는다. 적은 줄을 돌려준다(테스트용)."""
    now = now or datetime.now(timezone.utc)
    _BOOT_AT["at"] = time.monotonic()
    _LAST_REQ.update(at=time.monotonic(), quiet_noted=False)
    prev = None
    try:
        prev = next((r for r in reversed(rows()) if r.get("kind") in ("exit", "boot")), None)
    except Exception:                                            # noqa: BLE001
        pass
    row: Dict[str, Any] = {"pid": pid, "mb": mb}
    t = _parse(prev.get("at")) if prev else None
    if prev and prev.get("kind") == "exit" and t and (now - t).total_seconds() <= EXIT_MATCH_SEC:
        row.update(after_exit_sec=round((now - t).total_seconds(), 1), reason=prev.get("reason"), prev_pid=prev.get("pid"))
    else:
        row.update(outside=True, reason="우리 상한 기록 없음 — 배포·Render 재시작·강제 종료")
    append("boot", **row)
    return row


def touch_request() -> None:
    """요청 하나가 끝났다(after_request) — 값만 바꾼다(DB 없음)."""
    _LAST_REQ["at"] = time.monotonic()
    _LAST_REQ["quiet_noted"] = False


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


def check_quiet(now_mono: Optional[float] = None) -> Optional[dict]:
    """요청이 `quiet_min()`분 넘게 안 끝났으면 한 번 적는다(공백 하나에 한 줄). 적은 줄 또는 None."""
    now_mono = time.monotonic() if now_mono is None else now_mono
    idle = now_mono - _LAST_REQ["at"]
    if idle < quiet_min() * 60 or _LAST_REQ["quiet_noted"]:
        return None
    _LAST_REQ["quiet_noted"] = True
    active = []
    try:
        from src.utils import stall_guard as _sg
        with _sg._LOCK:
            active = [{"path": v.get("path"), "sec": round(now_mono - float(v.get("start") or now_mono))}
                      for v in _sg._ACTIVE.values()][:10]
    except Exception:                                            # noqa: BLE001
        pass
    row = {"idle_min": round(idle / 60, 1), "active": active, "threads": _threads_line(), "pid": os.getpid()}
    append("quiet", **row)
    logger.warning("[요청 없음] %.1f분 동안 끝난 요청 0 — 처리 중 %d건 · 스레드 %d", idle / 60, len(active), len(row["threads"]))
    return row
