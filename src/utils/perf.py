"""src/utils/perf.py — 요청 구간 타이밍(쿼리·렌더·총) 측정.

`perf_block("db")`로 감싼 구간의 누적 시간을 flask.g에 모으고, request_logger가 로그와
Server-Timing 헤더로 노출한다(브라우저 네트워크 탭에서 구간 확인). 병목을 수치로 증명하기 위함.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

try:
    from flask import g, has_request_context
except Exception:  # flask 없는 컨텍스트(테스트 등)
    g = None

    def has_request_context():
        return False


_ATTR = "_kgp_perf"


def _bucket() -> dict:
    if not has_request_context():
        return {}
    d = getattr(g, _ATTR, None)
    if d is None:
        d = {}
        setattr(g, _ATTR, d)
    return d


@contextmanager
def perf_block(name: str):
    """이 블록의 경과 시간(ms)을 name 버킷에 누적한다(중첩·반복 호출 합산)."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = (time.perf_counter() - t0) * 1000.0
        b = _bucket()
        if b is not None:
            b[name] = round(b.get(name, 0.0) + dt, 2)


_CNT_ATTR = "_kgp_perf_count"


def _counter() -> dict:
    if not has_request_context():
        return {}
    d = getattr(g, _CNT_ATTR, None)
    if d is None:
        d = {}
        setattr(g, _CNT_ATTR, d)
    return d


def perf_count(name: str, n: int = 1) -> None:
    """이벤트 카운트(예: DB 쿼리·연결 수) — N+1 진단용."""
    c = _counter()
    if c is not None:
        c[name] = c.get(name, 0) + n


def perf_counts() -> dict:
    c = _counter()
    return dict(c) if c else {}


def perf_snapshot() -> dict:
    """현재까지 누적된 구간 타이밍(ms) 스냅샷."""
    b = _bucket()
    return dict(b) if b else {}


def perf_server_timing() -> str:
    """Server-Timing 헤더 값(예: 'db;dur=12.3, render;dur=45.6')."""
    b = perf_snapshot()
    if not b:
        return ""
    return ", ".join(f"{k};dur={v}" for k, v in b.items())
