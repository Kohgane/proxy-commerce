"""src/sourcing_discovery/profitability_predictor.py — 수익성 예측 (Phase 115)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_CURRENCY_RATES: Dict[str, float] = {
    'CNY': 185.0,
    'USD': 1350.0,
    'JPY': 9.0,
    'EUR': 1480.0,
    'KRW': 1.0,
}


@dataclass
class ProfitabilityPrediction:
    product_name: str
    source_price: float
    source_currency: str
    estimated_selling_price: float
    estimated_costs: Dict[str, float]
    estimated_margin_rate: float
    estimated_monthly_units: int
    estimated_monthly_profit: float
    break_even_units: int
    recommended_model: str
    confidence_score: float
    risk_factors: List[str]


class ProfitabilityPredictor:
    """수익성 예측기."""

    def predict_profitability(self, product_info: Dict[str, Any]) -> ProfitabilityPrediction:
        """수익성 예측."""
        product_name = product_info.get('product_name', '알 수 없는 상품')
        source_price = float(product_info.get('source_price', 0))
        source_currency = product_info.get('source_currency', 'CNY')
        monthly_units = int(product_info.get('monthly_units', 50))

        rate = _CURRENCY_RATES.get(source_currency.upper(), 185.0)
        krw_price = source_price * rate

        customs = krw_price * 0.08
        vat = krw_price * 0.10
        platform_fee_rate = 0.10
        shipping_per_unit = float(product_info.get('shipping_cost', 5000))

        selling_price = krw_price * 2.5
        platform_fee = selling_price * platform_fee_rate

        total_variable_cost = krw_price + customs + vat + platform_fee + shipping_per_unit
        margin_amount = selling_price - total_variable_cost
        margin_rate = (margin_amount / selling_price * 100) if selling_price > 0 else 0

        fixed_cost_monthly = float(product_info.get('fixed_cost', 100000))
        break_even = int(fixed_cost_monthly / margin_amount) + 1 if margin_amount > 0 else 9999

        monthly_profit = margin_amount * monthly_units - fixed_cost_monthly

        risk_factors: List[str] = []
        if margin_rate < 20:
            risk_factors.append('낮은 마진율 (20% 미만)')
        if source_price > 50 and source_currency == 'CNY':
            risk_factors.append('높은 소싱 원가')
        if break_even > monthly_units:
            risk_factors.append('손익분기점 미달 위험')

        recommended_model = self.recommend_sourcing_model(
            {**product_info, 'monthly_units': monthly_units}
        )['model']

        confidence = min(95.0, max(40.0, 75.0 + margin_rate * 0.3))

        return ProfitabilityPrediction(
            product_name=product_name,
            source_price=source_price,
            source_currency=source_currency,
            estimated_selling_price=round(selling_price, 0),
            estimated_costs={
                'sourcing_krw': round(krw_price, 0),
                'customs': round(customs, 0),
                'vat': round(vat, 0),
                'platform_fee': round(platform_fee, 0),
                'shipping': shipping_per_unit,
                'total_variable': round(total_variable_cost, 0),
            },
            estimated_margin_rate=round(margin_rate, 1),
            estimated_monthly_units=monthly_units,
            estimated_monthly_profit=round(monthly_profit, 0),
            break_even_units=break_even,
            recommended_model=recommended_model,
            confidence_score=round(confidence, 1),
            risk_factors=risk_factors,
        )

    def predict_demand(self, product_info: Dict[str, Any]) -> Dict[str, Any]:
        """수요 예측."""
        import random
        product_name = product_info.get('product_name', '상품')
        base_demand = int(product_info.get('search_volume', 10000)) // 100
        base_demand = max(10, min(500, base_demand))
        growth_rate = float(product_info.get('growth_rate', 10))

        return {
            'product_name': product_name,
            'estimated_monthly_units': base_demand,
            'demand_trend': 'rising' if growth_rate > 20 else 'stable',
            'seasonal_factor': product_info.get('seasonality_score', 0.3),
            'peak_month': product_info.get('peak_month', 12),
            'demand_confidence': round(random.uniform(65, 90), 1),
            'market_size_estimate': base_demand * 12 * int(product_info.get('source_price', 10) * 185 * 2.5),
        }

    def recommend_sourcing_model(self, product_info: Dict[str, Any]) -> Dict[str, Any]:
        """소싱 모델 추천."""
        monthly_units = int(product_info.get('monthly_units', 50))

        if monthly_units >= 50:
            model = 'full_stock'
            description = '완전 사입 방식 (Full Stock). 안정적인 재고 보유로 빠른 배송 가능.'
            inventory_days = 30
        elif monthly_units >= 10:
            model = 'semi_stock'
            description = '부분 사입 방식 (Semi Stock). 핵심 상품은 재고 보유, 나머지는 드랍쉬핑.'
            inventory_days = 14
        else:
            model = 'pure_dropship'
            description = '순수 드랍쉬핑 방식 (Pure Dropship). 재고 없이 주문 즉시 소싱.'
            inventory_days = 0

        return {
            'model': model,
            'description': description,
            'monthly_units': monthly_units,
            'recommended_inventory_days': inventory_days,
            'advantages': {
                'full_stock': ['빠른 배송', '대량 할인', '안정적 공급'],
                'semi_stock': ['유연한 재고 관리', '위험 분산', '중간 배송 속도'],
                'pure_dropship': ['초기 투자 없음', '재고 위험 제로', '다품종 소싱 가능'],
            }.get(model, []),
        }

    def batch_predict(self, products: List[Dict[str, Any]]) -> List[ProfitabilityPrediction]:
        """일괄 수익성 예측."""
        return [self.predict_profitability(p) for p in products]
