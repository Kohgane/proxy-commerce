"""캠페인 분석."""
from __future__ import annotations
from .models import Campaign

class CampaignAnalytics:
    def stats(self, campaign: Campaign) -> dict:
        open_rate = (campaign.open_count / campaign.sent_count) if campaign.sent_count > 0 else 0
        click_rate = (campaign.click_count / campaign.sent_count) if campaign.sent_count > 0 else 0
        return {
            "campaign_id": campaign.campaign_id,
            "sent_count": campaign.sent_count,
            "open_count": campaign.open_count,
            "click_count": campaign.click_count,
            "open_rate": round(open_rate, 4),
            "click_rate": round(click_rate, 4),
        }

    def record_open(self, campaign: Campaign) -> None:
        campaign.open_count += 1

    def record_click(self, campaign: Campaign) -> None:
        campaign.click_count += 1
