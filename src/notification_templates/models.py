"""src/notification_templates/models.py — 알림 템플릿 모델."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TemplateVariable:
    """템플릿 변수."""

    name: str
    default: str = ''
    required: bool = False


@dataclass
class NotificationTemplate:
    """알림 템플릿."""

    name: str
    channel: str
    subject: str
    body: str
    variables: list[TemplateVariable] = field(default_factory=list)
    locale: str = 'ko'
    version: int = 1
