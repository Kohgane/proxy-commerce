"""src/audit/event_types.py — 감사 이벤트 타입 정의.

감사 로그 시스템에서 사용하는 이벤트 타입 상수를 정의한다.
"""

from enum import Enum


class EventType(str, Enum):
    """감사 로그 이벤트 타입.

    str 상속으로 JSON 직렬화 시 문자열로 변환된다.
    """

    # ── 주문 이벤트 ───────────────────────────────────────
    ORDER_CREATED = "order.created"
    ORDER_ROUTED = "order.routed"
    ORDER_SHIPPED = "order.shipped"
    ORDER_COMPLETED = "order.completed"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REFUNDED = "order.refunded"
    ORDER_DUPLICATE_DETECTED = "order.duplicate_detected"

    # ── 가격 이벤트 ───────────────────────────────────────
    PRICE_CHANGED = "price.changed"
    PRICE_SYNC_STARTED = "price.sync_started"
    PRICE_SYNC_COMPLETED = "price.sync_completed"

    # ── 재고 이벤트 ───────────────────────────────────────
    STOCK_CHANGED = "stock.changed"
    STOCK_SYNC_STARTED = "stock.sync_started"
    STOCK_SYNC_COMPLETED = "stock.sync_completed"
    STOCK_LOW_ALERT = "stock.low_alert"

    # ── API 호출 이벤트 ───────────────────────────────────
    API_CALL_SUCCESS = "api.call_success"
    API_CALL_FAILURE = "api.call_failure"
    API_RATE_LIMITED = "api.rate_limited"
    API_CIRCUIT_OPENED = "api.circuit_opened"
    API_CIRCUIT_CLOSED = "api.circuit_closed"

    # ── 인증/보안 이벤트 ─────────────────────────────────
    LOGIN_ATTEMPT = "auth.login_attempt"
    LOGIN_SUCCESS = "auth.login_success"
    LOGIN_FAILURE = "auth.login_failure"
    WEBHOOK_VERIFIED = "auth.webhook_verified"
    WEBHOOK_REJECTED = "auth.webhook_rejected"

    # ── 설정 변경 이벤트 ─────────────────────────────────
    CONFIG_CHANGED = "config.changed"
    ENV_UPDATED = "config.env_updated"

    # ── 시스템 이벤트 ─────────────────────────────────────
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    HEALTH_CHECK = "system.health_check"
