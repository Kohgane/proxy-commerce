"""A/B 테스트 캠페인."""
from __future__ import annotations
import uuid
from .models import Campaign
from datetime import datetime

class ABTestCampaign:
    def __init__(self) -> None:
        self._tests: dict[str, dict] = {}

    def create_test(self, name: str, variant_a: dict, variant_b: dict, segment_id: str = "") -> dict:
        test_id = str(uuid.uuid4())
        test = {
            "test_id": test_id,
            "name": name,
            "variant_a": {**variant_a, "sent": 0, "opens": 0},
            "variant_b": {**variant_b, "sent": 0, "opens": 0},
            "segment_id": segment_id,
            "status": "running",
            "created_at": datetime.now().isoformat(),
        }
        self._tests[test_id] = test
        return test

    def record_result(self, test_id: str, variant: str, event: str) -> None:
        test = self._tests.get(test_id)
        if not test:
            return
        key = f"variant_{variant}"
        if key in test:
            if event == "sent":
                test[key]["sent"] += 1
            elif event == "open":
                test[key]["opens"] += 1

    def winner(self, test_id: str) -> dict:
        test = self._tests.get(test_id)
        if not test:
            return {}
        a = test["variant_a"]
        b = test["variant_b"]
        a_rate = a["opens"] / a["sent"] if a["sent"] > 0 else 0
        b_rate = b["opens"] / b["sent"] if b["sent"] > 0 else 0
        winner = "a" if a_rate >= b_rate else "b"
        return {"test_id": test_id, "winner": winner, "a_open_rate": round(a_rate, 4), "b_open_rate": round(b_rate, 4)}
