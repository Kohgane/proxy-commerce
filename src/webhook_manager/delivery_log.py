"""src/webhook_manager/delivery_log.py — 웹훅 전송 이력."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class DeliveryLog:
    """전송 이력 (성공/실패/재시도 횟수/응답코드)."""

    def __init__(self) -> None:
        # {webhook_id: [delivery_record, ...]}
        self._logs: Dict[str, List[dict]] = defaultdict(list)

    def record(self, webhook_id: str, event: str, status: str,
               response_code: int = 0, response_body: str = "",
               attempt: int = 1, error: str = "") -> dict:
        """전송 기록 저장."""
        record = {
            "delivery_id": str(uuid.uuid4()),
            "webhook_id": webhook_id,
            "event": event,
            "status": status,  # success / failed / retrying
            "response_code": response_code,
            "response_body": response_body[:500],
            "attempt": attempt,
            "error": error,
            "delivered_at": _now_iso(),
        }
        self._logs[webhook_id].append(record)
        return dict(record)

    def get_deliveries(self, webhook_id: str,
                       status: str = None, limit: int = 50) -> List[dict]:
        """특정 웹훅의 전송 이력 조회."""
        records = self._logs.get(webhook_id, [])
        if status:
            records = [r for r in records if r.get("status") == status]
        return [dict(r) for r in records[-limit:]]

    def get_all(self, limit: int = 100) -> List[dict]:
        """모든 전송 이력 조회 (최근 N개)."""
        all_records = []
        for records in self._logs.values():
            all_records.extend(records)
        all_records.sort(key=lambda r: r.get("delivered_at", ""))
        return [dict(r) for r in all_records[-limit:]]

    def get_stats(self, webhook_id: str) -> dict:
        """전송 통계."""
        records = self._logs.get(webhook_id, [])
        total = len(records)
        success = sum(1 for r in records if r.get("status") == "success")
        failed = sum(1 for r in records if r.get("status") == "failed")
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": round(success / total, 4) if total > 0 else 0.0,
        }
