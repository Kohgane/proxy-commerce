"""Z10-B(오너 2026-10-11 02:10~02:33 KST — OOM 5회) — 잡·크론 실행 중 **200ms RSS 샘플러**.

단계 경계 측정(`rss.span`)은 경계 **사이**의 순간 피크를 못 본다. 실측 02:24:30 사전검증 job=3aaff0c7:
`pv_job_start rss=156 peak=156` → 3초 뒤 `image_fetch n=1/5 rss=159 peak=417` — 그 사이 누군가 +261MB를 잡았다 놓았다.
`peak`는 `VmHWM`(프로세스 생애 최대, **모든 스레드 합**)이라 「이 잡이 했다」가 아니다 — 같은 프로세스의 다른 스레드
(쿠팡 대표 사진 판정 `cpx-check`·이미지 저장본 크론)일 수 있다. 그래서:

- `watch(name)` 동안 200ms(`Z10_SAMPLE_MS`)마다 `VmRSS`를 읽어 **이 구간의 최대**와 그 시각을 잡는다.
- `Z10_TRACE=1`이면 피크가 20MB 이상 오를 때마다 **tracemalloc 상위 5**(줄 단위)와 **모든 스레드의 맨 위 프레임**을 찍어 둔다
  (Pillow의 화소 버퍼는 tracemalloc에 안 잡힌다 — 그래서 스택이 같이 필요하다: 피크 순간 누가 디코드 중이었나).
- 끝날 때 `[RSS] stage=<name>_peak peak_mb=… base_mb=… delta_mb=… at_ms=… top=… stacks=…` 한 줄.
- 상한(`PREVALIDATE_RSS_LIMIT_MB`, 기본 400)도 샘플러가 본다 — 넘은 순간을 기록해 두면 잡 스레드의 다음 `rss.guard`가
  그 잡만 멈춘다(C 디코드 한가운데는 끊을 수 없다 — 다음 경계에서).
- `active_count()` — 지금 도는 잡·크론 수. gunicorn 워커 재시작 훅은 0일 때만 워커를 갈아끼운다.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger("rss")

_LOCK = threading.Lock()
_ACTIVE: Dict[int, dict] = {}
_SEQ = [0]
_THREAD: List[Optional[threading.Thread]] = [None]
_TRACE_STEP_MB = 20


def interval_sec() -> float:
    try:
        return max(0.02, int(os.getenv("Z10_SAMPLE_MS", "200") or 200) / 1000.0)
    except (TypeError, ValueError):
        return 0.2


def trace_on() -> bool:
    return str(os.getenv("Z10_TRACE", "0")).strip() == "1"


def active_count() -> int:
    with _LOCK:
        return len(_ACTIVE)


def active_names() -> List[str]:
    with _LOCK:
        return [w["name"] for w in _ACTIVE.values()]


def over(job: str) -> Optional[tuple]:
    """이 잡(또는 잡 이름 없는 감시 전체) 구간에 상한을 넘은 적이 있나 → `(rss_mb, limit_mb, at_ms)` 또는 None."""
    with _LOCK:
        for w in _ACTIVE.values():
            if w.get("over") and (not job or w.get("job") == job):
                return w["over"]
    return None


def _top_frames(skip_ident: int) -> List[str]:
    """모든 스레드의 맨 위 2프레임(우리 코드 쪽) — 「피크 순간 누가 무엇을 하고 있었나」."""
    out = []
    names = {t.ident: t.name for t in threading.enumerate()}
    for ident, frame in sys._current_frames().items():
        if ident == skip_ident:
            continue
        chain, f = [], frame
        while f is not None and len(chain) < 40:
            chain.append(f)
            f = f.f_back
        ours = [fr for fr in chain if "/src/" in fr.f_code.co_filename.replace("\\", "/")]
        pick = (ours or chain)[:2]
        if not pick:
            continue
        desc = " < ".join(f"{os.path.basename(fr.f_code.co_filename)}:{fr.f_lineno} {fr.f_code.co_name}" for fr in pick)
        out.append(f"{names.get(ident, ident)}: {desc}")
    return out[:8]


def _tm_top5() -> List[str]:
    try:
        import tracemalloc
        if not tracemalloc.is_tracing():
            return []
        snap = tracemalloc.take_snapshot()
        snap = snap.filter_traces((tracemalloc.Filter(False, tracemalloc.__file__),
                                   tracemalloc.Filter(False, "<frozen importlib._bootstrap>")))
        stats = snap.statistics("lineno")[:5]
        return [f"{os.path.relpath(s.traceback[0].filename) if s.traceback else '?'}:{s.traceback[0].lineno if s.traceback else 0}"
                f" {s.size / 1048576:.1f}MB x{s.count}" for s in stats]
    except Exception as exc:                                         # noqa: BLE001 — 계측이 일을 막지 않는다
        return [f"tracemalloc 실패 {type(exc).__name__}"]


def _loop() -> None:
    from src.utils import rss as _rss
    me = threading.get_ident()
    while True:
        with _LOCK:
            if not _ACTIVE:
                _THREAD[0] = None
                return
            watches = list(_ACTIVE.values())
        cur, _hwm = _rss.read_mb()
        now = time.monotonic()
        lim = _rss.job_limit_mb()
        traced = None
        for w in watches:
            w["samples"] += 1
            if cur > w["peak"]:
                w["peak"], w["peak_at"] = cur, int((now - w["t0"]) * 1000)
                if w["trace"] and cur >= w["traced_mb"] + _TRACE_STEP_MB:
                    if traced is None:
                        traced = (_tm_top5(), _top_frames(me))
                    w["traced_mb"] = cur
                    w["top"], w["stacks"] = traced
            if lim > 0 and cur > lim and not w.get("over") and w.get("job"):
                w["over"] = (cur, lim, int((now - w["t0"]) * 1000))
                if not w.get("stacks"):
                    w["stacks"] = _top_frames(me)
        time.sleep(interval_sec())


def _ensure_thread() -> None:
    with _LOCK:
        t = _THREAD[0]
        if t is not None and t.is_alive():
            return
        t = threading.Thread(target=_loop, daemon=True, name="rss-sampler")
        _THREAD[0] = t
    t.start()


@contextlib.contextmanager
def watch(name: str, job: str = ""):
    """이 구간 동안 200ms 샘플링 — 끝나면 구간 피크 한 줄. 돌려주는 dict에 `peak`·`base`·`top`·`stacks`가 남는다."""
    from src.utils import rss as _rss
    base, _ = _rss.read_mb()
    tr = trace_on()
    if tr:
        try:
            import tracemalloc
            if not tracemalloc.is_tracing():
                tracemalloc.start(1)
        except Exception:                                            # noqa: BLE001
            tr = False
    w = {"name": name, "job": job or "", "t0": time.monotonic(), "base": base, "peak": base, "peak_at": 0,
         "samples": 0, "trace": tr, "traced_mb": base, "top": [], "stacks": [], "over": None}
    with _LOCK:
        _SEQ[0] += 1
        key = _SEQ[0]
        _ACTIVE[key] = w
    _ensure_thread()
    try:
        yield w
    finally:
        with _LOCK:
            _ACTIVE.pop(key, None)
            idle = not _ACTIVE
        cur, _ = _rss.read_mb()
        w["peak"] = max(w["peak"], cur)
        extra = {"job": (job or "")[:8], "base_mb": base, "delta_mb": w["peak"] - base if base >= 0 else "",
                 "at_ms": w["peak_at"], "samples": w["samples"],
                 "over": f"{w['over'][0]}>{w['over'][1]}" if w["over"] else ""}
        if w["top"]:
            extra["top"] = " | ".join(w["top"])
        if w["stacks"]:
            extra["stacks"] = " | ".join(w["stacks"])
        logger.info("[RSS] stage=%s_peak peak_mb=%d %s", name, w["peak"],
                    " ".join(f"{k}={v}" for k, v in extra.items() if v not in (None, "")))
        if idle and tr:
            try:
                import tracemalloc
                tracemalloc.stop()
            except Exception:                                        # noqa: BLE001
                pass
