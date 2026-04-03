"""src/benchmark/load_profile.py — 부하 프로파일 정의."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class LoadProfile:
    """부하 프로파일 정의 (concurrent users, duration, ramp-up)."""

    name: str = "default"
    concurrent_users: int = 10
    duration_seconds: int = 30
    ramp_up_seconds: int = 5
    target_url: str = ""
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[dict] = None
    requests_per_second: Optional[float] = None  # None = as fast as possible

    def validate(self) -> None:
        if self.concurrent_users < 1:
            raise ValueError("concurrent_users는 1 이상이어야 합니다.")
        if self.duration_seconds < 1:
            raise ValueError("duration_seconds는 1 이상이어야 합니다.")
        if self.ramp_up_seconds < 0:
            raise ValueError("ramp_up_seconds는 0 이상이어야 합니다.")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "concurrent_users": self.concurrent_users,
            "duration_seconds": self.duration_seconds,
            "ramp_up_seconds": self.ramp_up_seconds,
            "target_url": self.target_url,
            "method": self.method,
            "requests_per_second": self.requests_per_second,
        }
