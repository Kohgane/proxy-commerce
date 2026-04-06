"""src/seller_report/hybrid_model_advisor.py — HybridModelAdvisor (Phase 114)."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SourcingModel(str, Enum):
    pure_dropship = 'pure_dropship'   # 순수 구매대행
    semi_stock = 'semi_stock'         # 소량 사입
    full_stock = 'full_stock'         # 대량 사입
    hybrid = 'hybrid'                 # 혼합


@dataclass
class ProductSourcingRecommendation:
    product_id: str
    name: str
    current_model: SourcingModel
    recommended_model: SourcingModel
    reason: str
    monthly_sales: int
    monthly_revenue: float
    avg_margin: float
    estimated_savings: float
    estimated_delivery_improvement: float  # days reduction
    confidence_score: float
    recommended_stock_qty: int
    estimated_investment: float


class HybridModelAdvisor:
    """무재고→사입 전환 자동 추천 (하이브리드 모델)."""

    # 전환 기준
    A_GRADE_THRESHOLD = 50   # 월 50개 이상 → full_stock
    B_GRADE_MIN = 10         # 월 10~50개 → semi_stock
    # 월 10개 미만 → pure_dropship 유지

    CURRENT_DELIVERY_DAYS = 12.0   # 구매대행 평균 배송일
    FULL_STOCK_DELIVERY_DAYS = 1.0  # 사입 후 배송일
    SEMI_STOCK_DELIVERY_DAYS = 3.0  # 소량 사입 배송일

    def __init__(self) -> None:
        self._products = self._generate_sample_products()

    def _generate_sample_products(self) -> List[Dict[str, Any]]:
        products = []
        for i in range(1, 201):
            monthly_sales = random.randint(1, 120)
            unit_price = random.uniform(10_000, 200_000)
            margin = random.uniform(10, 35)
            products.append({
                'product_id': f'PROD_{i:04d}',
                'name': f'상품 {i:04d}',
                'monthly_sales': monthly_sales,
                'monthly_revenue': round(monthly_sales * unit_price),
                'avg_margin': round(margin, 2),
                'unit_price': round(unit_price),
                'current_model': SourcingModel.pure_dropship,
            })
        return products

    def _recommend_model(self, monthly_sales: int) -> SourcingModel:
        if monthly_sales >= self.A_GRADE_THRESHOLD:
            return SourcingModel.full_stock
        elif monthly_sales >= self.B_GRADE_MIN:
            return SourcingModel.semi_stock
        else:
            return SourcingModel.pure_dropship

    def _build_recommendation(self, p: Dict[str, Any]) -> ProductSourcingRecommendation:
        monthly_sales = p['monthly_sales']
        recommended = self._recommend_model(monthly_sales)
        current = p['current_model']

        # 배송 개선
        if recommended == SourcingModel.full_stock:
            delivery_improvement = self.CURRENT_DELIVERY_DAYS - self.FULL_STOCK_DELIVERY_DAYS
            stock_qty = monthly_sales * 2
            investment = stock_qty * p['unit_price'] * (1 - p['avg_margin'] / 100)
            reason = f"월 {monthly_sales}개 판매 (A급) — 사입 전환 시 당일/익일 배송 가능"
            savings = monthly_sales * p['unit_price'] * 0.05  # 5% 비용 절감 추정
        elif recommended == SourcingModel.semi_stock:
            delivery_improvement = self.CURRENT_DELIVERY_DAYS - self.SEMI_STOCK_DELIVERY_DAYS
            stock_qty = monthly_sales
            investment = stock_qty * p['unit_price'] * (1 - p['avg_margin'] / 100)
            reason = f"월 {monthly_sales}개 판매 (B급) — 소량 사입 + 무재고 병행 추천"
            savings = monthly_sales * p['unit_price'] * 0.02
        else:
            delivery_improvement = 0.0
            stock_qty = 0
            investment = 0.0
            reason = f"월 {monthly_sales}개 판매 (C급) — 현재 무재고 모델 유지"
            savings = 0.0

        # 신뢰도 (판매량 기반)
        confidence = min(0.95, 0.5 + monthly_sales / 200)

        return ProductSourcingRecommendation(
            product_id=p['product_id'],
            name=p['name'],
            current_model=current,
            recommended_model=recommended,
            reason=reason,
            monthly_sales=monthly_sales,
            monthly_revenue=p['monthly_revenue'],
            avg_margin=p['avg_margin'],
            estimated_savings=round(savings),
            estimated_delivery_improvement=round(delivery_improvement, 1),
            confidence_score=round(confidence, 2),
            recommended_stock_qty=stock_qty,
            estimated_investment=round(investment),
        )

    def analyze_all_products(self) -> List[ProductSourcingRecommendation]:
        """전체 상품 전환 분석."""
        return [self._build_recommendation(p) for p in self._products]

    def get_stock_recommendations(self) -> List[ProductSourcingRecommendation]:
        """사입 전환 추천 목록 (pure_dropship 제외)."""
        all_recs = self.analyze_all_products()
        return [
            r for r in all_recs
            if r.recommended_model != SourcingModel.pure_dropship
        ]

    def get_investment_estimate(self) -> Dict[str, Any]:
        """사입 전환 시 필요 투자금 추정."""
        recs = self.get_stock_recommendations()
        full_stock_recs = [r for r in recs if r.recommended_model == SourcingModel.full_stock]
        semi_stock_recs = [r for r in recs if r.recommended_model == SourcingModel.semi_stock]

        total_investment = sum(r.estimated_investment for r in recs)
        full_investment = sum(r.estimated_investment for r in full_stock_recs)
        semi_investment = sum(r.estimated_investment for r in semi_stock_recs)
        total_savings = sum(r.estimated_savings for r in recs)

        return {
            'total_products_to_convert': len(recs),
            'full_stock_count': len(full_stock_recs),
            'semi_stock_count': len(semi_stock_recs),
            'total_investment': round(total_investment),
            'full_stock_investment': round(full_investment),
            'semi_stock_investment': round(semi_investment),
            'estimated_monthly_savings': round(total_savings),
            'payback_months': round(total_investment / total_savings, 1) if total_savings > 0 else None,
        }

    def get_delivery_improvement_estimate(self) -> Dict[str, Any]:
        """배송 속도 개선 예측."""
        recs = self.get_stock_recommendations()
        if not recs:
            return {'avg_before': self.CURRENT_DELIVERY_DAYS, 'avg_after': self.CURRENT_DELIVERY_DAYS, 'improvement': 0.0}

        avg_improvement = sum(r.estimated_delivery_improvement for r in recs) / len(recs)
        avg_after = self.CURRENT_DELIVERY_DAYS - avg_improvement

        return {
            'avg_delivery_before_days': self.CURRENT_DELIVERY_DAYS,
            'avg_delivery_after_days': round(avg_after, 1),
            'avg_improvement_days': round(avg_improvement, 1),
            'affected_products': len(recs),
            'full_stock_delivery_days': self.FULL_STOCK_DELIVERY_DAYS,
            'semi_stock_delivery_days': self.SEMI_STOCK_DELIVERY_DAYS,
        }

    def get_hybrid_summary(self) -> Dict[str, Any]:
        """하이브리드 전환 요약."""
        all_products = self._products
        recs = self.get_stock_recommendations()
        investment_info = self.get_investment_estimate()
        delivery_info = self.get_delivery_improvement_estimate()

        total_revenue = sum(p['monthly_revenue'] for p in all_products)
        convert_revenue = sum(r.monthly_revenue for r in recs)
        revenue_increase_pct = round(convert_revenue / total_revenue * 20, 1) if total_revenue > 0 else 0.0

        return {
            'total_products': len(all_products),
            'convert_count': len(recs),
            'full_stock_count': investment_info['full_stock_count'],
            'semi_stock_count': investment_info['semi_stock_count'],
            'total_investment': investment_info['total_investment'],
            'delivery_before_days': delivery_info['avg_delivery_before_days'],
            'delivery_after_days': delivery_info['avg_delivery_after_days'],
            'estimated_revenue_increase_pct': revenue_increase_pct,
            'monthly_savings': investment_info['estimated_monthly_savings'],
            'summary_text': (
                f"전체 {len(all_products)}개 상품 중 {len(recs)}개 사입 전환 시: "
                f"투자금 {investment_info['total_investment']:,}원, "
                f"배송 속도 평균 {delivery_info['avg_delivery_before_days']}일"
                f"→{delivery_info['avg_delivery_after_days']}일, "
                f"예상 매출 증가 {revenue_increase_pct}%"
            ),
        }

    def simulate_model_change(self, product_id: str, new_model: str) -> Dict[str, Any]:
        """모델 변경 시뮬레이션."""
        product = None
        for p in self._products:
            if p['product_id'] == product_id:
                product = p
                break

        if product is None:
            return {'error': f'상품 {product_id}를 찾을 수 없습니다.'}

        try:
            model = SourcingModel(new_model)
        except ValueError:
            return {'error': f'유효하지 않은 모델: {new_model}'}

        old_model = product['current_model']
        monthly_sales = product['monthly_sales']
        unit_price = product['unit_price']

        # 배송 일수
        delivery_map = {
            SourcingModel.pure_dropship: self.CURRENT_DELIVERY_DAYS,
            SourcingModel.semi_stock: self.SEMI_STOCK_DELIVERY_DAYS,
            SourcingModel.full_stock: self.FULL_STOCK_DELIVERY_DAYS,
            SourcingModel.hybrid: self.SEMI_STOCK_DELIVERY_DAYS,
        }

        old_delivery = delivery_map.get(old_model, self.CURRENT_DELIVERY_DAYS)
        new_delivery = delivery_map.get(model, self.CURRENT_DELIVERY_DAYS)
        investment = monthly_sales * 2 * unit_price * (1 - product['avg_margin'] / 100) if model != SourcingModel.pure_dropship else 0

        return {
            'product_id': product_id,
            'name': product['name'],
            'old_model': old_model.value,
            'new_model': model.value,
            'monthly_sales': monthly_sales,
            'monthly_revenue': product['monthly_revenue'],
            'avg_margin': product['avg_margin'],
            'delivery_before_days': old_delivery,
            'delivery_after_days': new_delivery,
            'delivery_improvement_days': round(old_delivery - new_delivery, 1),
            'estimated_investment': round(investment),
            'estimated_monthly_revenue_increase': round(product['monthly_revenue'] * 0.1) if model == SourcingModel.full_stock else 0,
        }
