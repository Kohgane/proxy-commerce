"""Z7(오너 2026-10-08) — 프로세스 메모리(RSS) 한 줄 로그. 다음 OOM 때 「어느 단계에서 커졌나」 좌표가 바로 나오게.

`/proc/self/status`의 VmRSS(지금)·VmHWM(이 프로세스 생애 최대)를 MB로 읽는다. 리눅스가 아니면 `resource`의
ru_maxrss(최대만)로 대신하고, 그것도 없으면 -1. 로그 형식: `[RSS] stage=<단계> rss_mb=<지금> peak_mb=<최대> …`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("rss")


def read_mb() -> tuple:
    """`(rss_mb, peak_mb)` — 못 읽으면 -1."""
    try:
        cur = peak = -1
        with open("/proc/self/status", encoding="ascii", errors="ignore") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    cur = int(line.split()[1]) // 1024
                elif line.startswith("VmHWM:"):
                    peak = int(line.split()[1]) // 1024
        if cur >= 0:
            return cur, peak
    except OSError:
        pass
    try:
        import resource
        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) // 1024
        return -1, peak
    except Exception:                                      # noqa: BLE001
        return -1, -1


def log(stage: str, **kw) -> tuple:
    """단계 하나 — 로그 한 줄을 남기고 `(rss_mb, peak_mb)`를 돌려준다."""
    cur, peak = read_mb()
    try:
        if "job" not in kw and JOB.get():                 # Z10: 사전검증 잡 안이면 어느 잡인지 같은 줄에
            kw = {"job": JOB.get()[:8], **kw}
    except NameError:                                      # 모듈 로드 중(아래 정의 전)
        pass
    extra = " ".join(f"{k}={v}" for k, v in kw.items() if v not in (None, ""))
    logger.info("[RSS] stage=%s rss_mb=%d peak_mb=%d%s", stage, cur, peak, (" " + extra) if extra else "")
    return cur, peak


# ── Z10(오너 2026-10-10 22:29~22:35 KST OOM) — 단계 측정 · 잡 단위 상한 ─────────────────────────────────────────
#   실측: 네이버 사전검증 1건이 159 → 420MB(+261MB, 같은 시각 Render 512MB 초과 2회). 쿠팡은 159 → 181(peak 220).
#   단계마다 RSS·증감·소요 ms를 같은 줄에 남기고(`span`), 사전검증 잡 안에서는 RSS가 상한을 넘으면 **그 잡만** 멈춘다(`guard`).
import contextlib as _cl
import contextvars as _cv
import os as _os
import time as _time

#: 지금 도는 사전검증 잡 id(로그 줄·상한 판정용). 잡 밖(일반 요청)에서는 빈 값 — 상한을 적용하지 않는다.
JOB: "_cv.ContextVar[str]" = _cv.ContextVar("rss_job", default="")


def job_limit_mb() -> int:
    """잡 하나가 넘으면 안 되는 프로세스 RSS(MB) — `PREVALIDATE_RSS_LIMIT_MB`(기본 400). 0이면 끈다."""
    try:
        return int(_os.getenv("PREVALIDATE_RSS_LIMIT_MB", "400") or 400)
    except (TypeError, ValueError):
        return 400


class MemoryCapExceeded(RuntimeError):
    """사전검증 잡이 메모리 상한을 넘었다 — 잡만 멈추고(카드에 원문) 워커·서비스는 살린다."""

    def __init__(self, stage: str, rss_mb: int, limit_mb: int, detail: str = ""):
        self.stage, self.rss_mb, self.limit_mb, self.detail = stage, rss_mb, limit_mb, detail
        super().__init__(f"메모리 상한 — {stage}에서 {rss_mb}MB(상한 {limit_mb}MB){(' · ' + detail) if detail else ''}")


def guard(stage: str, detail: str = "") -> None:
    """사전검증 잡 안에서만: RSS가 상한을 넘었으면 `MemoryCapExceeded`. 잡 밖이면 아무것도 안 한다."""
    if not JOB.get():
        return
    lim = job_limit_mb()
    if lim <= 0:
        return
    cur, _peak = read_mb()
    if cur > lim:
        log("cap_exceeded", job=JOB.get()[:8], at=stage, limit_mb=lim, detail=detail)
        raise MemoryCapExceeded(stage, cur, lim, detail)


@_cl.contextmanager
def span(stage: str, **kw):
    """한 단계 — 끝날 때 `[RSS] stage=… rss_mb=… delta_mb=… ms=… job=…` 한 줄. `kw`(장수·바이트 등)는 안에서 채울 수 있게 dict로 넘긴다."""
    before, _p = read_mb()
    t0 = _time.monotonic()
    box = dict(kw)
    try:
        yield box
    finally:
        cur, _peak = read_mb()
        log(stage, delta_mb=(cur - before) if cur >= 0 and before >= 0 else "",
            ms=int((_time.monotonic() - t0) * 1000), **box)
