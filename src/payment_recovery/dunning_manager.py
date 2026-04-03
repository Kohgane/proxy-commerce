"""src/payment_recovery/dunning_manager.py — 독촉 관리자."""
from __future__ import annotations


class DunningManager:
    """독촉 관리자."""

    def __init__(self) -> None:
        self._dunning_history: dict[str, list] = {}

    def send_dunning(self, payment_id: str, level: int) -> dict:
        """독촉을 발송한다."""
        record = {'payment_id': payment_id, 'level': level, 'status': 'sent'}
        self._dunning_history.setdefault(payment_id, []).append(record)
        return record

    def escalate(self, payment_id: str, current_level: int) -> dict:
        """독촉 수준을 높인다."""
        return self.send_dunning(payment_id, current_level + 1)

    def get_history(self, payment_id: str) -> list:
        """독촉 이력을 반환한다."""
        return list(self._dunning_history.get(payment_id, []))
