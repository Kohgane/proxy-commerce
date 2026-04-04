"""이메일 캠페인 CRUD + 스케줄링."""
from __future__ import annotations
import uuid
from .models import Campaign

class CampaignManager:
    def __init__(self) -> None:
        self._campaigns: dict[str, Campaign] = {}

    def create(self, name: str, subject: str, body_template: str, segment_id: str = "", scheduled_at: str = "") -> Campaign:
        c = Campaign(
            campaign_id=str(uuid.uuid4()),
            name=name,
            subject=subject,
            body_template=body_template,
            segment_id=segment_id,
            status="scheduled" if scheduled_at else "draft",
            scheduled_at=scheduled_at,
        )
        self._campaigns[c.campaign_id] = c
        return c

    def get(self, campaign_id: str) -> Campaign | None:
        return self._campaigns.get(campaign_id)

    def list(self, status: str | None = None) -> list[Campaign]:
        camps = list(self._campaigns.values())
        if status:
            camps = [c for c in camps if c.status == status]
        return camps

    def update(self, campaign_id: str, **kwargs) -> Campaign | None:
        c = self._campaigns.get(campaign_id)
        if not c:
            return None
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def delete(self, campaign_id: str) -> bool:
        return bool(self._campaigns.pop(campaign_id, None))

    def send(self, campaign_id: str, recipient_count: int = 0) -> dict:
        c = self._campaigns.get(campaign_id)
        if not c:
            return {"success": False, "error": "campaign not found"}
        c.status = "sent"
        c.sent_count = recipient_count
        return {"success": True, "campaign_id": campaign_id, "sent_count": recipient_count}
