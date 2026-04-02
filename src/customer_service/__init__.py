"""src/customer_service/__init__.py — Customer Service package."""

from .auto_responder import AutoResponder
from .escalation import EscalationRule
from .models import Ticket, TicketMessage, TicketPriority, TicketStatus
from .ticket_manager import TicketManager

__all__ = [
    'AutoResponder',
    'EscalationRule',
    'Ticket',
    'TicketMessage',
    'TicketPriority',
    'TicketStatus',
    'TicketManager',
]
