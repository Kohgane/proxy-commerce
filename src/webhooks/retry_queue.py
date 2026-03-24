"""src/webhooks/retry_queue.py — 웹훅 재시도 큐.

실패한 웹훅 이벤트를 지수 백오프로 재시도한다.

환경변수:
  WEBHOOK_RETRY_ENABLED  — 재시도 큐 활성화 여부 (기본 "0")
  WEBHOOK_RETRY_MAX      — 최대 재시도 횟수 (기본 3)
"""

import datetime
import logging
import os
import threading
import uuid
from collections import deque
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_RETRY_ENABLED = os.getenv("WEBHOOK_RETRY_ENABLED", "0") == "1"
_RETRY_MAX = int(os.getenv("WEBHOOK_RETRY_MAX", "3"))


class RetryQueue:
    """스레드 안전한 웹훅 재시도 큐."""

    def __init__(self):
        self._queue: deque = deque()
        self._lock = threading.Lock()

    def is_enabled(self) -> bool:
        """재시도 큐 활성화 여부를 반환한다."""
        return os.getenv("WEBHOOK_RETRY_ENABLED", "0") == "1"

    def enqueue(self, platform: str, event_type: str, payload: Any) -> str:
        """재시도 큐에 항목을 추가한다.

        Args:
            platform: 플랫폼 이름.
            event_type: 이벤트 타입.
            payload: 페이로드.

        Returns:
            항목 ID 문자열.
        """
        item_id = str(uuid.uuid4())
        item: Dict[str, Any] = {
            "id": item_id,
            "platform": platform,
            "event_type": event_type,
            "payload": payload,
            "attempts": 0,
            "next_retry": datetime.datetime.utcnow(),
        }
        with self._lock:
            self._queue.append(item)
        logger.debug("재시도 큐 추가: %s (%s/%s)", item_id, platform, event_type)
        return item_id

    def process(self, hub) -> int:
        """현재 처리 가능한 항목을 처리한다.

        next_retry <= 현재 시각인 항목을 디스패치하고, 실패 시 지수 백오프로 재예약한다.

        Args:
            hub: WebhookHub 인스턴스.

        Returns:
            처리한 항목 수.
        """
        max_retries = int(os.getenv("WEBHOOK_RETRY_MAX", str(_RETRY_MAX)))
        now = datetime.datetime.utcnow()
        processed = 0

        with self._lock:
            items = list(self._queue)
            self._queue.clear()

        remaining = []
        for item in items:
            if item["next_retry"] > now:
                remaining.append(item)
                continue

            try:
                hub.dispatch(item["platform"], item["event_type"], item["payload"])
                processed += 1
                logger.info("재시도 성공: %s (%s/%s)", item["id"], item["platform"], item["event_type"])
            except Exception as exc:
                item["attempts"] += 1
                if item["attempts"] < max_retries:
                    # 지수 백오프: 2^attempts 초
                    backoff = 2 ** item["attempts"]
                    item["next_retry"] = now + datetime.timedelta(seconds=backoff)
                    remaining.append(item)
                    logger.warning(
                        "재시도 실패 (시도 %d/%d, 다음 재시도: %ds 후): %s — %s",
                        item["attempts"], max_retries, backoff, item["id"], exc,
                    )
                else:
                    logger.error(
                        "최대 재시도 횟수 초과, 폐기: %s (%s/%s)",
                        item["id"], item["platform"], item["event_type"],
                    )

        with self._lock:
            for item in remaining:
                self._queue.append(item)

        return processed

    def get_pending(self) -> List[Dict[str, Any]]:
        """대기 중인 항목 목록을 반환한다."""
        with self._lock:
            return list(self._queue)

    def get_stats(self) -> Dict[str, Any]:
        """큐 통계를 반환한다."""
        with self._lock:
            pending = len(self._queue)
        return {
            "pending": pending,
            "max_retries": int(os.getenv("WEBHOOK_RETRY_MAX", str(_RETRY_MAX))),
        }


# 모듈 레벨 싱글턴
retry_queue = RetryQueue()
