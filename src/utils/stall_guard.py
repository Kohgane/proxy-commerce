"""Z8(오너 2026-10-08 23:3x KST) — 오래 걸리는 요청의 **스택을 로그에** 남긴다.

실측: GET / 3회 중 2회 60초 무응답·1회 0.9초 — 워커 2개 중 1개의 gthread 4개가 전부 묶였다.
그때 어디서 멈췄는지 알 길이 없었다(Render 로그엔 접속 기록만). 다음엔 좌표가 바로 나오게:

- 요청이 시작되면 (스레드 번호, 시작 시각, 경로)를 적어 두고, 끝나면 지운다.
- 감시 스레드가 5초마다 보고 **30초를 넘긴 요청**이 있으면 그 스레드의 스택을 한 번 덤프한다
  (`[STALL] path=… elapsed=…s thread=…` + 스택). 90초를 넘기면 한 번 더 — 같은 자리면 묶인 것, 다르면 느린 것.
- 덤프에는 그 순간 처리 중인 다른 요청 목록(경로·경과)도 한 줄로 싣는다(워커 하나가 통째 묶였는지).

`STALL_DUMP_SEC`(기본 30)로 조정, 0이면 끈다. 프로세스(워커)마다 감시 스레드 하나 — 포크 뒤 첫 요청에서 띄운다.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_ACTIVE: Dict[int, dict] = {}          # thread id → {path, start, dumped:[sec…]}
_LOCK = threading.Lock()
_WATCH = {"pid": None, "thread": None}
_STOP = threading.Event()


def dump_after_sec() -> float:
    try:
        return float(os.getenv("STALL_DUMP_SEC", "30") or 30)
    except ValueError:
        return 30.0


def begin(path: str) -> None:
    tid = threading.get_ident()
    with _LOCK:
        _ACTIVE[tid] = {"path": str(path or "")[:200], "start": time.monotonic(), "dumped": []}
    _ensure_watcher()


def end() -> None:
    with _LOCK:
        _ACTIVE.pop(threading.get_ident(), None)


def active() -> List[dict]:
    now = time.monotonic()
    with _LOCK:
        return [{"thread": t, "path": r["path"], "elapsed": round(now - r["start"], 1)} for t, r in _ACTIVE.items()]


def _stack_of(tid: int) -> str:
    frame = sys._current_frames().get(tid)
    if frame is None:
        return "(스레드가 이미 끝남)"
    return "".join(traceback.format_stack(frame))


def check_once(now: Optional[float] = None) -> List[str]:
    """한 번 훑어 덤프할 것을 덤프 — 덤프한 로그 줄들을 돌려준다(테스트용)."""
    limit = dump_after_sec()
    if limit <= 0:
        return []
    now = time.monotonic() if now is None else now
    out = []
    with _LOCK:
        snap = {t: dict(r, dumped=list(r["dumped"])) for t, r in _ACTIVE.items()}
    for tid, r in snap.items():
        el = now - r["start"]
        for mark in (limit, limit * 3):
            if el >= mark and mark not in r["dumped"]:
                others = " · ".join(f"{o['path']} {o['elapsed']}s" for o in active() if o["thread"] != tid) or "없음"
                line = (f"[STALL] path={r['path']} elapsed={el:.1f}s thread={tid} "
                        f"(동시 처리 중: {others})\n{_stack_of(tid)}")
                logger.error(line)
                out.append(line)
                with _LOCK:
                    if tid in _ACTIVE:
                        _ACTIVE[tid]["dumped"].append(mark)
                break
    return out


def _loop() -> None:
    while not _STOP.wait(5.0):
        try:
            check_once()
        except Exception as exc:                              # noqa: BLE001 — 감시는 죽지 않는다
            logger.warning("[STALL] 감시 오류: %s", exc)


def _ensure_watcher() -> None:
    if dump_after_sec() <= 0:
        return
    pid = os.getpid()
    if _WATCH["pid"] == pid and _WATCH["thread"] is not None and _WATCH["thread"].is_alive():
        return
    with _LOCK:
        if _WATCH["pid"] == pid and _WATCH["thread"] is not None and _WATCH["thread"].is_alive():
            return
        t = threading.Thread(target=_loop, daemon=True, name="stall-guard")
        t.start()
        _WATCH.update(pid=pid, thread=t)


def install(app) -> None:
    """Flask 앱에 걸기: 요청 시작·끝 기록 + 요청 스레드 표시(`g._kgp_req_thread` — pg 요청 연결의 주인)."""

    @app.before_request
    def _stall_begin():
        try:
            from flask import g, request
            g._kgp_req_thread = threading.get_ident()
            begin(request.path)
        except Exception:
            pass

    @app.teardown_request
    def _stall_end(_exc=None):
        end()


def reset() -> None:
    """테스트용."""
    with _LOCK:
        _ACTIVE.clear()
