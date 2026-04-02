"""src/customer_service/ticket_manager.py — In-memory ticket management."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from .models import Ticket, TicketMessage, TicketPriority, TicketStatus


class TicketManager:
    """Manages CS tickets in memory."""

    def __init__(self) -> None:
        self._tickets: Dict[str, Ticket] = {}

    def create(
        self,
        customer_id: str,
        subject: str,
        description: str,
        priority: str = 'normal',
    ) -> Ticket:
        now = datetime.utcnow()
        ticket = Ticket(
            id=str(uuid4()),
            customer_id=customer_id,
            subject=subject,
            description=description,
            status=TicketStatus.open,
            priority=TicketPriority(priority),
            assigned_to=None,
            created_at=now,
            updated_at=now,
        )
        self._tickets[ticket.id] = ticket
        return ticket

    def get(self, ticket_id: str) -> Optional[Ticket]:
        return self._tickets.get(ticket_id)

    def list_tickets(
        self,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> List[Ticket]:
        result = list(self._tickets.values())
        if status is not None:
            result = [t for t in result if t.status.value == status]
        if assigned_to is not None:
            result = [t for t in result if t.assigned_to == assigned_to]
        return result

    def update_status(self, ticket_id: str, status: str) -> Optional[Ticket]:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return None
        ticket.status = TicketStatus(status)
        ticket.updated_at = datetime.utcnow()
        return ticket

    def assign(self, ticket_id: str, agent_id: str) -> Optional[Ticket]:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return None
        ticket.assigned_to = agent_id
        ticket.updated_at = datetime.utcnow()
        return ticket

    def add_message(
        self,
        ticket_id: str,
        sender: str,
        content: str,
        is_auto: bool = False,
    ) -> Optional[TicketMessage]:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return None
        msg = TicketMessage(
            id=str(uuid4()),
            ticket_id=ticket_id,
            sender=sender,
            content=content,
            created_at=datetime.utcnow(),
            is_auto=is_auto,
        )
        ticket.messages.append(msg)
        ticket.updated_at = datetime.utcnow()
        return msg

    def close(self, ticket_id: str) -> Optional[Ticket]:
        return self.update_status(ticket_id, TicketStatus.closed.value)
