"""src/order_management/split_notifier.py — 분할/병합 알림."""
from __future__ import annotations


class SplitNotifier:
    """분할/병합 알림 발송기."""

    def notify_split(self, order_id: str, sub_order_ids: list, customer_id: str) -> dict:
        """분할 알림을 발송한다."""
        return {
            'notified': True,
            'order_id': order_id,
            'sub_order_ids': list(sub_order_ids),
            'customer_id': customer_id,
        }

    def notify_merge(self, merged_order_id: str, original_ids: list, customer_id: str) -> dict:
        """병합 알림을 발송한다."""
        return {
            'notified': True,
            'merged_order_id': merged_order_id,
            'original_ids': list(original_ids),
            'customer_id': customer_id,
        }
