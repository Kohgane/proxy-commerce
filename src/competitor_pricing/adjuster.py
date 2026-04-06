"""src/competitor_pricing/adjuster.py — 자동 가격 조정 제안 (Phase 111)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from .tracker import CompetitorTracker
from .position_analyzer import PricePositionAnalyzer, PositionLabel

logger = logging.getLogger(__name__)

# 마진 안전 임계값: 이 이하로 마진이 떨어지면 제안을 거부한다
_LOSS_THRESHOLD = -0.05  # -5%
# 원가를 알 수 없을 때 사용하는 추정 원가 비율 (판매가의 80%)
_ESTIMATED_COST_RATIO = 0.80


class AdjustmentStrategy(str, Enum):
    match_lowest = 'match_lowest'
    beat_lowest = 'beat_lowest'
    match_average = 'match_average'
    maintain_margin = 'maintain_margin'
    dynamic = 'dynamic'


class SuggestionStatus(str, Enum):
    pending = 'pending'
    applied = 'applied'
    rejected = 'rejected'


@dataclass
class AdjustmentSuggestion:
    suggestion_id: str
    my_product_id: str
    current_price: float
    suggested_price: float
    strategy: AdjustmentStrategy
    reason: str
    estimated_margin: float
    estimated_margin_rate: float
    confidence: float
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    status: SuggestionStatus = SuggestionStatus.pending


class PriceAdjustmentSuggester:
    """가격 조정 제안 서비스."""

    def __init__(
        self,
        tracker: Optional[CompetitorTracker] = None,
        analyzer: Optional[PricePositionAnalyzer] = None,
    ) -> None:
        self._tracker = tracker or CompetitorTracker()
        self._analyzer = analyzer or PricePositionAnalyzer(self._tracker)
        self._suggestions: Dict[str, AdjustmentSuggestion] = {}
        self._auto_adjust_mode: bool = False

    @property
    def auto_adjust_mode(self) -> bool:
        return self._auto_adjust_mode

    @auto_adjust_mode.setter
    def auto_adjust_mode(self, value: bool) -> None:
        self._auto_adjust_mode = value

    # ── 제안 생성 ─────────────────────────────────────────────────────────────

    def suggest_adjustment(
        self,
        my_product_id: str,
        strategy: Optional[AdjustmentStrategy] = None,
        channel: Optional[str] = None,
    ) -> Optional[AdjustmentSuggestion]:
        """가격 조정 제안 생성."""
        position = self._analyzer.analyze_position(my_product_id, channel)
        current_price = position.my_price
        competitor_prices = position.competitor_prices

        if not competitor_prices:
            logger.info("경쟁사 없음, 가격 유지 제안: %s", my_product_id)
            strategy = AdjustmentStrategy.maintain_margin

        effective_strategy = strategy or AdjustmentStrategy.dynamic

        # dynamic: 포지션에 따라 최적 전략 선택
        if effective_strategy == AdjustmentStrategy.dynamic:
            effective_strategy = self._pick_strategy(position.position_label)

        min_price = min(competitor_prices) if competitor_prices else current_price
        avg_price = position.avg_price

        if effective_strategy == AdjustmentStrategy.match_lowest:
            suggested_price = min_price
            reason = f"최저가 경쟁사({min_price:,.0f}원)에 맞춤"
            confidence = 0.85

        elif effective_strategy == AdjustmentStrategy.beat_lowest:
            suggested_price = round(min_price * 0.99, 0)
            reason = f"최저가({min_price:,.0f}원) 대비 1% 언더컷"
            confidence = 0.90

        elif effective_strategy == AdjustmentStrategy.match_average:
            suggested_price = round(avg_price, 0)
            reason = f"경쟁사 평균가({avg_price:,.0f}원)에 맞춤"
            confidence = 0.75

        elif effective_strategy == AdjustmentStrategy.maintain_margin:
            suggested_price = current_price
            reason = "현재 가격 유지 (마진 보호)"
            confidence = 1.0

        else:
            suggested_price = round(avg_price, 0)
            reason = "동적 전략 기본값: 평균가 적용"
            confidence = 0.70

        # 마진 안전성 검사 (원가를 모를 경우 판매가의 _ESTIMATED_COST_RATIO를 원가로 가정)
        estimated_cost = suggested_price * _ESTIMATED_COST_RATIO
        estimated_margin = suggested_price - estimated_cost
        estimated_margin_rate = (estimated_margin / suggested_price) if suggested_price > 0 else 0.0

        if estimated_margin_rate < _LOSS_THRESHOLD:
            logger.warning(
                "마진 안전장치 발동: %s 제안가 %.0f → 예상 마진율 %.1f%%",
                my_product_id,
                suggested_price,
                estimated_margin_rate * 100,
            )
            suggestion = AdjustmentSuggestion(
                suggestion_id=str(uuid.uuid4()),
                my_product_id=my_product_id,
                current_price=current_price,
                suggested_price=suggested_price,
                strategy=effective_strategy,
                reason=f"[마진 안전장치] {reason} — 예상 마진율 {estimated_margin_rate*100:.1f}% (임계값 미달)",
                estimated_margin=estimated_margin,
                estimated_margin_rate=round(estimated_margin_rate * 100, 2),
                confidence=0.0,
                status=SuggestionStatus.rejected,
            )
            self._suggestions[suggestion.suggestion_id] = suggestion
            return suggestion

        suggestion = AdjustmentSuggestion(
            suggestion_id=str(uuid.uuid4()),
            my_product_id=my_product_id,
            current_price=current_price,
            suggested_price=suggested_price,
            strategy=effective_strategy,
            reason=reason,
            estimated_margin=round(estimated_margin, 2),
            estimated_margin_rate=round(estimated_margin_rate * 100, 2),
            confidence=confidence,
        )
        self._suggestions[suggestion.suggestion_id] = suggestion
        logger.info(
            "가격 조정 제안 생성: %s → %.0f (전략: %s)",
            my_product_id,
            suggested_price,
            effective_strategy.value,
        )
        return suggestion

    def suggest_bulk_adjustments(
        self,
        strategy: Optional[AdjustmentStrategy] = None,
        channel: Optional[str] = None,
    ) -> List[AdjustmentSuggestion]:
        """전체 상품 일괄 가격 조정 제안."""
        product_ids = list(
            {cp.product_id for cp in self._tracker.get_competitors() if cp.product_id}
        )
        suggestions = []
        for pid in product_ids:
            result = self.suggest_adjustment(pid, strategy, channel)
            if result:
                suggestions.append(result)
        return suggestions

    # ── 상태 변경 ─────────────────────────────────────────────────────────────

    def apply_suggestion(self, suggestion_id: str) -> bool:
        """제안 적용 (mock: ChannelSync 호출 시뮬레이션)."""
        suggestion = self._suggestions.get(suggestion_id)
        if not suggestion:
            return False
        if suggestion.status == SuggestionStatus.rejected:
            logger.warning("거부된 제안은 적용 불가: %s", suggestion_id)
            return False
        suggestion.status = SuggestionStatus.applied
        logger.info(
            "가격 조정 적용: %s → %.0f원",
            suggestion.my_product_id,
            suggestion.suggested_price,
        )
        # mock ChannelSync 호출
        return True

    def reject_suggestion(self, suggestion_id: str, reason: Optional[str] = None) -> bool:
        """제안 거부."""
        suggestion = self._suggestions.get(suggestion_id)
        if not suggestion:
            return False
        suggestion.status = SuggestionStatus.rejected
        if reason:
            suggestion.reason = f"{suggestion.reason} [거부: {reason}]"
        return True

    # ── 조회 ─────────────────────────────────────────────────────────────────

    def get_suggestions(
        self,
        status: Optional[SuggestionStatus] = None,
        strategy: Optional[AdjustmentStrategy] = None,
    ) -> List[AdjustmentSuggestion]:
        """제안 목록 반환 (필터링 가능)."""
        result = list(self._suggestions.values())
        if status:
            result = [s for s in result if s.status == status]
        if strategy:
            result = [s for s in result if s.strategy == strategy]
        return result

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    @staticmethod
    def _pick_strategy(label: PositionLabel) -> AdjustmentStrategy:
        """포지션 레이블에 따른 전략 선택."""
        mapping = {
            PositionLabel.most_expensive: AdjustmentStrategy.match_average,
            PositionLabel.above_average: AdjustmentStrategy.match_average,
            PositionLabel.average: AdjustmentStrategy.maintain_margin,
            PositionLabel.below_average: AdjustmentStrategy.maintain_margin,
            PositionLabel.cheapest: AdjustmentStrategy.maintain_margin,
        }
        return mapping.get(label, AdjustmentStrategy.maintain_margin)
