"""src/customer_service/escalation.py — SLA-based escalation rules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from .models import Ticket

SLA_ALERT_HOURS = 24
SLA_ESCALATE_HOURS = 48


class EscalationRule:
    """Checks SLA compliance for tickets."""

    def check_sla(self, ticket: Ticket) -> Optional[str]:
        """Return 'escalate' if >48h, 'alert' if >24h, None if within SLA."""
        now = datetime.utcnow()
        updated = ticket.updated_at
        # Normalize to naive UTC for comparison
        if updated.tzinfo is not None:
            updated = updated.astimezone(timezone.utc).replace(tzinfo=None)
        elapsed_hours = (now - updated).total_seconds() / 3600

        if elapsed_hours > SLA_ESCALATE_HOURS:
            return 'escalate'
        if elapsed_hours > SLA_ALERT_HOURS:
            return 'alert'
        return None

    def get_overdue_tickets(self, tickets: List[Ticket]) -> List[dict]:
        """Return tickets with non-None SLA status."""
        result = []
        for ticket in tickets:
            sla_status = self.check_sla(ticket)
            if sla_status is not None:
                result.append({
                    'ticket_id': ticket.id,
                    'customer_id': ticket.customer_id,
                    'subject': ticket.subject,
                    'sla_status': sla_status,
                    'updated_at': ticket.updated_at.isoformat(),
                })
        return result
