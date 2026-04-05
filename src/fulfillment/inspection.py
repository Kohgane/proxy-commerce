"""src/fulfillment/inspection.py — 검수 서비스 (Phase 103)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class InspectionGrade(str, Enum):
    A = 'A'  # 100% 정상
    B = 'B'  # 경미한 스크래치
    C = 'C'  # 사용 가능하나 하자
    D = 'D'  # 불량


@dataclass
class InspectionResult:
    inspection_id: str
    order_id: str
    grade: InspectionGrade
    defect_types: List[str] = field(default_factory=list)
    photo_urls: List[str] = field(default_factory=list)
    comment: str = ''
    requires_return: bool = False
    inspected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InspectionService:
    """입고 상품 검수 서비스."""

    def __init__(self):
        self._history: List[InspectionResult] = []

    def inspect(self, order_id: str, items: List[Dict]) -> InspectionResult:
        """상품 검수를 수행한다."""
        inspection_id = f'insp_{uuid.uuid4().hex[:8]}'
        # mock: 기본적으로 grade A
        grade = InspectionGrade.A
        defect_types: List[str] = []
        comment = '검수 완료 — 이상 없음'

        # items에 defects가 있으면 grade 낮춤
        grade_order = list(InspectionGrade)
        for item in items:
            if item.get('defect_type'):
                defect_types.append(item['defect_type'])
            if item.get('grade'):
                try:
                    candidate = InspectionGrade(item['grade'])
                    if grade_order.index(candidate) > grade_order.index(grade):
                        grade = candidate
                except ValueError:
                    pass

        if defect_types:
            comment = f'불량 유형: {", ".join(defect_types)}'

        requires_return = grade == InspectionGrade.D

        result = InspectionResult(
            inspection_id=inspection_id,
            order_id=order_id,
            grade=grade,
            defect_types=defect_types,
            photo_urls=[f'https://photos.example.com/{inspection_id}_{i}.jpg' for i in range(1, 3)],
            comment=comment,
            requires_return=requires_return,
        )
        self._history.append(result)

        if requires_return:
            self._trigger_return(order_id, result)

        logger.info("검수 완료: %s, 등급: %s", order_id, grade.value)
        return result

    def get_history(self, order_id: Optional[str] = None) -> List[InspectionResult]:
        if order_id:
            return [r for r in self._history if r.order_id == order_id]
        return list(self._history)

    def _trigger_return(self, order_id: str, result: InspectionResult) -> None:
        logger.warning("Grade D 불량 감지 — 반품/교환 프로세스 트리거: %s", order_id)

    def get_stats(self) -> Dict:
        stats: Dict[str, int] = {g.value: 0 for g in InspectionGrade}
        for r in self._history:
            stats[r.grade.value] += 1
        return {
            'total': len(self._history),
            'by_grade': stats,
            'return_count': sum(1 for r in self._history if r.requires_return),
        }
