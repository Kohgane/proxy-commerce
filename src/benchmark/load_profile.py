"""src/benchmark/load_profile.py — 부하 프로파일."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LoadProfile:
    """벤치마크 부하 프로파일."""

    def __init__(
        self,
        concurrent_users: int,
        duration_seconds: int,
        ramp_up_seconds: int,
        target_url: str,
        method: str = 'GET',
        body: Optional[dict] = None,
    ):
        self.concurrent_users = concurrent_users
        self.duration_seconds = duration_seconds
        self.ramp_up_seconds = ramp_up_seconds
        self.target_url = target_url
        self.method = method
        self.body = body

    def to_dict(self) -> dict:
        return {
            'concurrent_users': self.concurrent_users,
            'duration_seconds': self.duration_seconds,
            'ramp_up_seconds': self.ramp_up_seconds,
            'target_url': self.target_url,
            'method': self.method,
            'body': self.body,
        }
