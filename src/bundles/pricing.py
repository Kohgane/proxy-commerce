"""src/bundles/pricing.py — Phase 44: 번들 가격 계산."""
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PRICING_STRATEGIES = {'sum_discount', 'fixed_price', 'cheapest_free'}


class BundlePricing:
    """번들 가격 계산.

    전략:
      - sum_discount:   합산 후 할인율 적용
      - fixed_price:    고정 가격
      - cheapest_free:  가장 저렴한 상품 무료
    """

    def calculate(
        self,
        items: List[dict],              # [{product_id, quantity, unit_price}]
        strategy: str = 'sum_discount',
        discount_pct: float = 0.0,
        fixed_price: Optional[float] = None,
    ) -> dict:
        """번들 가격 계산.

        Returns:
            {original_price, discount_amount, final_price, strategy}
        """
        if strategy not in PRICING_STRATEGIES:
            raise ValueError(f"지원하지 않는 가격 전략: {strategy}")

        original = Decimal('0')
        for item in items:
            price = Decimal(str(item.get('unit_price', 0)))
            qty = Decimal(str(item.get('quantity', 1)))
            original += price * qty

        if strategy == 'sum_discount':
            pct = Decimal(str(discount_pct))
            discount_amount = (original * pct / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            final = original - discount_amount
        elif strategy == 'fixed_price':
            if fixed_price is None:
                raise ValueError("fixed_price 전략에서는 fixed_price 필수")
            final = Decimal(str(fixed_price))
            discount_amount = original - final
        elif strategy == 'cheapest_free':
            if not items:
                discount_amount = Decimal('0')
                final = original
            else:
                cheapest = min(
                    Decimal(str(i.get('unit_price', 0))) for i in items
                )
                discount_amount = cheapest
                final = original - cheapest
        else:
            discount_amount = Decimal('0')
            final = original

        return {
            'original_price': float(original),
            'discount_amount': float(discount_amount),
            'final_price': float(final),
            'strategy': strategy,
        }

    def calculate_from_bundle(
        self,
        bundle: dict,
        price_catalog: Dict[str, float],
        **kwargs,
    ) -> dict:
        """번들 객체 + 가격 카탈로그로 계산."""
        items = []
        for item in bundle.get('items', []):
            pid = item['product_id']
            unit_price = price_catalog.get(pid, 0)
            items.append({'product_id': pid, 'quantity': item.get('quantity', 1), 'unit_price': unit_price})
        return self.calculate(items, **kwargs)
