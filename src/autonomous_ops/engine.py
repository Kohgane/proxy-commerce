"""src/autonomous_ops/engine.py — AutonomousOperationEngine 오케스트레이터 (Phase 106)."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class OperationMode(str, Enum):
    fully_auto = 'fully_auto'
    semi_auto = 'semi_auto'
    manual = 'manual'
    emergency = 'emergency'


@dataclass
class OperationStatus:
    mode: OperationMode
    health_score: float
    active_alerts: int
    auto_actions_count: int
    last_check: str
    uptime_seconds: float

    def to_dict(self) -> Dict:
        return {
            'mode': self.mode.value,
            'health_score': self.health_score,
            'active_alerts': self.active_alerts,
            'auto_actions_count': self.auto_actions_count,
            'last_check': self.last_check,
            'uptime_seconds': self.uptime_seconds,
        }


class AutonomousOperationEngine:
    """모니터링 → 이상 감지 → 자동 대응 → 알림 → 보고 오케스트레이션."""

    def __init__(self) -> None:
        self._mode: OperationMode = OperationMode.fully_auto
        self._health_score: float = 100.0
        self._active_alerts: List[str] = []
        self._auto_actions_count: int = 0
        self._start_time: float = time.monotonic()

    # ── 상태 조회 ─────────────────────────────────────────────────────────────

    def get_status(self) -> OperationStatus:
        return OperationStatus(
            mode=self._mode,
            health_score=self._health_score,
            active_alerts=len(self._active_alerts),
            auto_actions_count=self._auto_actions_count,
            last_check=datetime.now(timezone.utc).isoformat(),
            uptime_seconds=time.monotonic() - self._start_time,
        )

    def set_mode(self, mode: OperationMode) -> OperationStatus:
        self._mode = mode
        logger.info("운영 모드 변경: %s", mode.value)
        return self.get_status()

    # ── 헬스 체크 ─────────────────────────────────────────────────────────────

    def run_health_check(self) -> Dict:
        checks = {
            'operation_mode': self._mode.value,
            'active_alerts': len(self._active_alerts),
            'auto_actions': self._auto_actions_count,
            'uptime_seconds': time.monotonic() - self._start_time,
        }
        score = max(0.0, 100.0 - len(self._active_alerts) * 5.0)
        self._health_score = score
        checks['score'] = score
        logger.debug("헬스 체크 완료: score=%.1f", score)
        return checks

    # ── 알림 관리 ─────────────────────────────────────────────────────────────

    def record_alert(self, alert_id: str) -> None:
        if alert_id not in self._active_alerts:
            self._active_alerts.append(alert_id)
        logger.info("알림 등록: %s", alert_id)

    def acknowledge_alert(self, alert_id: str) -> bool:
        if alert_id in self._active_alerts:
            self._active_alerts.remove(alert_id)
            logger.info("알림 확인: %s", alert_id)
            return True
        return False

    def get_alerts(self) -> List[str]:
        return list(self._active_alerts)

    # ── 자동 액션 ─────────────────────────────────────────────────────────────

    def record_auto_action(self) -> None:
        self._auto_actions_count += 1

    # ── 자동 모드 전환 ────────────────────────────────────────────────────────

    def auto_switch_mode(self, health_score: float) -> OperationMode:
        if health_score >= 80:
            new_mode = OperationMode.fully_auto
        elif health_score >= 60:
            new_mode = OperationMode.semi_auto
        elif health_score >= 40:
            new_mode = OperationMode.manual
        else:
            new_mode = OperationMode.emergency
        self._mode = new_mode
        logger.info("자동 모드 전환: score=%.1f → %s", health_score, new_mode.value)
        return new_mode
