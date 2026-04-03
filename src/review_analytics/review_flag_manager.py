"""src/review_analytics/review_flag_manager.py — 리뷰 신고 관리자."""
from __future__ import annotations


class ReviewFlagManager:
    """리뷰 신고 관리자."""

    def __init__(self) -> None:
        self._flags: dict[str, dict] = {}

    def flag(self, review_id: str, flag_type: str, flagged_by: str) -> dict:
        """리뷰를 신고한다."""
        record = {
            'review_id': review_id,
            'flag_type': flag_type,
            'flagged_by': flagged_by,
            'status': 'pending',
        }
        self._flags[review_id] = record
        return record

    def list_flagged(self) -> list:
        """신고된 리뷰 목록을 반환한다."""
        return list(self._flags.values())

    def resolve(self, review_id: str, resolution: str) -> dict:
        """신고를 해결한다."""
        if review_id in self._flags:
            self._flags[review_id]['status'] = resolution
        return {'review_id': review_id, 'status': resolution}
