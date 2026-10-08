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
    extra = " ".join(f"{k}={v}" for k, v in kw.items() if v not in (None, ""))
    logger.info("[RSS] stage=%s rss_mb=%d peak_mb=%d%s", stage, cur, peak, (" " + extra) if extra else "")
    return cur, peak
