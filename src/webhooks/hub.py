"""src/webhooks/hub.py — 통합 웹훅 허브.

플랫폼별 이벤트 핸들러를 등록하고 디스패치하는 허브.

환경변수:
  WEBHOOK_HUB_ENABLED  — 웹훅 허브 활성화 여부 (기본 "0")
"""

import logging
import os
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("WEBHOOK_HUB_ENABLED", "0") == "1"


class WebhookHub:
    """웹훅 허브 — 플랫폼별 이벤트 핸들러 등록 및 디스패치."""

    def __init__(self):
        # {platform: {event_type: [handler_func, ...]}}
        self._handlers: Dict[str, Dict[str, List[Callable]]] = {}

    def is_enabled(self) -> bool:
        """웹훅 허브 활성화 여부를 반환한다."""
        return os.getenv("WEBHOOK_HUB_ENABLED", "0") == "1"

    def register_handler(self, platform: str, event_type: str, handler_func: Callable) -> None:
        """핸들러를 등록한다.

        Args:
            platform: 플랫폼 이름 (예: "shopify", "woocommerce").
            event_type: 이벤트 타입 (예: "order/created").
            handler_func: 호출할 핸들러 함수.
        """
        self._handlers.setdefault(platform, {}).setdefault(event_type, []).append(handler_func)
        logger.debug("핸들러 등록: %s/%s → %s", platform, event_type, handler_func.__name__)

    def dispatch(self, platform: str, event_type: str, payload: Any) -> List[Any]:
        """등록된 핸들러에 이벤트를 디스패치한다.

        Args:
            platform: 플랫폼 이름.
            event_type: 이벤트 타입.
            payload: 전달할 페이로드.

        Returns:
            각 핸들러의 반환값 리스트.
        """
        handlers = self._handlers.get(platform, {}).get(event_type, [])
        results = []
        for handler in handlers:
            try:
                result = handler(payload)
                results.append(result)
            except Exception as exc:
                logger.error(
                    "핸들러 실행 실패 (%s/%s, %s): %s",
                    platform, event_type, handler.__name__, exc,
                )
                # 재시도 큐에 추가 (활성화된 경우)
                if os.getenv("WEBHOOK_RETRY_ENABLED", "0") == "1":
                    try:
                        from .retry_queue import retry_queue
                        retry_queue.enqueue(platform, event_type, payload)
                    except Exception as rq_exc:
                        logger.warning("재시도 큐 추가 실패: %s", rq_exc)

        return results

    def get_handlers(self, platform: str, event_type: str) -> List[Callable]:
        """등록된 핸들러 목록을 반환한다.

        Args:
            platform: 플랫폼 이름.
            event_type: 이벤트 타입.

        Returns:
            핸들러 함수 리스트.
        """
        return self._handlers.get(platform, {}).get(event_type, [])


# 모듈 레벨 싱글턴
hub = WebhookHub()
