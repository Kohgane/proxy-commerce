"""세그먼트 규칙 ABC 및 구현체."""
from __future__ import annotations
from abc import ABC, abstractmethod

class SegmentRule(ABC):
    @abstractmethod
    def matches(self, customer: dict) -> bool: ...
    @abstractmethod
    def name(self) -> str: ...

class PurchaseFrequencyRule(SegmentRule):
    """구매 빈도 기반: heavy/medium/light."""
    def __init__(self, level: str = "heavy") -> None:
        self._level = level
        self._thresholds = {"heavy": 10, "medium": 5, "light": 1}

    def name(self) -> str:
        return f"purchase_frequency_{self._level}"

    def matches(self, customer: dict) -> bool:
        freq = customer.get("purchase_count", 0)
        if self._level == "heavy":
            return freq >= self._thresholds["heavy"]
        elif self._level == "medium":
            return self._thresholds["light"] <= freq < self._thresholds["heavy"]
        return freq < self._thresholds["light"]

class SpendingRule(SegmentRule):
    """총 지출 기반: VIP/일반/저가치."""
    def __init__(self, tier: str = "VIP") -> None:
        self._tier = tier
        self._thresholds = {"VIP": 1000000, "일반": 100000, "저가치": 0}

    def name(self) -> str:
        return f"spending_{self._tier}"

    def matches(self, customer: dict) -> bool:
        spend = customer.get("total_spend", 0)
        if self._tier == "VIP":
            return spend >= self._thresholds["VIP"]
        elif self._tier == "일반":
            return self._thresholds["일반"] <= spend < self._thresholds["VIP"]
        return spend < self._thresholds["일반"]

class RecencyRule(SegmentRule):
    """최근 구매일 기반: 활성/휴면/이탈."""
    def __init__(self, status: str = "활성") -> None:
        self._status = status

    def name(self) -> str:
        return f"recency_{self._status}"

    def matches(self, customer: dict) -> bool:
        days = customer.get("days_since_last_purchase", 999)
        if self._status == "활성":
            return days <= 30
        elif self._status == "휴면":
            return 30 < days <= 90
        return days > 90

class GeographicRule(SegmentRule):
    """지역 기반."""
    def __init__(self, region: str = "서울") -> None:
        self._region = region

    def name(self) -> str:
        return f"geo_{self._region}"

    def matches(self, customer: dict) -> bool:
        return customer.get("region", "") == self._region
