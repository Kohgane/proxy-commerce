"""src/autonomous_ops/autopilot.py — 자동 파일럿 컨트롤러 (Phase 106)."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .anomaly_detector import AnomalyAlert


class ActionStatus(str, Enum):
    pending = 'pending'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
    skipped = 'skipped'


@dataclass
class ActionRecord:
    action_id: str
    action_type: str
    trigger_alert_id: str
    status: ActionStatus
    started_at: str
    completed_at: Optional[str] = None
    result: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'action_id': self.action_id,
            'action_type': self.action_type,
            'trigger_alert_id': self.trigger_alert_id,
            'status': self.status.value,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'result': self.result,
            'metadata': self.metadata,
        }


class AutoAction(ABC):
    action_type: str = ''

    @abstractmethod
    def execute(self, alert: 'AnomalyAlert', context: Dict) -> Dict:
        ...


class PauseOrderingAction(AutoAction):
    action_type = 'pause_ordering'

    def execute(self, alert: 'AnomalyAlert', context: Dict) -> Dict:
        return {'paused': True, 'reason': f'이상 감지로 주문 중지: {alert.alert_id}'}


class AdjustPricingAction(AutoAction):
    action_type = 'adjust_pricing'

    def execute(self, alert: 'AnomalyAlert', context: Dict) -> Dict:
        return {'adjusted': True, 'adjustment_pct': -5.0}


class ScaleInventoryAction(AutoAction):
    action_type = 'scale_inventory'

    def execute(self, alert: 'AnomalyAlert', context: Dict) -> Dict:
        return {'scaled': True, 'scale_factor': 1.5}


class NotifyAdminAction(AutoAction):
    action_type = 'notify_admin'

    def execute(self, alert: 'AnomalyAlert', context: Dict) -> Dict:
        return {'notified': True, 'channels': ['telegram', 'email']}


class ActivateBackupAction(AutoAction):
    action_type = 'activate_backup'

    def execute(self, alert: 'AnomalyAlert', context: Dict) -> Dict:
        return {'backup_activated': True}


class AutoPilotController:
    """이상 감지 시 자동 대응 실행 및 이력 관리."""

    def __init__(self) -> None:
        self._actions: Dict[str, AutoAction] = {}
        self._history: List[ActionRecord] = []
        # 기본 액션 등록
        for action in [
            PauseOrderingAction(),
            AdjustPricingAction(),
            ScaleInventoryAction(),
            NotifyAdminAction(),
            ActivateBackupAction(),
        ]:
            self.register_action(action)

    def register_action(self, action: AutoAction) -> None:
        self._actions[action.action_type] = action

    def respond_to_alert(self, alert: 'AnomalyAlert', context: Optional[Dict] = None) -> ActionRecord:
        if context is None:
            context = {}
        action = self._choose_action(alert)
        now = datetime.now(timezone.utc).isoformat()
        record = ActionRecord(
            action_id=f'act_{uuid.uuid4().hex[:10]}',
            action_type=action.action_type if action else 'notify_admin',
            trigger_alert_id=alert.alert_id,
            status=ActionStatus.running,
            started_at=now,
        )
        try:
            chosen = action or self._actions.get('notify_admin')
            if chosen:
                result = chosen.execute(alert, context)
                record.result = result
                record.status = ActionStatus.completed
            else:
                record.status = ActionStatus.skipped
                record.result = {'skipped': True}
        except Exception as exc:
            record.status = ActionStatus.failed
            record.result = {'error': str(exc)}
        record.completed_at = datetime.now(timezone.utc).isoformat()
        self._history.append(record)
        return record

    def get_history(self, limit: int = 50) -> List[Dict]:
        return [r.to_dict() for r in self._history[-limit:]]

    def get_stats(self) -> Dict:
        total = len(self._history)
        by_status: Dict[str, int] = {}
        for r in self._history:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        completed = by_status.get('completed', 0)
        success_rate = completed / total if total else 0.0
        return {'total': total, 'by_status': by_status, 'success_rate': success_rate}

    def _choose_action(self, alert: 'AnomalyAlert') -> Optional[AutoAction]:
        from .anomaly_detector import AnomalyType
        mapping = {
            AnomalyType.revenue_drop: 'adjust_pricing',
            AnomalyType.cost_spike: 'pause_ordering',
            AnomalyType.order_surge: 'scale_inventory',
            AnomalyType.order_drought: 'adjust_pricing',
            AnomalyType.conversion_drop: 'adjust_pricing',
            AnomalyType.refund_spike: 'pause_ordering',
            AnomalyType.delivery_delay_spike: 'notify_admin',
            AnomalyType.seller_issue: 'activate_backup',
            AnomalyType.system_error: 'notify_admin',
        }
        action_type = mapping.get(alert.type)
        if action_type:
            return self._actions.get(action_type)
        return self._actions.get('notify_admin')
