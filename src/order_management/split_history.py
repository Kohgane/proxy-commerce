"""src/order_management/split_history.py — 분할/병합 이력."""
from __future__ import annotations


class SplitHistory:
    """분할/병합 이력 관리자."""

    def __init__(self) -> None:
        self._split_records: dict[str, list] = {}
        self._merge_records: dict[str, list] = {}

    def record_split(self, parent_order_id: str, sub_order_ids: list) -> None:
        """분할 이력을 기록한다."""
        self._split_records.setdefault(parent_order_id, []).append({
            'parent_order_id': parent_order_id,
            'sub_order_ids': list(sub_order_ids),
        })

    def record_merge(self, source_order_ids: list, merged_order_id: str) -> None:
        """병합 이력을 기록한다."""
        self._merge_records.setdefault(merged_order_id, []).append({
            'merged_order_id': merged_order_id,
            'source_order_ids': list(source_order_ids),
        })

    def get_split_history(self, order_id: str) -> list:
        """분할 이력을 반환한다."""
        return list(self._split_records.get(order_id, []))

    def get_merge_history(self, merged_order_id: str) -> list:
        """병합 이력을 반환한다."""
        return list(self._merge_records.get(merged_order_id, []))

    def get_sub_orders(self, order_id: str) -> dict:
        """하위 주문 목록을 반환한다."""
        records = self._split_records.get(order_id, [])
        sub_orders = []
        for record in records:
            sub_orders.extend(record.get('sub_order_ids', []))
        return {'parent_order_id': order_id, 'sub_orders': sub_orders}
