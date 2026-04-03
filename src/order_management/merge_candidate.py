"""src/order_management/merge_candidate.py — 병합 후보."""
from __future__ import annotations


class MergeCandidate:
    """병합 후보 탐색기."""

    def find_candidates(self, orders: list) -> list:
        """병합 후보를 탐색한다."""
        groups: dict[tuple, list] = {}
        for order in orders:
            key = (order.get('recipient', ''), order.get('warehouse_id', ''))
            groups.setdefault(key, []).append(order.get('order_id', ''))
        candidates = []
        for key, ids in groups.items():
            if len(ids) >= 2:
                candidates.append({
                    'order_ids': ids,
                    'reason': f'동일 수령인({key[0]}) 및 창고({key[1]})',
                })
        return candidates
