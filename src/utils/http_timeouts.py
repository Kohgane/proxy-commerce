"""Z8(오너 2026-10-08 23:3x KST 워커 교착) — 모든 `requests` 호출의 타임아웃을 **한 곳에서** 강제한다.

`requests.get/post/request`, 직접 만든 `Session`, SDK 안의 `Session`(텐센트 등)은 전부 마지막에
`HTTPAdapter.send(request, timeout=…)`를 지난다. 그 자리 하나에서:

- 타임아웃이 **없으면**(None) → (connect 5s, read 15s)
- 숫자 하나면 → (min(값, 5), min(값, 15))
- (connect, read) 짝이면 → 각각 상한으로 자른다(None이면 상한)

상한은 env로 조정한다: `HTTP_CONNECT_TIMEOUT_MAX`(기본 5) · `HTTP_READ_TIMEOUT_MAX`(기본 15).
read 타임아웃은 「응답 전체」가 아니라 **바이트 사이 간격** 상한이다(requests 정의) — 그래도 무응답 서버에
요청 스레드가 영영 묶이는 일은 없어진다.
"""
from __future__ import annotations

import contextlib
import logging
import os
import threading
from typing import Any, Tuple

logger = logging.getLogger(__name__)

_INSTALLED = {"done": False, "orig": None}
_LOCAL = threading.local()          # allow()로 이 스레드만 read 상한을 잠시 올린다


def _env_float(name: str, default: float) -> float:
    try:
        v = float(os.getenv(name, "") or default)
        return v if v > 0 else default
    except ValueError:
        return default


def caps() -> Tuple[float, float]:
    read = _env_float("HTTP_READ_TIMEOUT_MAX", 15.0)
    extra = getattr(_LOCAL, "read", None)
    return _env_float("HTTP_CONNECT_TIMEOUT_MAX", 5.0), (max(read, extra) if extra else read)


@contextlib.contextmanager
def allow(read: float, why: str):
    """이 블록 안에서만, 이 스레드만 read 상한을 `read`초로 — 오래 걸리는 게 정상인 호출에만(사유를 로그에).

    쓰는 곳은 이 머리말에 적는다: ① 네이버 이미지 업로드(사진 최대 10장 한 요청 — 호출부가 60s를 준다)
    ② 텐센트 이미지 번역(백그라운드 워커 — 장당 20s). 요청 스레드의 일반 호출은 15s 그대로다.
    """
    prev = getattr(_LOCAL, "read", None)
    _LOCAL.read = float(read)
    logger.info("[HTTP] read 상한 %ss로 잠시 올림 — %s", read, why)
    try:
        yield
    finally:
        _LOCAL.read = prev


def clamp(timeout: Any) -> Tuple[float, float]:
    """호출부가 준 타임아웃 → (connect, read) — 없으면 상한, 있으면 상한으로 자른다."""
    c_max, r_max = caps()
    if timeout is None:
        return c_max, r_max
    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        c, r = timeout
        c = c_max if c is None else min(float(c), c_max)
        r = r_max if r is None else min(float(r), r_max)
        return c, r
    try:
        t = float(timeout)
    except (TypeError, ValueError):
        return c_max, r_max
    return min(t, c_max), min(t, r_max)


def install() -> bool:
    """`HTTPAdapter.send`를 한 번 감싼다(멱등). 이미 감쌌으면 False."""
    if _INSTALLED["done"]:
        return False
    from requests.adapters import HTTPAdapter
    orig = HTTPAdapter.send

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        return orig(self, request, stream=stream, timeout=clamp(timeout), verify=verify, cert=cert, proxies=proxies)

    send.__kgp_timeout_guard__ = True          # 테스트·진단이 설치 여부를 본다
    HTTPAdapter.send = send
    _INSTALLED.update(done=True, orig=orig)
    logger.info("[HTTP] 외부 호출 타임아웃 상한 설치 — connect %ss · read %ss", *caps())
    return True


def uninstall() -> None:
    """테스트용."""
    if _INSTALLED["done"] and _INSTALLED["orig"] is not None:
        from requests.adapters import HTTPAdapter
        HTTPAdapter.send = _INSTALLED["orig"]
    _INSTALLED.update(done=False, orig=None)
