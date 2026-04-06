"""src/order_matching/risk_assessor.py — 주문 이행 리스크 평가 (Phase 112).

OrderRiskAssessor: 소싱처 안정성 / 가격변동 / 배송 / 재고 / 환율 / 시즌 리스크 종합 평가
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    low = 'low'        # 0~30
    medium = 'medium'  # 31~60
    high = 'high'      # 61~80
    critical = 'critical'  # 81~100


@dataclass
class RiskFactor:
    factor_type: str
    score: float
    description: str
    weight: float


@dataclass
class RiskAssessment:
    assessment_id: str
    order_id: str
    product_id: str
    overall_risk_score: float
    risk_level: RiskLevel
    risk_factors: List[RiskFactor]
    recommendations: List[str]
    assessed_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _score_to_level(score: float) -> RiskLevel:
    if score <= 30:
        return RiskLevel.low
    if score <= 60:
        return RiskLevel.medium
    if score <= 80:
        return RiskLevel.high
    return RiskLevel.critical


class OrderRiskAssessor:
    """주문 이행 리스크 평가기."""

    def __init__(self) -> None:
        # assessment_id → RiskAssessment
        self._assessments: Dict[str, RiskAssessment] = {}
        # order_id → list of RiskAssessment
        self._order_assessments: Dict[str, List[RiskAssessment]] = {}
        # source_id → source context dict
        self._source_context: Dict[str, dict] = {}
        # product_id → product context dict
        self._product_context: Dict[str, dict] = {}

    # ── 컨텍스트 등록 ─────────────────────────────────────────────────────────

    def register_source_context(self, source_id: str, context: dict) -> None:
        """소싱처 컨텍스트 등록 (최근 체크 실패율, 가격 변동성 등)."""
        self._source_context[source_id] = dict(context)

    def register_product_context(self, product_id: str, context: dict) -> None:
        """상품 컨텍스트 등록 (재고 상황, 시즌 여부 등)."""
        self._product_context[product_id] = dict(context)

    # ── 리스크 평가 ───────────────────────────────────────────────────────────

    def assess_order_risk(self, order_id: str) -> RiskAssessment:
        """주문 전체 리스크 평가 (첫 번째 상품 기준 또는 최고 리스크)."""
        assessments = self._order_assessments.get(order_id, [])
        if assessments:
            # 이미 평가된 경우 최고 리스크 반환
            return max(assessments, key=lambda a: a.overall_risk_score)

        # 미등록 주문이면 order_id를 product_id 로 평가
        return self.assess_product_risk(order_id, order_id=order_id)

    def assess_product_risk(
        self,
        product_id: str,
        source_id: Optional[str] = None,
        order_id: str = '',
    ) -> RiskAssessment:
        """상품 이행 리스크 평가."""
        source_ctx = self._source_context.get(source_id or '', {})
        product_ctx = self._product_context.get(product_id, {})

        factors: List[RiskFactor] = []
        recommendations: List[str] = []

        # 1. 소싱처 안정성 리스크
        check_fail_rate = float(source_ctx.get('check_fail_rate', 0.0))
        source_stability_score = min(check_fail_rate * 100, 100)
        factors.append(RiskFactor(
            factor_type='source_stability',
            score=source_stability_score,
            description=f'소싱처 체크 실패율 {check_fail_rate:.0%}',
            weight=0.25,
        ))
        if source_stability_score > 30:
            recommendations.append('소싱처 안정성 점검 필요')

        # 2. 가격 변동 리스크
        price_volatility = float(source_ctx.get('price_volatility', 0.0))
        price_risk_score = min(price_volatility * 200, 100)
        factors.append(RiskFactor(
            factor_type='price_volatility',
            score=price_risk_score,
            description=f'최근 가격 변동성 {price_volatility:.1%}',
            weight=0.20,
        ))
        if price_risk_score > 40:
            recommendations.append('가격 변동 모니터링 강화')

        # 3. 배송 리스크
        delivery_uncertainty = float(source_ctx.get('delivery_uncertainty', 0.1))
        shipping_risk_score = min(delivery_uncertainty * 200, 100)
        factors.append(RiskFactor(
            factor_type='shipping_risk',
            score=shipping_risk_score,
            description=f'배송 불확실성 {delivery_uncertainty:.1%}',
            weight=0.15,
        ))

        # 4. 재고 리스크
        stock = int(source_ctx.get('stock', 100))
        if stock == 0:
            stock_risk_score = 100.0
        elif stock < 5:
            stock_risk_score = 70.0
        elif stock < 20:
            stock_risk_score = 40.0
        else:
            stock_risk_score = 10.0
        factors.append(RiskFactor(
            factor_type='stock_risk',
            score=stock_risk_score,
            description=f'현재 재고 {stock}개',
            weight=0.20,
        ))
        if stock_risk_score > 50:
            recommendations.append('재고 부족 위험 — 대안 소싱처 확인')

        # 5. 환율 리스크
        is_foreign_currency = bool(source_ctx.get('is_foreign_currency', False))
        fx_volatility = float(source_ctx.get('fx_volatility', 0.0))
        fx_risk_score = (min(fx_volatility * 300, 100) if is_foreign_currency else 0.0)
        factors.append(RiskFactor(
            factor_type='fx_risk',
            score=fx_risk_score,
            description='외화 결제 환율 변동' if is_foreign_currency else '원화 결제',
            weight=0.10,
        ))

        # 6. 시즌/수요 리스크
        is_peak_season = bool(product_ctx.get('is_peak_season', False))
        demand_surge = float(product_ctx.get('demand_surge', 0.0))
        season_risk_score = min((50.0 if is_peak_season else 0.0) + demand_surge * 50, 100)
        factors.append(RiskFactor(
            factor_type='season_demand_risk',
            score=season_risk_score,
            description='성수기 수요 급증 위험' if is_peak_season else '비성수기',
            weight=0.10,
        ))
        if is_peak_season:
            recommendations.append('성수기 재고 사전 확보 권장')

        # 종합 점수 (가중 합산)
        overall_score = sum(f.score * f.weight for f in factors)
        overall_score = min(round(overall_score, 1), 100.0)
        risk_level = _score_to_level(overall_score)

        if not recommendations and risk_level == RiskLevel.low:
            recommendations.append('현재 이행 리스크 낮음')

        assessment = RiskAssessment(
            assessment_id=str(uuid.uuid4()),
            order_id=order_id,
            product_id=product_id,
            overall_risk_score=overall_score,
            risk_level=risk_level,
            risk_factors=factors,
            recommendations=recommendations,
            assessed_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._assessments[assessment.assessment_id] = assessment
        if order_id:
            self._order_assessments.setdefault(order_id, []).append(assessment)
        logger.info(
            "리스크 평가: product=%s, score=%.1f, level=%s",
            product_id, overall_score, risk_level.value,
        )
        return assessment

    # ── 조회 ──────────────────────────────────────────────────────────────────

    def get_high_risk_orders(self) -> List[RiskAssessment]:
        """고위험(high/critical) 주문 목록."""
        return [
            a for a in self._assessments.values()
            if a.risk_level in (RiskLevel.high, RiskLevel.critical)
        ]

    def get_risk_summary(self) -> dict:
        """리스크 현황 요약."""
        all_assessments = list(self._assessments.values())
        total = len(all_assessments)
        if total == 0:
            return {
                'total': 0,
                'low': 0, 'medium': 0, 'high': 0, 'critical': 0,
                'avg_score': 0.0,
                'high_risk_count': 0,
            }
        by_level: Dict[str, int] = {}
        scores = []
        for a in all_assessments:
            by_level[a.risk_level.value] = by_level.get(a.risk_level.value, 0) + 1
            scores.append(a.overall_risk_score)
        return {
            'total': total,
            'low': by_level.get('low', 0),
            'medium': by_level.get('medium', 0),
            'high': by_level.get('high', 0),
            'critical': by_level.get('critical', 0),
            'avg_score': round(sum(scores) / total, 1),
            'high_risk_count': by_level.get('high', 0) + by_level.get('critical', 0),
        }
