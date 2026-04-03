"""src/email_marketing/ — Phase 88: 자동 이메일 마케팅."""
from __future__ import annotations

from .models import Campaign
from .campaign_manager import CampaignManager
from .email_template_renderer import EmailTemplateRenderer
from .campaign_triggers import CampaignTrigger, ScheduleTrigger, EventTrigger, SegmentTrigger
from .campaign_analytics import CampaignAnalytics
from .unsubscribe_manager import UnsubscribeManager
from .ab_test_campaign import ABTestCampaign

__all__ = [
    "Campaign",
    "CampaignManager",
    "EmailTemplateRenderer",
    "CampaignTrigger",
    "ScheduleTrigger",
    "EventTrigger",
    "SegmentTrigger",
    "CampaignAnalytics",
    "UnsubscribeManager",
    "ABTestCampaign",
]
