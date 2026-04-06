"""src/order_matching/sla_tracker.py — 이행 SLA 추적 (Phase 112).

FulfillmentSLATracker: 주문 이행 단계별 SLA 추적 + 초과 감지 + 알림
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 기본 SLA (시간)
DEFAULT_ORDER_TO_PURCHASE_HOURS = 4
DEFAULT_PURCHASE_TO_WAREHOUSE_HOURS = 72
DEFAULT_WAREHOUSE_TO_SHIP_HOURS = 24
DEFAULT_TOTAL_FULFILLMENT_HOURS = 100  # 4 + 72 + 24


class FulfillmentStage(str, Enum):
    order_received = 'order_received'
    source_matched = 'source_matched'
    purchase_initiated = 'purchase_initiated'
    purchase_confirmed = 'purchase_confirmed'
    warehouse_received = 'warehouse_received'
    quality_checked = 'quality_checked'
    shipped = 'shipped'
    delivered = 'delivered'


# 단계별 허용 시간 (시간 단위)
STAGE_SLA_HOURS: Dict[str, int] = {
    FulfillmentStage.order_received: 1,
    FulfillmentStage.source_matched: 1,
    FulfillmentStage.purchase_initiated: 4,
    FulfillmentStage.purchase_confirmed: 4,
    FulfillmentStage.warehouse_received: 72,
    FulfillmentStage.quality_checked: 4,
    FulfillmentStage.shipped: 24,
    FulfillmentStage.delivered: 48,
}


@dataclass
class SLAConfig:
    order_to_purchase_hours: int = DEFAULT_ORDER_TO_PURCHASE_HOURS
    purchase_to_warehouse_hours: int = DEFAULT_PURCHASE_TO_WAREHOUSE_HOURS
    warehouse_to_ship_hours: int = DEFAULT_WAREHOUSE_TO_SHIP_HOURS
    total_fulfillment_hours: int = DEFAULT_TOTAL_FULFILLMENT_HOURS


@dataclass
class SLAStatus:
    order_id: str
    stage: FulfillmentStage
    stage_started_at: str
    stage_deadline: str
    is_overdue: bool
    elapsed_hours: float
    remaining_hours: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _OrderTracking:
    order_id: str
    current_stage: FulfillmentStage
    started_at: str
    stage_started_at: str
    stage_deadline: str
    stage_history: List[dict] = field(default_factory=list)


class FulfillmentSLATracker:
    """이행 SLA 추적기."""

    def __init__(self, config: Optional[SLAConfig] = None) -> None:
        self._config = config or SLAConfig()
        # order_id → _OrderTracking
        self._tracking: Dict[str, _OrderTracking] = {}
        # SLA 초과 알림 이력
        self._overdue_notifications: List[dict] = []

    # ── 추적 시작 / 단계 업데이트 ─────────────────────────────────────────────

    def start_tracking(self, order_id: str) -> SLAStatus:
        """SLA 추적 시작 (order_received 단계)."""
        now = datetime.now(tz=timezone.utc)
        stage = FulfillmentStage.order_received
        deadline = now + timedelta(hours=STAGE_SLA_HOURS[stage])
        tracking = _OrderTracking(
            order_id=order_id,
            current_stage=stage,
            started_at=now.isoformat(),
            stage_started_at=now.isoformat(),
            stage_deadline=deadline.isoformat(),
        )
        self._tracking[order_id] = tracking
        logger.info("SLA 추적 시작: order_id=%s", order_id)
        return self._build_status(tracking, now)

    def update_stage(self, order_id: str, stage: FulfillmentStage) -> Optional[SLAStatus]:
        """단계 업데이트."""
        tracking = self._tracking.get(order_id)
        if tracking is None:
            logger.warning("SLA 추적 없음: order_id=%s", order_id)
            return None

        now = datetime.now(tz=timezone.utc)
        # 이전 단계 이력 저장
        tracking.stage_history.append({
            'stage': tracking.current_stage.value,
            'started_at': tracking.stage_started_at,
            'ended_at': now.isoformat(),
        })
        # 새 단계로 이동
        tracking.current_stage = stage
        tracking.stage_started_at = now.isoformat()
        deadline = now + timedelta(hours=STAGE_SLA_HOURS.get(stage, 24))
        tracking.stage_deadline = deadline.isoformat()
        logger.info("SLA 단계 업데이트: order_id=%s → %s", order_id, stage.value)
        return self._build_status(tracking, now)

    # ── 조회 ──────────────────────────────────────────────────────────────────

    def get_sla_status(self, order_id: str) -> Optional[SLAStatus]:
        """SLA 현황 조회."""
        tracking = self._tracking.get(order_id)
        if tracking is None:
            return None
        now = datetime.now(tz=timezone.utc)
        status = self._build_status(tracking, now)
        # 초과 감지 및 알림
        if status.is_overdue:
            self._maybe_notify_overdue(order_id, tracking.current_stage)
        return status

    def get_overdue_orders(self) -> List[SLAStatus]:
        """SLA 초과 주문 목록."""
        now = datetime.now(tz=timezone.utc)
        overdue = []
        for tracking in self._tracking.values():
            status = self._build_status(tracking, now)
            if status.is_overdue:
                overdue.append(status)
        return overdue

    def get_sla_performance(self) -> dict:
        """SLA 달성률 통계."""
        now = datetime.now(tz=timezone.utc)
        total = len(self._tracking)
        if total == 0:
            return {'total': 0, 'on_time': 0, 'overdue': 0, 'achievement_rate': 0.0}
        overdue_count = sum(
            1 for t in self._tracking.values()
            if self._build_status(t, now).is_overdue
        )
        on_time = total - overdue_count
        return {
            'total': total,
            'on_time': on_time,
            'overdue': overdue_count,
            'achievement_rate': round(on_time / total * 100, 1),
        }

    def get_stage_duration_stats(self) -> dict:
        """단계별 평균 소요시간 (완료된 단계 기준)."""
        durations: Dict[str, List[float]] = {}
        for tracking in self._tracking.values():
            for entry in tracking.stage_history:
                stage = entry['stage']
                started = datetime.fromisoformat(entry['started_at'])
                ended = datetime.fromisoformat(entry['ended_at'])
                hours = (ended - started).total_seconds() / 3600
                durations.setdefault(stage, []).append(hours)

        stats = {}
        for stage, dur_list in durations.items():
            stats[stage] = {
                'avg_hours': round(sum(dur_list) / len(dur_list), 2),
                'min_hours': round(min(dur_list), 2),
                'max_hours': round(max(dur_list), 2),
                'count': len(dur_list),
            }
        return stats

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _build_status(self, tracking: _OrderTracking, now: datetime) -> SLAStatus:
        stage_started = datetime.fromisoformat(tracking.stage_started_at)
        deadline = datetime.fromisoformat(tracking.stage_deadline)
        elapsed_hours = (now - stage_started).total_seconds() / 3600
        remaining_hours = (deadline - now).total_seconds() / 3600
        is_overdue = now > deadline
        return SLAStatus(
            order_id=tracking.order_id,
            stage=tracking.current_stage,
            stage_started_at=tracking.stage_started_at,
            stage_deadline=tracking.stage_deadline,
            is_overdue=is_overdue,
            elapsed_hours=round(elapsed_hours, 2),
            remaining_hours=round(remaining_hours, 2),
        )

    def _maybe_notify_overdue(self, order_id: str, stage: FulfillmentStage) -> None:
        """SLA 초과 알림 생성 (중복 방지)."""
        key = f"{order_id}:{stage.value}"
        if not any(n['key'] == key for n in self._overdue_notifications):
            self._overdue_notifications.append({
                'key': key,
                'order_id': order_id,
                'stage': stage.value,
                'message': f'SLA 초과: 주문 {order_id} 단계 {stage.value}',
                'notified_at': datetime.now(tz=timezone.utc).isoformat(),
            })
            logger.warning("SLA 초과 알림: order_id=%s, stage=%s", order_id, stage.value)

    def get_overdue_notifications(self) -> List[dict]:
        """SLA 초과 알림 이력."""
        return list(self._overdue_notifications)
