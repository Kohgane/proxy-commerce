"""수신 거부 관리."""
from __future__ import annotations
from datetime import datetime

class UnsubscribeManager:
    def __init__(self) -> None:
        self._unsubscribed: dict[str, dict] = {}

    def unsubscribe(self, email: str, reason: str = "") -> dict:
        entry = {"email": email, "reason": reason, "timestamp": datetime.now().isoformat()}
        self._unsubscribed[email] = entry
        return entry

    def is_unsubscribed(self, email: str) -> bool:
        return email in self._unsubscribed

    def list(self) -> list[dict]:
        return list(self._unsubscribed.values())

    def resubscribe(self, email: str) -> bool:
        return bool(self._unsubscribed.pop(email, None))
