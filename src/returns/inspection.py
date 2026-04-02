"""src/returns/inspection.py — Phase 37: 반품 상품 검수 서비스."""
import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# 등급 기준 및 환불 비율
GRADE_CONFIG = {
    'A': {'label': '최상', 'refund_pct': 100, 'description': '포장 미개봉 또는 완전 정상'},
    'B': {'label': '양호', 'refund_pct': 90, 'description': '사용감 없음, 경미한 포장 손상'},
    'C': {'label': '보통', 'refund_pct': 70, 'description': '사용감 있음, 기능 정상'},
    'D': {'label': '불량', 'refund_pct': 0, 'description': '파손/훼손으로 재판매 불가'},
}


class InspectionService:
    """반품 상품 검수 서비스.

    검수 등급: A(100%) / B(90%) / C(70%) / D(0%)
    """

    def grade(
        self,
        condition_score: int,
        packaging_intact: bool = True,
        functional: bool = True,
    ) -> str:
        """조건 점수에 따라 등급 결정.

        Args:
            condition_score: 0-100 상태 점수
            packaging_intact: 포장 온전 여부
            functional: 기능 정상 여부

        Returns:
            등급 문자열 (A/B/C/D)
        """
        if not functional:
            return 'D'
        if condition_score >= 95 and packaging_intact:
            return 'A'
        if condition_score >= 80:
            return 'B'
        if condition_score >= 50:
            return 'C'
        return 'D'

    def get_refund_ratio(self, grade: str) -> Decimal:
        """등급별 환불 비율 반환."""
        pct = GRADE_CONFIG.get(grade.upper(), {}).get('refund_pct', 0)
        return Decimal(str(pct)) / Decimal('100')

    def inspect(
        self,
        return_id: str,
        condition_score: int,
        packaging_intact: bool = True,
        functional: bool = True,
        notes: str = '',
    ) -> dict:
        """검수 결과 생성."""
        grade = self.grade(condition_score, packaging_intact, functional)
        config = GRADE_CONFIG[grade]
        return {
            'return_id': return_id,
            'grade': grade,
            'label': config['label'],
            'refund_pct': config['refund_pct'],
            'description': config['description'],
            'condition_score': condition_score,
            'packaging_intact': packaging_intact,
            'functional': functional,
            'notes': notes,
        }

    def get_grade_info(self, grade: str) -> Optional[dict]:
        """등급 정보 반환."""
        return GRADE_CONFIG.get(grade.upper())
