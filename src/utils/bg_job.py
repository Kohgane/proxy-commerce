"""Z8(오너 2026-10-08 워커 교착) — 크론 작업은 **요청 스레드를 1초 이상 붙잡지 않는다.**

`/cron/reprice`·`/cron/image-copies`(+ 같은 유형 `/cron/sourcing-monitor`·`/cron/supabase-backup`)는
예전엔 요청 안에서 재가격 엔진·이미지 복사(최대 45s)·소싱처 재확인(최대 200건)·백업을 돌렸다 — 외부 크론이
부를 때마다 gthread 하나가 수십 초 묶였다. 이제:

- 요청은 즉시 **202** `{ok, started, job}` — 일은 백그라운드 스레드(작업 이름당 동시 1개).
- 이미 도는 중이면 **409** 「진행 중」(얼마나 됐는지 같이).
- 끝나면 `[CRON] job=… elapsed_ms=… ok=…` 한 줄 — Render 로그로 소요를 본다. `GET /cron/jobs`가 마지막 결과를 준다.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_JOBS: Dict[str, dict] = {}       # 이름 → {state, started_at, started_ts, finished_at, elapsed_ms, result, error, thread}


def _run(name: str, fn: Callable[[], dict]) -> None:
    t0 = time.monotonic()
    ok, result, error = True, None, ""
    try:
        result = fn()
        if isinstance(result, dict) and result.get("ok") is False:
            ok = False
    except Exception as exc:                                   # noqa: BLE001 — 백그라운드는 죽지 않는다
        ok, error = False, f"{type(exc).__name__}: {str(exc)[:300]}"
        logger.error("[CRON] job=%s 예외: %s", name, error)
    ms = int((time.monotonic() - t0) * 1000)
    with _LOCK:
        _JOBS[name].update(state="done" if ok else "failed", finished_at=datetime.now(timezone.utc).isoformat(),
                           elapsed_ms=ms, result=result, error=error, thread=None)
    logger.info("[CRON] job=%s elapsed_ms=%d ok=%s", name, ms, ok)


def start(name: str, fn: Callable[[], dict]) -> Tuple[bool, dict]:
    """`(시작했나, 상태)` — 이미 도는 중이면 시작하지 않는다."""
    with _LOCK:
        cur = _JOBS.get(name) or {}
        t = cur.get("thread")
        if t is not None and t.is_alive():
            return False, view(name, locked=True)
        t = threading.Thread(target=_run, args=(name, fn), daemon=True, name=f"cron-{name}")
        _JOBS[name] = {"state": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                       "started_ts": time.time(), "finished_at": "", "elapsed_ms": None, "result": None,
                       "error": "", "thread": t}
    t.start()
    return True, view(name)


def view(name: str, *, locked: bool = False) -> dict:
    def _v():
        cur = dict(_JOBS.get(name) or {})
        cur.pop("thread", None)
        if cur.get("state") == "running":
            cur["running_sec"] = round(time.time() - float(cur.get("started_ts") or time.time()), 1)
        cur.pop("started_ts", None)
        return dict(cur, job=name)
    if locked:
        return _v()
    with _LOCK:
        return _v()


def all_views() -> Dict[str, dict]:
    with _LOCK:
        names = list(_JOBS)
    return {n: view(n) for n in names}


def join(name: str, timeout: float = 10.0) -> Optional[dict]:
    """테스트·진단용 — 끝날 때까지(최대 timeout) 기다리고 상태를 돌려준다."""
    with _LOCK:
        t = (_JOBS.get(name) or {}).get("thread")
    if t is not None:
        t.join(timeout)
    return view(name) if name in _JOBS else None


def reset() -> None:
    with _LOCK:
        _JOBS.clear()


def accepted(name: str, started: bool, state: dict):
    """크론 라우트 공통 응답 — 202(시작) 또는 409(진행 중)."""
    from flask import jsonify
    if started:
        return jsonify({"ok": True, "started": True, "job": name, "status_url": "/cron/jobs"}), 202
    return jsonify({"ok": False, "started": False, "job": name, "error": "진행 중",
                    "running_sec": state.get("running_sec")}), 409
