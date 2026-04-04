"""src/ai_pricing/pricing_models.py — AI 동적 가격 최적화 데이터 모델 (Phase 97)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class PricePoint:
    """가격 포인트 데이터 모델."""
    sku: str = ''
    base_price: float = 0.0
    optimized_price: float = 0.0
    margin: float = 0.0                   # 마진율 (0.0~1.0)
    competitor_avg: float = 0.0           # 경쟁사 평균가
    demand_score: float = 1.0             # 수요 지수 (1.0 = 기준)
    confidence: float = 0.0              # 최적화 신뢰도 (0.0~1.0)
    cost: float = 0.0                    # 원가
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CompetitorPrice:
    """경쟁사 가격 데이터."""
    competitor_id: str = ''              # amazon_us, amazon_jp, coupang, naver 등
    sku: str = ''
    price: float = 0.0
    currency: str = 'KRW'
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_url: str = ''
    is_available: bool = True


@dataclass
class DemandForecast:
    """수요 예측 결과."""
    sku: str = ''
    period: str = ''                      # '2024-01', '2024-W01' 등
    predicted_qty: float = 0.0
    confidence_interval_lower: float = 0.0
    confidence_interval_upper: float = 0.0
    seasonality_factor: float = 1.0       # 계절성 가중치
    trend_factor: float = 1.0             # 추세 가중치
    forecast_method: str = 'moving_avg'
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def confidence_interval(self) -> tuple:
        return (self.confidence_interval_lower, self.confidence_interval_upper)


@dataclass
class PricingDecision:
    """가격 결정 기록."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sku: str = ''
    old_price: float = 0.0
    new_price: float = 0.0
    reason: str = ''
    strategy: str = ''                    # ensemble, competitor_match, demand_surge 등
    approved: bool = False
    applied_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict = field(default_factory=dict)

    @property
    def price_change_pct(self) -> float:
        """가격 변동률 (%)."""
        if self.old_price == 0:
            return 0.0
        return round((self.new_price - self.old_price) / self.old_price * 100, 2)

    def apply(self) -> None:
        """가격 결정을 적용으로 표시한다."""
        self.approved = True
        self.applied_at = datetime.now(timezone.utc)


@dataclass
class PricingMetrics:
    """가격 최적화 전체 메트릭."""
    total_optimized: int = 0
    avg_price_change_pct: float = 0.0
    revenue_impact: float = 0.0           # 예상 매출 영향 (KRW)
    margin_impact: float = 0.0            # 예상 마진 영향
    skus_increased: int = 0
    skus_decreased: int = 0
    skus_unchanged: int = 0
    pending_approvals: int = 0
    last_run_at: Optional[datetime] = None
    category_breakdown: Dict = field(default_factory=dict)

    def recalculate(self, decisions: List[PricingDecision]) -> None:
        """결정 목록에서 메트릭을 재계산한다."""
        self.total_optimized = len(decisions)
        if not decisions:
            return
        changes = [d.price_change_pct for d in decisions]
        self.avg_price_change_pct = round(sum(changes) / len(changes), 2)
        self.skus_increased = sum(1 for c in changes if c > 0)
        self.skus_decreased = sum(1 for c in changes if c < 0)
        self.skus_unchanged = sum(1 for c in changes if c == 0)
        self.pending_approvals = sum(1 for d in decisions if not d.approved)
        self.last_run_at = datetime.now(timezone.utc)
