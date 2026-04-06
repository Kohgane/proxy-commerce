"""src/exception_handler/damage_handler.py — 상품 훼손 대응 (Phase 105)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DamageType(str, Enum):
    scratched = 'scratched'
    dented = 'dented'
    broken = 'broken'
    water_damage = 'water_damage'
    missing_parts = 'missing_parts'
    wrong_color = 'wrong_color'


class DamageGrade(str, Enum):
    A = 'A'  # 경미
    B = 'B'  # 보통
    C = 'C'  # 심각
    D = 'D'  # 파손


@dataclass
class DamageReport:
    report_id: str
    order_id: str
    damage_type: DamageType
    grade: DamageGrade
    photos: List[str] = field(default_factory=list)
    description: str = ''
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    response_action: Optional[str] = None
    compensation_amount: float = 0.0
    claim_sent: bool = False
    insurance_filed: bool = False

    def to_dict(self) -> Dict:
        return {
            'report_id': self.report_id,
            'order_id': self.order_id,
            'damage_type': self.damage_type.value,
            'grade': self.grade.value,
            'photos': self.photos,
            'description': self.description,
            'detected_at': self.detected_at,
            'response_action': self.response_action,
            'compensation_amount': self.compensation_amount,
            'claim_sent': self.claim_sent,
            'insurance_filed': self.insurance_filed,
        }


class DamageHandler:
    """상품 훼손 감지 및 자동 대응."""

    # 등급별 자동 대응 전략 설명
    _GRADE_STRATEGY = {
        DamageGrade.A: '할인 보상 제안 (5~10%)',
        DamageGrade.B: '부분 환불 + 재발송 선택',
        DamageGrade.C: '전액 환불 또는 재구매',
        DamageGrade.D: '즉시 전액 환불 + 셀러 클레임',
    }

    # 등급별 기본 보상 비율
    _COMPENSATION_RATE = {
        DamageGrade.A: 0.08,
        DamageGrade.B: 0.30,
        DamageGrade.C: 0.80,
        DamageGrade.D: 1.00,
    }

    def __init__(self) -> None:
        self._reports: Dict[str, DamageReport] = {}

    def report_damage(
        self,
        order_id: str,
        damage_type: DamageType,
        grade: DamageGrade,
        photos: Optional[List[str]] = None,
        description: str = '',
    ) -> DamageReport:
        report_id = f'dmg_{uuid.uuid4().hex[:10]}'
        report = DamageReport(
            report_id=report_id,
            order_id=order_id,
            damage_type=damage_type,
            grade=grade,
            photos=photos or [],
            description=description,
        )
        self._reports[report_id] = report
        logger.info("훼손 보고 생성: %s (order=%s, grade=%s)", report_id, order_id, grade.value)
        return report

    def determine_action(self, report_id: str, item_price: float = 0.0) -> Dict:
        """등급별 자동 대응 전략 결정."""
        report = self._get_or_raise(report_id)
        strategy = self._GRADE_STRATEGY[report.grade]
        comp_rate = self._COMPENSATION_RATE[report.grade]
        compensation = round(item_price * comp_rate, 2)

        report.response_action = strategy
        report.compensation_amount = compensation

        action = {
            'report_id': report_id,
            'grade': report.grade.value,
            'strategy': strategy,
            'compensation_amount': compensation,
            'compensation_rate': comp_rate,
            'send_claim': report.grade in (DamageGrade.C, DamageGrade.D),
            'file_insurance': report.grade == DamageGrade.D,
        }

        if action['send_claim']:
            self.send_seller_claim(report_id)
        if action['file_insurance']:
            self.file_insurance_claim(report_id)

        logger.info("훼손 대응 결정: %s → %s", report_id, strategy)
        return action

    def send_seller_claim(self, report_id: str) -> bool:
        """셀러 자동 클레임 발송 (mock)."""
        report = self._get_or_raise(report_id)
        report.claim_sent = True
        logger.info("셀러 클레임 발송 (mock): %s", report_id)
        return True

    def file_insurance_claim(self, report_id: str) -> bool:
        """보험 청구 자동화 (mock)."""
        report = self._get_or_raise(report_id)
        report.insurance_filed = True
        logger.info("보험 청구 (mock): %s", report_id)
        return True

    def get_report(self, report_id: str) -> Optional[DamageReport]:
        return self._reports.get(report_id)

    def list_reports(self, order_id: Optional[str] = None) -> List[DamageReport]:
        reports = list(self._reports.values())
        if order_id:
            reports = [r for r in reports if r.order_id == order_id]
        return reports

    def get_stats(self) -> Dict:
        reports = list(self._reports.values())
        by_grade: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for r in reports:
            by_grade[r.grade.value] = by_grade.get(r.grade.value, 0) + 1
            by_type[r.damage_type.value] = by_type.get(r.damage_type.value, 0) + 1
        return {
            'total': len(reports),
            'by_grade': by_grade,
            'by_type': by_type,
            'total_compensation': sum(r.compensation_amount for r in reports),
        }

    def _get_or_raise(self, report_id: str) -> DamageReport:
        report = self._reports.get(report_id)
        if report is None:
            raise KeyError(f'훼손 보고를 찾을 수 없습니다: {report_id}')
        return report
