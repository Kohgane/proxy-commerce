"""배송 상태 변화 감지 — 폴링 기반 상태 추적."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import DeliveryEvent, NotificationPreference
from .notification_dispatcher import DeliveryNotificationDispatcher
from .delay_detector import DeliveryDelayDetector
from .exception_handler import DeliveryExceptionHandler

logger = logging.getLogger(__name__)

# 폴링 기본 주기 (초)
DEFAULT_POLL_INTERVAL = 300  # 5분


class _WatchEntry:
    """추적 등록 항목."""
    __slots__ = ('tracking_no', 'carrier', 'order_id', 'user_id', 'last_status')

    def __init__(self, tracking_no: str, carrier: str, order_id: str, user_id: str):
        self.tracking_no = tracking_no
        self.carrier = carrier
        self.order_id = order_id
        self.user_id = user_id
        self.last_status: Optional[str] = None


class DeliveryStatusWatcher:
    """배송 상태 변화 감지기 — 폴링 기반."""

    def __init__(
        self,
        dispatcher: DeliveryNotificationDispatcher = None,
        delay_detector: DeliveryDelayDetector = None,
        exception_handler: DeliveryExceptionHandler = None,
        preference_manager=None,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._dispatcher = dispatcher or DeliveryNotificationDispatcher()
        self._delay_detector = delay_detector or DeliveryDelayDetector()
        self._exception_handler = exception_handler or DeliveryExceptionHandler()
        self._pref_mgr = preference_manager
        self._poll_interval = poll_interval
        self._entries: Dict[str, _WatchEntry] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register(
        self,
        tracking_no: str,
        carrier: str,
        order_id: str,
        user_id: str,
    ) -> _WatchEntry:
        """배송 추적 등록."""
        entry = _WatchEntry(tracking_no, carrier, order_id, user_id)
        self._entries[tracking_no] = entry
        logger.info("배송 추적 등록: %s (%s) — 주문 %s", tracking_no, carrier, order_id)
        return entry

    def unregister(self, tracking_no: str) -> bool:
        """추적 해제."""
        if tracking_no in self._entries:
            del self._entries[tracking_no]
            return True
        return False

    def get_entry(self, tracking_no: str) -> Optional[_WatchEntry]:
        """등록된 추적 항목 조회."""
        return self._entries.get(tracking_no)

    def list_entries(self) -> List[_WatchEntry]:
        """등록된 모든 추적 항목 반환."""
        return list(self._entries.values())

    def tick(self) -> List[DeliveryEvent]:
        """단일 폴링 사이클 실행 (테스트/동기 호출용)."""
        return self.poll_once()

    def poll_once(self) -> List[DeliveryEvent]:
        """모든 등록 운송장 상태 1회 폴링."""
        events: List[DeliveryEvent] = []
        for tracking_no, entry in list(self._entries.items()):
            try:
                event = self._check_entry(entry)
                if event:
                    events.append(event)
            except Exception as exc:
                logger.error("폴링 오류 %s: %s", tracking_no, exc)
        return events

    def start(self) -> None:
        """백그라운드 폴링 스레드 시작."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='DeliveryStatusWatcher')
        self._thread.start()
        logger.info("DeliveryStatusWatcher 시작 (주기: %ds)", self._poll_interval)

    def stop(self) -> None:
        """백그라운드 폴링 스레드 중지."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("DeliveryStatusWatcher 중지")

    def _run_loop(self) -> None:
        """백그라운드 폴링 루프."""
        while self._running:
            try:
                self.poll_once()
            except Exception as exc:
                logger.error("폴링 루프 오류: %s", exc)
            time.sleep(self._poll_interval)

    def _check_entry(self, entry: _WatchEntry) -> Optional[DeliveryEvent]:
        """단일 운송장 상태 확인. 상태 변화 감지 시 알림 발송."""
        tracker = self._get_tracker()
        record = tracker.get_status(entry.tracking_no)
        if record is None:
            return None

        new_status = record.status.value if hasattr(record.status, 'value') else str(record.status)

        # 지연 감지기에 현재 상태 기록
        self._delay_detector.record_status(entry.tracking_no, new_status)

        # 상태 변화 감지
        if new_status == entry.last_status:
            # 지연 검사 (상태 변화 없어도 수행)
            anomalies = self._delay_detector.check_delays(
                entry.tracking_no, new_status, entry.order_id
            )
            for anomaly in anomalies:
                self._exception_handler.handle_anomaly(anomaly, entry.user_id)
            return None

        event = DeliveryEvent(
            tracking_no=entry.tracking_no,
            status=new_status,
            location=record.events[-1].location if record.events else '',
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw={},
        )
        entry.last_status = new_status
        logger.info("배송 상태 변화: %s → %s", entry.tracking_no, new_status)

        # 예외 상태 처리
        if new_status == 'exception':
            self._exception_handler.handle_exception(
                entry.tracking_no, entry.order_id, entry.user_id
            )

        # 알림 발송
        pref = self._get_preference(entry.user_id)
        self._dispatcher.dispatch(event, pref, entry.order_id)

        return event

    def _get_tracker(self):
        from ..shipping.tracker import ShipmentTracker
        return ShipmentTracker()

    def _get_preference(self, user_id: str) -> NotificationPreference:
        if self._pref_mgr:
            return self._pref_mgr.get(user_id)
        return NotificationPreference(user_id=user_id)
