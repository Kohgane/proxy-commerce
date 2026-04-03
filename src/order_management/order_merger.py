"""src/order_management/order_merger.py — 주문 병합기."""
from __future__ import annotations


class OrderMerger:
    """주문 병합기."""

    def merge(self, order_ids: list) -> dict:
        """주문을 병합한다."""
        merged_id = f'merged-{"-".join(order_ids[:2])}'
        return {
            'merged_order_id': merged_id,
            'merged_order_ids': list(order_ids),
            'status': 'merged',
        }
