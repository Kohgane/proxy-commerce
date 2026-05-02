"""src/delivery_notifications/models.py — Phase 117: 배송 알림 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class DeliveryNotification:
    """발송된 배송 알림 기록."""
    order_id: str
    tracking_no: str
    carrier: str
    status_from: str
    status_to: str
    channel: str
    # 기본값이 있는 필드는 뒤에 배치
    id: str = field(default_factory=lambda: str(uuid4()))
    sent_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    success: bool = True


@dataclass
class DeliveryEvent:
    """배송 상태 변화 이벤트."""
    tracking_no: str
    status: str
    location: str
    timestamp: str
    raw: dict = field(default_factory=dict)


@dataclass
class NotificationPreference:
    """고객별 알림 설정."""
    user_id: str
    channels: list = field(default_factory=lambda: ['telegram'])
    language: str = 'ko'
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8
    frequency: str = 'all'


@dataclass
class DeliveryAnomaly:
    """배송 이상 감지 기록."""
    tracking_no: str
    # anomaly_type: delayed | stuck | lost | damaged
    anomaly_type: str
    detected_at: str
    # severity: low | medium | high
    severity: str
    order_id: str = ''
