"""src/utils/shutdown.py — Y15 P0-운영(오너 2026-10-23 Render 로그): 내려갈 때 **반드시 내려간다**.

10-23 09:10 UTC 인스턴스 vssjj: gunicorn이 「Handling signal: term → Worker exiting → Shutting down: Master」를 찍고도 프로세스가
안 끝났다(09:33에도 같은 인스턴스의 틱 감시 스레드가 텔레그램을 찍음). 포트는 닫혔는데 인스턴스는 살아 있어 Render가 그리로 트래픽을
보냈고 틱이 50분 유실됐다. 로컬 재현: 마스터 안에서 스레드 풀(`concurrent.futures`) 일이 돌고 있으면 `sys.exit` 뒤 인터프리터 종료가
그 일을 **끝까지 기다린다**(풀 스레드는 데몬이 아니다 — 맡긴 쪽 스레드가 데몬이어도).

- `STOP` — 우리 백그라운드 루프는 `sleep` 대신 `wait(sec)`로 쉰다(세팅되면 바로 깬다).
- `register(thread)` · `stop_all(join_sec)` — 멈춤 신호 + 등록 스레드 합계 `join_sec` 안에 join.
- `arm_hard_exit(sec)` — 그 뒤에도 종료가 멈춰 있으면 `os._exit`. 데몬 스레드는 인터프리터 종료 단계(atexit·스레드 join)에도 돈다.
gunicorn 훅(`gunicorn.conf.py` `on_exit`·`worker_exit`)이 부른다.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import List

logger = logging.getLogger(__name__)

STOP = threading.Event()
_THREADS: List[threading.Thread] = []
_LOCK = threading.Lock()
_ARMED = {"t": None}


def wait(sec: float) -> bool:
    """`sec`초 쉰다 — 멈춤 신호면 바로 True(루프는 빠져나간다)."""
    return STOP.wait(max(0.0, float(sec)))


def stopping() -> bool:
    return STOP.is_set()


def register(t: threading.Thread) -> threading.Thread:
    with _LOCK:
        _THREADS[:] = [x for x in _THREADS if x.is_alive()] + [t]
    return t


def stop_all(join_sec: float = 3.0) -> int:
    """멈춤 신호를 세우고 등록 스레드를 합계 `join_sec` 안에 join — 남은(안 멈춘) 스레드 수."""
    STOP.set()
    deadline = time.monotonic() + max(0.0, float(join_sec))
    with _LOCK:
        threads = list(_THREADS)
    for t in threads:
        if t is threading.current_thread():
            continue
        t.join(max(0.0, deadline - time.monotonic()))
    left = [t.name for t in threads if t.is_alive() and t is not threading.current_thread()]
    if left:
        logger.warning("[종료] %d개 스레드가 %.1f초 안에 안 멈춤: %s", len(left), join_sec, ", ".join(left[:8]))
    return len(left)


def arm_hard_exit(sec: float = 2.0, code: int = 0) -> bool:
    """`sec`초 뒤에도 이 프로세스가 살아 있으면 `os._exit(code)` — 종료 단계에서 무엇이 붙잡든. 한 번만 건다."""
    if _ARMED["t"] is not None:
        return False

    def _kill():
        time.sleep(max(0.0, float(sec)))
        try:
            logger.warning("[종료] %.1f초 뒤에도 프로세스가 안 끝남 — 강제 종료(pid %s)", sec, os.getpid())
        except Exception:                                        # noqa: BLE001
            pass
        os._exit(code)

    t = threading.Thread(target=_kill, name="hard-exit", daemon=True)
    _ARMED["t"] = t
    t.start()
    return True


def start_daemon(target, name: str, *args, **kwargs) -> threading.Thread:
    """우리 상시 루프 스레드 — 데몬 + 등록(멈춤 신호 때 join 대상)."""
    t = threading.Thread(target=target, args=args, kwargs=kwargs, name=name, daemon=True)
    register(t)
    t.start()
    return t
