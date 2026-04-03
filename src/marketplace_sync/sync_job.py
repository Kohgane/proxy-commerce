"""src/marketplace_sync/sync_job.py — 동기화 작업."""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SyncJob:
    marketplace: str
    job_type: str  # products, orders, inventory, prices
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = 'pending'
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    records_synced: int = 0
    records_failed: int = 0
    error_message: str = ''

    def start(self):
        self.status = 'running'
        self.started_at = datetime.datetime.now(tz=datetime.timezone.utc)

    def complete(self, synced: int = 0, failed: int = 0):
        self.status = 'completed'
        self.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        self.records_synced = synced
        self.records_failed = failed

    def fail(self, error: str):
        self.status = 'failed'
        self.completed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        self.error_message = error

    def to_dict(self) -> dict:
        return {
            'job_id': self.job_id,
            'marketplace': self.marketplace,
            'job_type': self.job_type,
            'status': self.status,
            'records_synced': self.records_synced,
            'records_failed': self.records_failed,
        }
