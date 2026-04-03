"""src/data_exchange/bulk_operation.py — 대량 작업 관리."""
from __future__ import annotations

import datetime
import uuid


class BulkOperation:
    """대량 작업 관리자."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}

    def start(self, operation_type: str, total_records: int) -> dict:
        """새 대량 작업을 시작한다."""
        job = {
            "job_id": str(uuid.uuid4()),
            "operation_type": operation_type,
            "total_records": total_records,
            "processed": 0,
            "status": "running",
            "started_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "completed_at": None,
        }
        self._jobs[job["job_id"]] = job
        return job

    def update_progress(self, job_id: str, processed: int) -> bool:
        """작업 진행 상황을 갱신한다."""
        if job_id not in self._jobs:
            return False
        job = self._jobs[job_id]
        job["processed"] = processed
        if processed >= job["total_records"]:
            job["status"] = "completed"
            job["completed_at"] = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        return True

    def get_status(self, job_id: str) -> dict:
        """작업 상태를 반환한다."""
        return self._jobs.get(job_id, {})

    def list_jobs(self) -> list:
        """모든 작업 목록을 반환한다."""
        return list(self._jobs.values())
