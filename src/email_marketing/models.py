"""이메일 캠페인 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Campaign:
    campaign_id: str
    name: str
    subject: str
    body_template: str
    segment_id: str = ""
    status: str = "draft"  # draft/scheduled/sending/sent/paused
    scheduled_at: str = ""
    sent_count: int = 0
    open_count: int = 0
    click_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
