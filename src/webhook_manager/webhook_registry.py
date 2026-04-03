"""src/webhook_manager/webhook_registry.py — 웹훅 엔드포인트 등록/수정/삭제."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class WebhookRegistry:
    """웹훅 엔드포인트 등록/수정/삭제."""

    def __init__(self) -> None:
        self._webhooks: Dict[str, dict] = {}

    def register(self, url: str, events: List[str], secret: str = "",
                 name: str = "", **kwargs) -> dict:
        """웹훅 등록."""
        if not url:
            raise ValueError("url은 필수입니다.")
        webhook_id = kwargs.get("webhook_id") or str(uuid.uuid4())
        webhook = {
            "webhook_id": webhook_id,
            "url": url,
            "events": events or [],
            "secret": secret,
            "name": name,
            "active": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self._webhooks[webhook_id] = webhook
        return dict(webhook)

    def get(self, webhook_id: str) -> Optional[dict]:
        w = self._webhooks.get(webhook_id)
        return dict(w) if w else None

    def list(self, event: str = None, active_only: bool = False) -> List[dict]:
        webhooks = list(self._webhooks.values())
        if active_only:
            webhooks = [w for w in webhooks if w.get("active")]
        if event:
            webhooks = [w for w in webhooks if event in w.get("events", [])]
        return [dict(w) for w in webhooks]

    def update(self, webhook_id: str, **kwargs) -> dict:
        if webhook_id not in self._webhooks:
            raise KeyError(f"웹훅 없음: {webhook_id}")
        for key, value in kwargs.items():
            if key not in ("webhook_id", "created_at"):
                self._webhooks[webhook_id][key] = value
        self._webhooks[webhook_id]["updated_at"] = _now_iso()
        return dict(self._webhooks[webhook_id])

    def delete(self, webhook_id: str) -> bool:
        if webhook_id not in self._webhooks:
            return False
        del self._webhooks[webhook_id]
        return True

    def deactivate(self, webhook_id: str) -> dict:
        return self.update(webhook_id, active=False)
