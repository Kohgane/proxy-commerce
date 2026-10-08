"""Z8(오너 2026-10-08 23:3x 워커 교착) — 네트워크를 쥔 채 잡는 잠금은 **기다림에 상한**을 둔다.

`with lock:`은 앞 스레드가 외부 호출에서 묶이면 뒤 스레드를 끝없이 세운다(gthread 4개가 전부 그 줄에 서면
워커가 통째로 멈춘다). `try_lock(lock, timeout=5, code=…)`는 5초 안에 못 잡으면 **사유코드를 로그에 남기고**
`False`를 내준다 — 호출부가 「그 판정은 건너뜀」으로 통과시킨다(막지 않는다).
"""
from __future__ import annotations

import contextlib
import logging
import os

logger = logging.getLogger(__name__)


def wait_sec() -> float:
    try:
        return max(0.1, float(os.getenv("LOCK_WAIT_SEC", "5") or 5))
    except ValueError:
        return 5.0


@contextlib.contextmanager
def try_lock(lock, *, code: str, what: str = "", timeout=None):
    """잡았으면 True, 상한 안에 못 잡았으면 False(사유코드 로그) — 잡은 경우에만 풀어 준다."""
    t = wait_sec() if timeout is None else float(timeout)
    got = lock.acquire(timeout=t)
    if not got:
        logger.warning("[LOCK] %s — %s %.1fs 안에 잠금을 못 잡아 건너뜀", code, what or "잠금", t)
    try:
        yield got
    finally:
        if got:
            lock.release()
