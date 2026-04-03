"""src/order_management/order_splitter.py — 주문 분할기."""
from __future__ import annotations

from .models import SubOrder
from .split_rule import SupplierSplitRule, WarehouseSplitRule, ShippingMethodSplitRule


class OrderSplitter:
    """주문 분할기."""

    def __init__(self) -> None:
        self._rules = {
            'supplier': SupplierSplitRule(),
            'warehouse': WarehouseSplitRule(),
            'shipping_method': ShippingMethodSplitRule(),
        }

    def split(self, order, strategy: str = 'supplier') -> dict:
        """주문을 분할한다."""
        if isinstance(order, str):
            return {
                'parent_order_id': order,
                'sub_orders': [
                    SubOrder(
                        parent_order_id=order,
                        sub_order_id=f'{order}-sub-1',
                        items=[],
                        status='pending',
                    )
                ],
            }
        order_id = order.get('order_id', 'unknown')
        items = order.get('items', [])
        shipping_info = order.get('shipping_info', {})
        rule = self._rules.get(strategy, self._rules['supplier'])
        groups = rule.split(items)
        sub_orders = []
        for i, group in enumerate(groups, start=1):
            sub = SubOrder(
                parent_order_id=order_id,
                sub_order_id=f'{order_id}-sub-{i}',
                items=group,
                status='pending',
                shipping_info=dict(shipping_info),
            )
            sub_orders.append(sub)
        return {'parent_order_id': order_id, 'sub_orders': sub_orders}
