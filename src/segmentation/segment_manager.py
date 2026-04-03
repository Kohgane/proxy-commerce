"""src/segmentation/segment_manager.py — 세그먼트 CRUD + 자동/수동 분류."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .segment_rule import SegmentRule


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# 내장 세그먼트 정의 (규칙 기반)
_BUILTIN_SEGMENTS = [
    {
        "name": "VIP",
        "description": "총 구매금액 100만원 이상 고객",
        "rules": [{"field": "total_purchase_amount", "operator": "gte", "value": 1_000_000}],
        "logic": "AND",
        "builtin": True,
    },
    {
        "name": "신규",
        "description": "구매 횟수 1회 이하",
        "rules": [{"field": "purchase_count", "operator": "lte", "value": 1}],
        "logic": "AND",
        "builtin": True,
    },
    {
        "name": "이탈위험",
        "description": "마지막 구매 후 90일 이상 경과",
        "rules": [{"field": "days_since_last_purchase", "operator": "gte", "value": 90}],
        "logic": "AND",
        "builtin": True,
    },
    {
        "name": "대량구매",
        "description": "구매 횟수 10회 이상",
        "rules": [{"field": "purchase_count", "operator": "gte", "value": 10}],
        "logic": "AND",
        "builtin": True,
    },
    {
        "name": "재구매고객",
        "description": "구매 횟수 2회 이상",
        "rules": [{"field": "purchase_count", "operator": "gte", "value": 2}],
        "logic": "AND",
        "builtin": True,
    },
]


class SegmentManager:
    """고객 세그먼트 CRUD + 자동/수동 분류."""

    def __init__(self) -> None:
        self._segments: Dict[str, dict] = {}
        self._customers: Dict[str, List[str]] = {}  # segment_name -> [customer_id]
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        for seg in _BUILTIN_SEGMENTS:
            self._segments[seg["name"]] = {
                "segment_id": str(uuid.uuid4()),
                "name": seg["name"],
                "description": seg["description"],
                "rules": seg["rules"],
                "logic": seg["logic"],
                "builtin": seg["builtin"],
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "customer_count": 0,
            }
            self._customers[seg["name"]] = []

    def create(self, name: str, description: str = "", rules: Optional[List[dict]] = None,
               logic: str = "AND") -> dict:
        """새 세그먼트 생성."""
        if name in self._segments:
            raise ValueError(f"이미 존재하는 세그먼트: {name}")
        seg = {
            "segment_id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "rules": rules or [],
            "logic": logic,
            "builtin": False,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "customer_count": 0,
        }
        self._segments[name] = seg
        self._customers[name] = []
        return dict(seg)

    def get(self, name: str) -> Optional[dict]:
        seg = self._segments.get(name)
        return dict(seg) if seg else None

    def update(self, name: str, **kwargs) -> dict:
        if name not in self._segments:
            raise KeyError(f"세그먼트 없음: {name}")
        allowed = {"description", "rules", "logic"}
        for k, v in kwargs.items():
            if k in allowed:
                self._segments[name][k] = v
        self._segments[name]["updated_at"] = _now_iso()
        return dict(self._segments[name])

    def delete(self, name: str) -> None:
        if name not in self._segments:
            raise KeyError(f"세그먼트 없음: {name}")
        if self._segments[name].get("builtin"):
            raise ValueError(f"내장 세그먼트는 삭제할 수 없습니다: {name}")
        del self._segments[name]
        self._customers.pop(name, None)

    def list(self) -> List[dict]:
        return [dict(s) for s in self._segments.values()]

    def classify_customer(self, customer: Dict[str, Any]) -> List[str]:
        """고객을 규칙에 따라 자동 분류. 해당하는 세그먼트 이름 목록 반환."""
        matched = []
        for name, seg in self._segments.items():
            rules = [SegmentRule(**r) for r in seg.get("rules", [])]
            if not rules:
                continue
            logic = seg.get("logic", "AND")
            if logic == "AND":
                if all(r.evaluate(customer) for r in rules):
                    matched.append(name)
            else:
                if any(r.evaluate(customer) for r in rules):
                    matched.append(name)
        return matched

    def add_customer(self, segment_name: str, customer_id: str) -> None:
        """수동으로 고객을 세그먼트에 추가."""
        if segment_name not in self._segments:
            raise KeyError(f"세그먼트 없음: {segment_name}")
        if customer_id not in self._customers[segment_name]:
            self._customers[segment_name].append(customer_id)
            self._segments[segment_name]["customer_count"] = len(self._customers[segment_name])

    def get_customers(self, segment_name: str) -> List[str]:
        if segment_name not in self._segments:
            raise KeyError(f"세그먼트 없음: {segment_name}")
        return list(self._customers[segment_name])

    def build_segment(self, segment_name: str, all_customers: List[Dict[str, Any]]) -> int:
        """전체 고객 목록으로 세그먼트 자동 재구성."""
        if segment_name not in self._segments:
            raise KeyError(f"세그먼트 없음: {segment_name}")
        seg = self._segments[segment_name]
        rules = [SegmentRule(**r) for r in seg.get("rules", [])]
        logic = seg.get("logic", "AND")
        matched_ids = []
        for customer in all_customers:
            cid = customer.get("customer_id", str(uuid.uuid4()))
            if not rules:
                matched_ids.append(cid)
                continue
            if logic == "AND":
                if all(r.evaluate(customer) for r in rules):
                    matched_ids.append(cid)
            else:
                if any(r.evaluate(customer) for r in rules):
                    matched_ids.append(cid)
        self._customers[segment_name] = matched_ids
        self._segments[segment_name]["customer_count"] = len(matched_ids)
        self._segments[segment_name]["updated_at"] = _now_iso()
        return len(matched_ids)
