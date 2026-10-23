"""Y11-O(오너 2026-10-15 15:43~15:45 KST 503) — **사진 그리기 워커 하나**.

실측(운영 DB): 15:41 KST 다듬기 24장을 웹 프로세스 안(요청·다듬기 스레드)에서 그린 직후 사전검증이 시작됐다 —
인스턴스 합계 417MB에서 출발해 490MB까지(스마트스토어 `detail_judge`에서 469 > 460 상한으로 멈춤). 그 앞 시도는
시작 문지기(420MB)에서 503 「메모리 여유 없음」. 그리기(cv2 디코드·Pillow 화소 버퍼)가 여러 스레드에서 겹치고, 끝난 뒤에도
힙이 운영체제로 돌아가지 않아(glibc arena) 합계가 내려오지 않았다.

그래서:
- 모든 사진 그리기(`image_edit.render_local` — 오너 탭 편집·번역 다듬기·「빼고 등록」 상자 지우기)는 이 워커 스레드 **하나**에서
  한 장씩 돈다(`run`). 부른 쪽은 끝날 때까지 기다린다(화면 흐름은 그대로).
- 장마다 끝나면 `gc.collect()` + `malloc_trim(0)`(glibc가 놓은 힙을 운영체제에 돌려준다).
- 장마다 200ms 샘플러 피크를 `[RSS] stage=render:…_peak` 한 줄 + 운영 DB(`rss:recent`)에 남긴다(로그를 못 볼 때 보고용).
- `busy()` = 그리는 중이거나 끝난 지 `RENDER_SETTLE_SEC`(기본 5초)가 안 됐다 — 사전검증은 이때 시작하지 않고 기다린다
  (「지금 RSS」가 아니라 「그리기 끝나고 5초 뒤 RSS」로 문지기를 본다).
"""
from __future__ import annotations

import concurrent.futures as _cf
import gc
import logging
import os
import queue
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("rss")

_Q: "queue.Queue" = queue.Queue()
_LOCK = threading.Lock()
_STATE = {"thread": None, "busy": 0, "last_end": 0.0, "done": 0}


def settle_sec() -> float:
    try:
        return max(0.0, float(os.getenv("RENDER_SETTLE_SEC", "5") or 5))
    except (TypeError, ValueError):
        return 5.0


def enabled() -> bool:
    return str(os.getenv("RENDER_WORKER", "1")).strip() != "0"


def trim() -> bool:
    """glibc `malloc_trim(0)` — 놓은 힙을 운영체제에 돌려준다. glibc가 아니면 False."""
    try:
        import ctypes
        return bool(ctypes.CDLL("libc.so.6").malloc_trim(0))
    except Exception:                                             # noqa: BLE001
        return False


TICKS_KEY = "rss:ticks"
TICKS_KEEP = 400


def record_tick(kind: str, **kw) -> None:
    """Y15 순찰 41(오너 2026-10-23 「틱 경계 프로브」): 리스 틱 시작/끝 · 요청 100개마다의 RSS·스레드 — `rss:ticks` 400줄.
    `rss:recent`(60줄)에 섞으면 2시간 치가 사전검증·작업 기록을 밀어내서 따로 둔다. 실패해도 일은 계속."""
    from datetime import datetime, timezone
    try:
        from src.db import image_translate_queue_pg as st
        cur = st.state_get(TICKS_KEY) or {}
        rows = list(cur.get("rows") or [])[-(TICKS_KEEP - 1):] + [{"at": datetime.now(timezone.utc).isoformat(), "kind": kind, **kw}]
        st.state_set(TICKS_KEY, {"rows": rows})
    except Exception as exc:                                      # noqa: BLE001
        logger.debug("[RSS] 틱 기록 실패: %s", exc)


def probe_row() -> dict:
    """지금 이 프로세스의 RSS(MB) · 살아 있는 스레드 수 · 서비스 이름 — 값만(무거운 측정 없음)."""
    import threading
    from src.utils import rss
    mb, peak = rss.read_mb()
    try:
        from src.services.workers import service_name
        svc = service_name()
    except Exception:                                             # noqa: BLE001
        svc = ""
    return {"mb": mb, "hwm_mb": peak, "threads": threading.active_count(), "svc": svc}


def tick_probe_on() -> bool:
    return str(os.getenv("TICK_PROBE", "1")).strip().lower() not in ("0", "false", "no", "off")


def _record(row: dict) -> None:
    """최근 그리기·사전검증 메모리 기록 60줄(운영 DB `rss:recent`) — 실패해도 일은 계속."""
    try:
        from src.db import image_translate_queue_pg as st
        cur = st.state_get("rss:recent") or {}
        rows = list(cur.get("rows") or [])[-59:] + [row]
        st.state_set("rss:recent", {"rows": rows})
    except Exception as exc:                                      # noqa: BLE001
        logger.debug("[RSS] 기록 실패: %s", exc)


def record(kind: str, **kw) -> None:
    from datetime import datetime, timezone
    _record({"at": datetime.now(timezone.utc).isoformat(), "kind": kind, **kw})


def _loop(q: "queue.Queue", state: dict) -> None:
    """워커 본체 — 시작할 때 받은 큐·상태만 쓴다(모듈 전역을 매번 다시 읽으면 바뀐 큐를 옛 워커가 같이 먹는다)."""
    from src.utils import rss_sampler as _smp
    me = threading.current_thread()
    while True:
        try:
            item = q.get(timeout=60)
        except queue.Empty:
            with _LOCK:
                if q.empty():
                    if state.get("thread") is me:          # 내가 지금 워커일 때만 자리를 비운다
                        state["thread"] = None
                    return
            continue
        fn, a, kw, fut, name = item
        if not fut.set_running_or_notify_cancel():
            continue
        with _LOCK:
            state["busy"] += 1
        t0 = time.monotonic()
        w: dict = {}
        out, err = None, None
        try:
            with _smp.watch("render:" + name) as w:
                out = fn(*a, **kw)
        except BaseException as exc:                              # noqa: BLE001 — 부른 쪽에 그대로
            err = exc
        a = kw = None                                             # noqa: F841 — 입력(바탕 그림 바이트) 참조를 놓는다
        gc.collect()
        trimmed = trim()
        from src.utils import rss as _rss
        after = _rss.instance_mb()
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("[RSS] stage=render_done name=%s ms=%d inst_after_mb=%d trimmed=%s", name, ms, after, trimmed)
        record("render", name=name, ms=ms, base_mb=w.get("base"), peak_mb=w.get("peak"),
               inst_base_mb=w.get("inst_base"), inst_peak_mb=w.get("inst_peak"), inst_after_mb=after, ok=err is None)
        with _LOCK:
            state["busy"] -= 1
            state["last_end"] = time.monotonic()
            state["done"] += 1
        # 정리·기록을 마친 뒤에 부른 쪽을 깨운다(그리기 끝 = 메모리까지 돌려준 뒤)
        if err is not None:
            fut.set_exception(err)
        else:
            fut.set_result(out)
        out = err = None                                          # noqa: F841


def _ensure() -> None:
    # 잠금 안에서 start — 밖에서 하면 그 사이 다른 호출이 「아직 안 살아 있음」(is_alive False)으로 보고 워커를 하나 더 만든다
    #   (두 장이 동시에 그려졌다 — Y11O-1 계약이 잡음).
    with _LOCK:
        t = _STATE["thread"]
        if t is not None and t.is_alive():
            return
        t = threading.Thread(target=_loop, args=(_Q, _STATE), daemon=True, name="render-worker")
        _STATE["thread"] = t
        t.start()


def run(fn: Callable, *a: Any, _name: str = "render", _timeout: float = 180.0, **kw: Any) -> Any:
    """`fn(*a, **kw)`를 그리기 워커에서 돌리고 결과를 돌려준다(예외도 그대로). 워커 안에서 다시 부르면 그 자리에서."""
    if not enabled() or threading.current_thread() is _STATE["thread"]:
        return fn(*a, **kw)
    fut: _cf.Future = _cf.Future()
    _Q.put((fn, a, kw, fut, _name))
    _ensure()
    return fut.result(timeout=_timeout)


def busy() -> bool:
    """그리는 중·줄 선 그리기 있음·끝난 지 `settle_sec()` 안 됨."""
    with _LOCK:
        b, last = _STATE["busy"], _STATE["last_end"]
    return bool(b) or not _Q.empty() or (last > 0 and time.monotonic() - last < settle_sec())


def wait_idle(timeout: float) -> tuple:
    """그리기가 끝나고 `settle_sec()`가 지날 때까지 기다린다 — `(기다린 초, 시간 넘김?)`."""
    t0 = time.monotonic()
    while busy():
        if time.monotonic() - t0 >= timeout:
            return round(time.monotonic() - t0, 1), True
        time.sleep(0.25)
    return round(time.monotonic() - t0, 1), False
