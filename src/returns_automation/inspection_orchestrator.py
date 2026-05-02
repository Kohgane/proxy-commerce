"""src/returns_automation/inspection_orchestrator.py — Phase 118: 검수 자동화 오케스트레이터.

Phase 37 InspectionService 위임 + 사진/패키지 상태 기반 A~D 등급 자동 추정.
검수 완료 시 refund_orchestrator 또는 exchange_orchestrator로 라우팅.
"""
from __future__ import annotations

import logging
from typing import Optional

from .models import AutoReturnRequest

logger = logging.getLogger(__name__)

# 등급 추정 규칙 (heuristic)
# 패키지 손상 없음 + weight_diff 5% 이내 → A 등급
# 패키지 손상 없음 + weight_diff 5~15% → B 등급
# 패키지 손상 있음 → C 등급
# 사진에 명백한 파손/결함 → D 등급
GRADE_A_WEIGHT_DIFF_PCT = 5.0
GRADE_B_WEIGHT_DIFF_PCT = 15.0


class InspectionOrchestrator:
    """검수 자동화 오케스트레이터.

    auto_grade()로 등급 자동 추정 후 Phase 37 InspectionService로 위임.
    """

    def __init__(self) -> None:
        # Phase 37 InspectionService 지연 초기화
        self._inspection_service = None

    def _get_service(self):
        """Phase 37 InspectionService 지연 초기화."""
        if self._inspection_service is None:
            try:
                from ..returns.inspection import InspectionService
                self._inspection_service = InspectionService()
            except Exception as exc:
                logger.warning("[검수] InspectionService 로드 실패 (fallback 사용): %s", exc)
        return self._inspection_service

    def auto_grade(
        self,
        request: AutoReturnRequest,
        photos: Optional[list] = None,
        weight_diff_pct: float = 0.0,
        package_intact: bool = True,
    ) -> str:
        """사진/패키지 상태/중량차이 기반 검수 등급 자동 추정 (heuristic mock).

        Args:
            request: 반품 요청 객체
            photos: 검수 사진 URL 목록
            weight_diff_pct: 원래 중량 대비 차이 퍼센트 (0~100)
            package_intact: 외부 포장 손상 없음 여부

        Returns:
            검수 등급 문자열 ('A'/'B'/'C'/'D')
        """
        photos = photos or request.photos

        # D 등급: 사진에 명백한 파손/결함 키워드 또는 파손 신고
        from .models import ReturnReasonCategory
        reason = request.reason_code
        if isinstance(reason, str):
            try:
                reason = ReturnReasonCategory(reason)
            except ValueError:
                pass
        if reason == ReturnReasonCategory.damaged_in_transit and not package_intact:
            logger.info("[검수] %s → 등급 D (배송 파손 + 포장 손상)", request.request_id)
            return 'D'

        # C 등급: 포장 손상
        if not package_intact:
            logger.info("[검수] %s → 등급 C (포장 손상)", request.request_id)
            return 'C'

        # A/B 등급: 중량 차이 기준
        if weight_diff_pct <= GRADE_A_WEIGHT_DIFF_PCT:
            logger.info("[검수] %s → 등급 A (중량차이 %.1f%%)", request.request_id, weight_diff_pct)
            return 'A'

        if weight_diff_pct <= GRADE_B_WEIGHT_DIFF_PCT:
            logger.info("[검수] %s → 등급 B (중량차이 %.1f%%)", request.request_id, weight_diff_pct)
            return 'B'

        logger.info("[검수] %s → 등급 C (중량차이 %.1f%% 초과)", request.request_id, weight_diff_pct)
        return 'C'

    def inspect(
        self,
        request: AutoReturnRequest,
        condition_score: int = 90,
        package_intact: bool = True,
        functional: bool = True,
        photos: Optional[list] = None,
        weight_diff_pct: float = 0.0,
        notes: str = '',
    ) -> dict:
        """검수를 수행하고 결과를 반환한다.

        Phase 37 InspectionService 위임 시도 후 fallback.

        Returns:
            검수 결과 dict (grade, refund_pct, description 등)
        """
        # 자동 등급 추정
        auto_grade = self.auto_grade(request, photos, weight_diff_pct, package_intact)

        # condition_score를 auto_grade 기반으로 보정
        grade_score_map = {'A': 95, 'B': 80, 'C': 60, 'D': 0}
        effective_score = grade_score_map.get(auto_grade, condition_score)

        # Phase 37 InspectionService 위임
        service = self._get_service()
        if service:
            try:
                result = service.inspect(
                    request.request_id,
                    effective_score,
                    package_intact,
                    functional,
                    notes,
                )
                result['auto_grade'] = auto_grade
                logger.info("[검수] %s 완료: 등급 %s", request.request_id, result.get('grade'))
                return result
            except Exception as exc:
                logger.warning("[검수] InspectionService 위임 실패 (fallback): %s", exc)

        # Fallback: 직접 등급 계산
        grade_config = {
            'A': {'label': '최상', 'refund_pct': 100, 'description': '새 상품과 동일'},
            'B': {'label': '양호', 'refund_pct': 90, 'description': '사용 흔적 미미'},
            'C': {'label': '보통', 'refund_pct': 70, 'description': '사용 흔적 있음'},
            'D': {'label': '불량', 'refund_pct': 0, 'description': '심각한 손상'},
        }
        cfg = grade_config.get(auto_grade, grade_config['C'])
        return {
            'return_id': request.request_id,
            'grade': auto_grade,
            'auto_grade': auto_grade,
            'label': cfg['label'],
            'refund_pct': cfg['refund_pct'],
            'description': cfg['description'],
            'condition_score': effective_score,
            'packaging_intact': package_intact,
            'functional': functional,
            'notes': notes,
        }
