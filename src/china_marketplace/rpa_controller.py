"""src/china_marketplace/rpa_controller.py — RPA 자동화 컨트롤러 mock (Phase 104)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RPATaskType(str, Enum):
    search_product = 'search_product'
    place_order = 'place_order'
    check_status = 'check_status'
    apply_coupon = 'apply_coupon'


class RPATaskStatus(str, Enum):
    pending = 'pending'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
    manual_required = 'manual_required'


@dataclass
class RPAStep:
    step_id: str
    action: str  # 'click' | 'type' | 'navigate' | 'screenshot' | 'wait'
    target: str  # CSS selector or URL
    value: str = ''
    screenshot_url: Optional[str] = None
    executed_at: Optional[str] = None
    success: bool = False

    def to_dict(self) -> Dict:
        return {
            'step_id': self.step_id,
            'action': self.action,
            'target': self.target,
            'value': self.value,
            'screenshot_url': self.screenshot_url,
            'executed_at': self.executed_at,
            'success': self.success,
        }


@dataclass
class RPATask:
    task_id: str
    task_type: RPATaskType
    status: RPATaskStatus = RPATaskStatus.pending
    steps: List[RPAStep] = field(default_factory=list)
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'task_id': self.task_id,
            'task_type': self.task_type.value,
            'status': self.status.value,
            'steps': [s.to_dict() for s in self.steps],
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'metadata': self.metadata,
        }


class RPAController:
    """브라우저 자동화 컨트롤러 mock."""

    def __init__(self):
        self._tasks: Dict[str, RPATask] = {}
        logger.info("RPAController 초기화 완료")

    def create_task(
        self,
        task_type: RPATaskType,
        metadata: Optional[Dict] = None,
    ) -> RPATask:
        task_id = f'rpa_{uuid.uuid4().hex[:10]}'
        task = RPATask(
            task_id=task_id,
            task_type=task_type,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        logger.info("RPA 작업 생성: %s (%s)", task_id, task_type.value)
        return task

    def execute_task(self, task_id: str) -> RPATask:
        """RPA 작업 실행 시뮬레이션 (mock)."""
        task = self._get_or_raise(task_id)
        task.status = RPATaskStatus.running
        task.started_at = datetime.now(timezone.utc).isoformat()

        steps = self._build_steps(task.task_type)
        task.steps = steps

        # 실패 시뮬레이션 (10% 확률)
        if random.random() < 0.1:
            task.status = RPATaskStatus.failed
            task.error = '페이지 로딩 타임아웃'
            task.completed_at = datetime.now(timezone.utc).isoformat()
            logger.warning("RPA 작업 실패: %s", task_id)
            return task

        # 캡챠 발생 시뮬레이션 (5% 확률)
        if random.random() < 0.05:
            task.status = RPATaskStatus.manual_required
            task.error = '캡챠 인증 필요 — 수동 처리 전환'
            task.completed_at = datetime.now(timezone.utc).isoformat()
            logger.warning("RPA 수동 전환 필요: %s", task_id)
            return task

        # 성공
        for step in task.steps:
            step.success = True
            step.executed_at = datetime.now(timezone.utc).isoformat()
            step.screenshot_url = f'https://screenshots.mock/{task_id}/{step.step_id}.png'

        task.status = RPATaskStatus.completed
        task.result = self._mock_result(task.task_type, task.metadata)
        task.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info("RPA 작업 완료: %s", task_id)
        return task

    def _build_steps(self, task_type: RPATaskType) -> List[RPAStep]:
        """작업 유형별 RPA 단계 생성."""
        step_defs: Dict[RPATaskType, List[Dict]] = {
            RPATaskType.search_product: [
                {'action': 'navigate', 'target': 'https://www.taobao.com'},
                {'action': 'type', 'target': '#q', 'value': '{keyword}'},
                {'action': 'click', 'target': '.btn-search'},
                {'action': 'screenshot', 'target': '#mainsrp-itemlist'},
            ],
            RPATaskType.place_order: [
                {'action': 'navigate', 'target': '{product_url}'},
                {'action': 'click', 'target': '.btn-add-to-cart'},
                {'action': 'click', 'target': '.go-to-checkout'},
                {'action': 'type', 'target': '#shipping-address', 'value': '{address}'},
                {'action': 'click', 'target': '.btn-confirm-order'},
                {'action': 'screenshot', 'target': '.order-success'},
            ],
            RPATaskType.check_status: [
                {'action': 'navigate', 'target': 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm'},
                {'action': 'screenshot', 'target': '.order-list'},
            ],
            RPATaskType.apply_coupon: [
                {'action': 'click', 'target': '.coupon-input'},
                {'action': 'type', 'target': '.coupon-input', 'value': '{coupon_code}'},
                {'action': 'click', 'target': '.btn-apply-coupon'},
                {'action': 'screenshot', 'target': '.coupon-result'},
            ],
        }
        defs = step_defs.get(task_type, [])
        return [
            RPAStep(
                step_id=f'step_{i + 1:03d}',
                action=d['action'],
                target=d['target'],
                value=d.get('value', ''),
            )
            for i, d in enumerate(defs)
        ]

    def _mock_result(self, task_type: RPATaskType, metadata: Dict) -> Dict:
        """작업 유형별 mock 결과."""
        if task_type == RPATaskType.search_product:
            return {'found': random.randint(50, 500), 'top_result': '타오바오 검색 결과'}
        if task_type == RPATaskType.place_order:
            return {'order_id': f'TB{uuid.uuid4().hex[:12].upper()}', 'status': '주문완료'}
        if task_type == RPATaskType.check_status:
            return {'status': '배송중', 'carrier': '순풍택배'}
        if task_type == RPATaskType.apply_coupon:
            return {'discount_cny': round(random.uniform(1, 30), 2), 'applied': True}
        return {}

    def get_task(self, task_id: str) -> Optional[RPATask]:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[RPATaskStatus] = None,
        task_type: Optional[RPATaskType] = None,
    ) -> List[RPATask]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        return tasks

    def get_history(self) -> List[Dict]:
        return [t.to_dict() for t in self._tasks.values()]

    def get_stats(self) -> Dict:
        tasks = list(self._tasks.values())
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for t in tasks:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
            by_type[t.task_type.value] = by_type.get(t.task_type.value, 0) + 1
        completed = by_status.get('completed', 0)
        total = len(tasks)
        return {
            'total': total,
            'by_status': by_status,
            'by_type': by_type,
            'success_rate': round(completed / total, 4) if total else 0.0,
        }

    def _get_or_raise(self, task_id: str) -> RPATask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f'RPA 작업을 찾을 수 없습니다: {task_id}')
        return task
