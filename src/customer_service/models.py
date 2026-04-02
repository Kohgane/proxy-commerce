"""src/customer_service/models.py — Customer service data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class TicketStatus(str, Enum):
    open = 'open'
    in_progress = 'in_progress'
    waiting_customer = 'waiting_customer'
    resolved = 'resolved'
    closed = 'closed'


class TicketPriority(str, Enum):
    low = 'low'
    normal = 'normal'
    high = 'high'
    urgent = 'urgent'


@dataclass
class TicketMessage:
    id: str
    ticket_id: str
    sender: str
    content: str
    created_at: datetime
    is_auto: bool = False


@dataclass
class Ticket:
    id: str
    customer_id: str
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    assigned_to: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[TicketMessage] = field(default_factory=list)
