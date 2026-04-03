"""src/email_service/ — Phase 56: 이메일 서비스."""
from __future__ import annotations

from .email_provider import EmailProvider
from .smtp_provider import SMTPProvider
from .sendgrid_provider import SendGridProvider
from .email_template import EmailTemplate
from .email_queue import EmailQueue
from .email_tracker import EmailTracker

__all__ = [
    "EmailProvider",
    "SMTPProvider",
    "SendGridProvider",
    "EmailTemplate",
    "EmailQueue",
    "EmailTracker",
]
