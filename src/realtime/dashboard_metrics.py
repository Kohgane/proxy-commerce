"""src/realtime/dashboard_metrics.py — 대시보드 메트릭."""
from __future__ import annotations

import random


class DashboardMetrics:
    """실시간 대시보드 메트릭 수집기 (모의 데이터)."""

    def collect(self) -> dict:
        """현재 대시보드 메트릭을 수집한다."""
        return {
            "orders": {
                "count": random.randint(100, 500),
                "pending": random.randint(5, 30),
                "processing": random.randint(10, 50),
            },
            "revenue": {
                "today": random.randint(500_000, 5_000_000),
                "week": random.randint(3_000_000, 20_000_000),
                "month": random.randint(15_000_000, 80_000_000),
            },
            "visitors": {
                "active": random.randint(50, 300),
                "today": random.randint(500, 3000),
            },
            "error_rate": round(random.uniform(0.001, 0.05), 4),
        }
