"""src/form_builder/form_submission.py — 폼 제출 데이터 저장 + 조회."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class FormSubmission:
    """폼 제출 데이터 저장 및 조회 (인메모리)."""

    def __init__(self) -> None:
        self._submissions: Dict[str, dict] = {}

    def submit(self, form_id: str, data: Dict[str, Any],
               submitter_id: Optional[str] = None) -> dict:
        """폼 제출 데이터 저장."""
        submission_id = str(uuid.uuid4())
        record = {
            "submission_id": submission_id,
            "form_id": form_id,
            "data": data,
            "submitter_id": submitter_id,
            "submitted_at": _now_iso(),
        }
        self._submissions[submission_id] = record
        return dict(record)

    def get(self, submission_id: str) -> Optional[dict]:
        s = self._submissions.get(submission_id)
        return dict(s) if s else None

    def list_by_form(self, form_id: str) -> List[dict]:
        return [dict(s) for s in self._submissions.values()
                if s["form_id"] == form_id]

    def list_all(self) -> List[dict]:
        return [dict(s) for s in self._submissions.values()]

    def delete(self, submission_id: str) -> None:
        if submission_id not in self._submissions:
            raise KeyError(f"제출 없음: {submission_id}")
        del self._submissions[submission_id]
