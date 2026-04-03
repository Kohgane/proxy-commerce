"""src/recommendation/ab_test_recommender.py — A/B 테스트 추천기."""
from __future__ import annotations


class ABTestRecommender:
    """A/B 테스트 추천기."""

    def __init__(self) -> None:
        self._assignments: dict[str, str] = {}
        self._results: dict[str, list] = {}

    def assign_variant(self, user_id: str, test_name: str) -> str:
        """사용자에게 변형을 할당한다."""
        key = f'{user_id}|{test_name}'
        if key not in self._assignments:
            # Consistent assignment based on hash
            self._assignments[key] = 'A' if hash(key) % 2 == 0 else 'B'
        return self._assignments[key]

    def record_result(self, user_id: str, test_name: str, clicked: bool) -> None:
        """결과를 기록한다."""
        variant = self.assign_variant(user_id, test_name)
        key = f'{test_name}|{variant}'
        self._results.setdefault(key, []).append({'clicked': clicked})

    def get_stats(self, test_name: str) -> dict:
        """통계를 반환한다."""
        stats: dict[str, dict] = {}
        assigned_variants = {
            v for k, v in self._assignments.items()
            if k.endswith(f'|{test_name}')
        }
        for variant in ('A', 'B'):
            key = f'{test_name}|{variant}'
            records = self._results.get(key, [])
            impressions = len(records)
            clicks = sum(1 for r in records if r['clicked'])
            if impressions > 0 or variant in assigned_variants:
                stats[variant] = {'impressions': impressions, 'clicks': clicks}
        return stats
