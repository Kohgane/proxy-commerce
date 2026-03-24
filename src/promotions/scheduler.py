"""src/promotions/scheduler.py — 프로모션 스케줄러.

프로모션 시작/종료 자동 처리, 만료 비활성화, 알림 발송.

환경변수:
  PROMOTIONS_ENABLED   — 프로모션 활성화 여부 (기본 "0")
  TELEGRAM_BOT_TOKEN   — 텔레그램 봇 토큰
  TELEGRAM_CHAT_ID     — 텔레그램 채팅 ID
"""

import datetime
import logging
import os
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_UPCOMING_HOURS = 24  # 곧 시작될 프로모션 알림 기준 (시간)


class PromotionScheduler:
    """프로모션 스케줄러."""

    def __init__(self, engine=None):
        self._engine = engine

    def _get_engine(self):
        """PromotionEngine 인스턴스를 반환한다."""
        if self._engine is not None:
            return self._engine
        from .engine import PromotionEngine
        return PromotionEngine()

    def is_enabled(self) -> bool:
        """프로모션 기능 활성화 여부를 반환한다."""
        return os.getenv("PROMOTIONS_ENABLED", "0") == "1"

    def run(self) -> Dict[str, Any]:
        """스케줄러를 실행한다.

        - 만료된 프로모션 자동 비활성화
        - 곧 시작될 프로모션 알림
        - 프로모션 성과 집계

        Returns:
            실행 결과 딕셔너리.
        """
        engine = self._get_engine()
        promotions = engine.get_promotions()
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        expired = self._deactivate_expired(engine, promotions, now)
        upcoming = self._notify_upcoming(promotions, now)

        return {
            "expired_count": len(expired),
            "upcoming_count": len(upcoming),
            "expired": expired,
            "upcoming": upcoming,
            "timestamp": now.isoformat(),
        }

    def aggregate_stats(self) -> List[Dict[str, Any]]:
        """모든 프로모션의 성과를 집계한다.

        Returns:
            [{promo_id, name, usage_count, total_discount_krw}, ...] 리스트.
        """
        engine = self._get_engine()
        promotions = engine.get_promotions()
        results = []
        for p in promotions:
            promo_id = str(p.get("promo_id", ""))
            if not promo_id:
                continue
            stats = engine.get_promo_stats(promo_id)
            if stats:
                results.append(stats)
        return results

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _deactivate_expired(
        self,
        engine,
        promotions: List[Dict[str, Any]],
        now: datetime.datetime,
    ) -> List[str]:
        """만료된 프로모션을 자동으로 비활성화한다."""
        expired_ids = []
        for p in promotions:
            if str(p.get("active", "0")) != "1":
                continue
            end_str = str(p.get("end_date", "")).strip()
            if not end_str:
                continue
            try:
                end = datetime.datetime.fromisoformat(end_str)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=datetime.timezone.utc)
                if now > end:
                    promo_id = str(p.get("promo_id", ""))
                    engine.update_promotion(promo_id, {"active": "0"})
                    expired_ids.append(promo_id)
                    logger.info("프로모션 만료 비활성화: promo_id=%s", promo_id)
            except (ValueError, TypeError):
                continue
        return expired_ids

    def _notify_upcoming(
        self,
        promotions: List[Dict[str, Any]],
        now: datetime.datetime,
    ) -> List[str]:
        """곧 시작될 프로모션(24시간 이내)에 대해 텔레그램 알림을 발송한다."""
        cutoff = now + datetime.timedelta(hours=_UPCOMING_HOURS)
        upcoming_ids = []
        upcoming_names = []

        for p in promotions:
            if str(p.get("active", "0")) != "1":
                continue
            start_str = str(p.get("start_date", "")).strip()
            if not start_str:
                continue
            try:
                start = datetime.datetime.fromisoformat(start_str)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=datetime.timezone.utc)
                if now <= start <= cutoff:
                    promo_id = str(p.get("promo_id", ""))
                    upcoming_ids.append(promo_id)
                    upcoming_names.append(str(p.get("name", promo_id)))
            except (ValueError, TypeError):
                continue

        if upcoming_names:
            self._send_upcoming_alert(upcoming_names)
        return upcoming_ids

    def _send_upcoming_alert(self, names: List[str]) -> None:
        """텔레그램으로 곧 시작될 프로모션 알림을 발송한다."""
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                return
            text = (
                f"🎯 *프로모션 시작 예정*\n\n"
                f"다음 {len(names)}개 프로모션이 24시간 내 시작됩니다:\n"
                + "\n".join(f"• {n}" for n in names)
            )
            import requests
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as exc:
            logger.warning("텔레그램 알림 실패: %s", exc)

    def check_and_activate(self) -> Tuple[List[str], List[str]]:
        """시작 시각이 된 비활성 프로모션을 활성화하고,
        만료된 프로모션을 비활성화한다.

        Returns:
            (activated_ids, deactivated_ids) 튜플.
        """
        engine = self._get_engine()
        promotions = engine.get_promotions()
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        activated = []
        deactivated = []

        for p in promotions:
            promo_id = str(p.get("promo_id", ""))
            is_active = str(p.get("active", "0")) == "1"
            start_str = str(p.get("start_date", "")).strip()
            end_str = str(p.get("end_date", "")).strip()

            try:
                if start_str and not is_active:
                    start = datetime.datetime.fromisoformat(start_str)
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=datetime.timezone.utc)
                    if now >= start:
                        engine.update_promotion(promo_id, {"active": "1"})
                        activated.append(promo_id)

                if end_str and is_active:
                    end = datetime.datetime.fromisoformat(end_str)
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=datetime.timezone.utc)
                    if now > end:
                        engine.update_promotion(promo_id, {"active": "0"})
                        deactivated.append(promo_id)
            except (ValueError, TypeError):
                continue

        return activated, deactivated
