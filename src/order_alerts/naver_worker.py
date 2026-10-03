"""W1·W2 — 네이버 주문 폴러를 **웹 서비스 안 워커**로(기본 꺼짐).

운영 주문 알림은 지금 LinkLynk 서버 `order_notify_all_v1.py`가 보낸다. 이걸 켜면 **같은 주문이 두 번** 알림 갈 수 있으므로
오너가 `NAVER_ORDER_POLL=1`로 옮기기로 정할 때만 돈다. 켜도 `WORKERS_ENABLED` 서비스에서만, 서비스 간엔 DB 리스로 한 곳만.
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_STARTED = {"done": False}
_LOCK = threading.Lock()


def poll_enabled() -> bool:
    return str(os.getenv("NAVER_ORDER_POLL", "")).strip().lower() in ("1", "true", "yes", "on")


def _loop(pollers, interval: int):
    from src.services import workers as _w
    from .alert_dispatcher import AlertDispatcher
    from .order_tracker import OrderTracker
    dispatcher, tracker = AlertDispatcher(), OrderTracker()
    while True:
        if _w.lease("naver-order-poll", ttl=interval + 60):
            total = 0
            errs = []
            for p in pollers:
                try:
                    orders = tracker.filter_new_orders(p.fetch_new_orders())
                    for o in orders:
                        if dispatcher.send_new_order_alert(o):
                            tracker.mark_alerted(o)
                            total += 1
                except Exception as exc:
                    errs.append(f"{p.store}: {str(exc)[:120]}")
                    logger.error("[네이버 주문] %s 폴링 오류: %s", p.store, exc)
            _w.record_run("naver-order-poll", total, note=" · ".join(errs))
        time.sleep(interval)


def start_if_enabled() -> str:
    """조건이 맞으면 스레드 하나를 띄운다. 왜 안 띄웠는지를 돌려준다(로그·진단용)."""
    from src.services import workers as _w
    if not poll_enabled():
        return "꺼짐 — NAVER_ORDER_POLL 미설정(운영 알림은 LinkLynk order_notify_all_v1)"
    if not _w.workers_enabled():
        return f"꺼짐 — 이 서비스는 워커 아님({_w.gate_text()})"
    from .naver_order_poller import store_pollers
    pollers = store_pollers()
    if not pollers:
        return "꺼짐 — 키가 있는 스토어 없음"
    with _LOCK:
        if _STARTED["done"]:
            return "이미 실행 중"
        interval = int(os.getenv("ORDER_POLL_INTERVAL_SECONDS", "300") or 300)
        threading.Thread(target=_loop, args=(pollers, interval), daemon=True, name="naver-order-poll").start()
        _STARTED["done"] = True
    return f"실행 — {', '.join(p.store for p in pollers)}"
