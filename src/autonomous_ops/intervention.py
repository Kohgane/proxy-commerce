"""src/autonomous_ops/intervention.py — 사람 개입 최소화 (Phase 106)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class TaskPriority(str, Enum):
    low = 'low'
    medium = 'medium'
    high = 'high'
    critical = 'critical'


_PRIORITY_ORDER = {
    TaskPriority.critical: 0,
    TaskPriority.high: 1,
    TaskPriority.medium: 2,
    TaskPriority.low: 3,
}


@dataclass
class ManualTask:
    task_id: str
    description: str
    priority: TaskPriority
    reason: str
    created_at: str
    resolved_at: Optional[str] = None
    resolved: bool = False

    def to_dict(self) -> Dict:
        return {
            'task_id': self.task_id,
            'description': self.description,
            'priority': self.priority.value,
            'reason': self.reason,
            'created_at': self.created_at,
            'resolved_at': self.resolved_at,
            'resolved': self.resolved,
        }


@dataclass
class InterventionRecord:
    record_id: str
    reason: str
    task_id: str
    created_at: str

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'reason': self.reason,
            'task_id': self.task_id,
            'created_at': self.created_at,
        }


class InterventionTracker:
    """수동 개입 추적 및 자동화 커버리지 측정."""

    def __init__(self) -> None:
        self._records: List[InterventionRecord] = []
        self._total_tasks: int = 0
        self._auto_handled: int = 0

    def record_intervention(self, reason: str, task_id: str = '') -> InterventionRecord:
        record = InterventionRecord(
            record_id=f'int_{uuid.uuid4().hex[:10]}',
            reason=reason,
            task_id=task_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._records.append(record)
        self._total_tasks += 1
        return record

    def record_auto_handled(self) -> None:
        self._auto_handled += 1
        self._total_tasks += 1

    def get_automation_coverage(self) -> float:
        total = self._auto_handled + len(self._records)
        if total == 0:
            return 0.0
        return self._auto_handled / total

    def get_stats(self) -> Dict:
        return {
            'total_tasks': self._total_tasks,
            'auto_handled': self._auto_handled,
            'manual_interventions': len(self._records),
            'automation_coverage': self.get_automation_coverage(),
        }


class ManualTaskQueue:
    """수동 처리 필요 작업 큐."""

    def __init__(self) -> None:
        self._tasks: List[ManualTask] = []

    def add_task(self, description: str, priority: TaskPriority, reason: str) -> ManualTask:
        task = ManualTask(
            task_id=f'tsk_{uuid.uuid4().hex[:10]}',
            description=description,
            priority=priority,
            reason=reason,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._tasks.append(task)
        return task

    def resolve_task(self, task_id: str) -> bool:
        for task in self._tasks:
            if task.task_id == task_id and not task.resolved:
                task.resolved = True
                task.resolved_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def list_pending(self, limit: int = 20) -> List[Dict]:
        pending = [t for t in self._tasks if not t.resolved]
        sorted_tasks = sorted(pending, key=lambda t: _PRIORITY_ORDER.get(t.priority, 99))
        return [t.to_dict() for t in sorted_tasks[:limit]]

    def get_stats(self) -> Dict:
        total = len(self._tasks)
        resolved = sum(1 for t in self._tasks if t.resolved)
        by_priority: Dict[str, int] = {}
        for t in self._tasks:
            if not t.resolved:
                by_priority[t.priority.value] = by_priority.get(t.priority.value, 0) + 1
        return {
            'total': total,
            'resolved': resolved,
            'pending': total - resolved,
            'by_priority': by_priority,
        }


class AutomationCoverage:
    """자동화 커버리지 측정."""

    def calculate(self, auto_count: int, manual_count: int) -> Dict:
        total = auto_count + manual_count
        coverage_rate = auto_count / total if total else 0.0
        return {
            'coverage_rate': coverage_rate,
            'auto': auto_count,
            'manual': manual_count,
            'total': total,
            'target_reached': coverage_rate >= 0.95,
        }


class InterventionReport:
    """개입 사유 분석 및 개선 제안."""

    def generate(self, tracker: InterventionTracker, queue: ManualTaskQueue) -> Dict:
        tracker_stats = tracker.get_stats()
        queue_stats = queue.get_stats()
        coverage = tracker_stats['automation_coverage']
        suggestions = []
        if coverage < 0.95:
            suggestions.append('자동화율이 목표(95%) 미달입니다. 반복 패턴 자동화를 검토하세요.')
        if queue_stats['pending'] > 10:
            suggestions.append('수동 작업 대기열이 10개를 초과합니다. 우선순위 처리가 필요합니다.')
        critical_pending = queue_stats.get('by_priority', {}).get('critical', 0)
        if critical_pending:
            suggestions.append(f'긴급 수동 작업이 {critical_pending}건 대기 중입니다.')
        return {
            'tracker': tracker_stats,
            'queue': queue_stats,
            'automation_coverage': coverage,
            'target_coverage': 0.95,
            'target_reached': coverage >= 0.95,
            'improvement_suggestions': suggestions,
        }
