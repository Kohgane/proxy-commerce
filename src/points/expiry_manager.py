"""src/points/expiry_manager.py — 포인트 만료 관리자 (Phase 92).

포인트 유효기간(365일) 만료 처리 및 만료 예정 알림을 관리한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .point_history import HistoryType, PointHistory

logger = logging.getLogger(__name__)


class ExpiryManager:
    """포인트 만료 관리자.

    만료 예정 포인트 조회(7일/30일), 배치 만료 처리, 만료 알림 생성을 담당한다.
    """

    def __init__(self, point_manager=None, history: Optional[PointHistory] = None) -> None:
        self._pm = point_manager
        self._history = history
        self._notifications: List[dict] = []

    def _get_pm(self):
        """PointManager 인스턴스를 반환한다 (지연 초기화 지원)."""
        if self._pm is None:
            from .point_manager import PointManager
            self._pm = PointManager()
        return self._pm

    def get_expiring_lots(self, user_id: str, within_days: int = 30) -> List[dict]:
        """만료 예정 적립 배치를 반환한다.

        Args:
            user_id: 사용자 ID
            within_days: 앞으로 N일 이내 만료되는 배치

        Returns:
            만료 예정 배치 목록 (남은 포인트가 있는 것만)
        """
        pm = self._get_pm()
        now = datetime.now(timezone.utc)
        deadline = (now + timedelta(days=within_days)).isoformat()
        result = []
        for lot in pm.get_lots_for_user(user_id):
            if lot.remaining > 0 and not lot.is_expired(now) and lot.expires_at <= deadline:
                days_left = (
                    datetime.fromisoformat(lot.expires_at) - now
                ).days
                result.append({**lot.to_dict(), "days_until_expiry": days_left})
        return result

    def run_expiry_batch(self, now: Optional[datetime] = None) -> Dict:
        """만료된 포인트 배치 처리를 실행한다.

        Returns:
            {"expired_lots": int, "expired_points": int, "affected_users": list}
        """
        pm = self._get_pm()
        history = self._history or pm.history
        _now = now or datetime.now(timezone.utc)
        expired_lots = 0
        expired_points = 0
        affected_users: List[str] = []

        for lot in pm._lots:
            if lot.remaining > 0 and lot.is_expired(_now):
                amount = lot.remaining
                lot.remaining = 0
                user_id = lot.user_id
                pm._balances[user_id] = max(0, pm._balances.get(user_id, 0) - amount)
                history.record(
                    user_id=user_id,
                    history_type=HistoryType.EXPIRE,
                    amount=amount,
                    balance_after=pm._balances[user_id],
                    reason=f"포인트 만료 (lot_id={lot.lot_id})",
                    order_id=lot.order_id,
                )
                notification = {
                    "user_id": user_id,
                    "lot_id": lot.lot_id,
                    "expired_points": amount,
                    "expired_at": _now.isoformat(),
                }
                self._notifications.append(notification)
                expired_lots += 1
                expired_points += amount
                if user_id not in affected_users:
                    affected_users.append(user_id)

        logger.info(
            "포인트 만료 배치 완료: lots=%d points=%d users=%d",
            expired_lots,
            expired_points,
            len(affected_users),
        )
        return {
            "expired_lots": expired_lots,
            "expired_points": expired_points,
            "affected_users": affected_users,
        }

    def get_notifications(self) -> List[dict]:
        """생성된 만료 알림 목록을 반환한다."""
        return list(self._notifications)
