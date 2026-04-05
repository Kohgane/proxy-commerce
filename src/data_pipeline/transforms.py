"""src/data_pipeline/transforms.py — 데이터 변환 (Phase 100)."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any


class Transform(ABC):
    """데이터 변환 추상 기반 클래스."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def apply(self, data: list[dict]) -> list[dict]:
        ...

    def validate(self, data: list[dict]) -> bool:
        return isinstance(data, list)


class FilterTransform(Transform):
    """조건 기반 레코드 필터링."""

    _OPS = {
        "eq": lambda a, b: a == b,
        "neq": lambda a, b: a != b,
        "gt": lambda a, b: a > b,
        "lt": lambda a, b: a < b,
        "in": lambda a, b: a in b,
        "contains": lambda a, b: b in str(a),
    }

    def __init__(self, field: str, operator: str, value: Any) -> None:
        self._field = field
        self._operator = operator
        self._value = value

    @property
    def name(self) -> str:
        return "filter"

    def apply(self, data: list[dict]) -> list[dict]:
        op_func = self._OPS.get(self._operator, lambda a, b: a == b)
        result = []
        for row in data:
            try:
                if op_func(row.get(self._field), self._value):
                    result.append(row)
            except (TypeError, KeyError):
                pass
        return result


class MapTransform(Transform):
    """필드 이름 매핑/변환."""

    def __init__(self, field_map: dict) -> None:
        self._field_map = field_map

    @property
    def name(self) -> str:
        return "map"

    def apply(self, data: list[dict]) -> list[dict]:
        result = []
        for row in data:
            new_row = dict(row)
            for src_field, dst_field in self._field_map.items():
                if src_field in new_row:
                    new_row[dst_field] = new_row.pop(src_field)
            result.append(new_row)
        return result


class AggregateTransform(Transform):
    """그룹별 집계."""

    def __init__(self, group_by: list[str], aggregations: dict) -> None:
        self._group_by = group_by
        self._aggregations = aggregations  # {"field": "sum/avg/count/min/max"}

    @property
    def name(self) -> str:
        return "aggregate"

    def apply(self, data: list[dict]) -> list[dict]:
        groups: dict = {}
        for row in data:
            key = tuple(row.get(g) for g in self._group_by)
            if key not in groups:
                groups[key] = []
            groups[key].append(row)

        result = []
        for key, rows in groups.items():
            agg_row = {g: v for g, v in zip(self._group_by, key)}
            for field, agg_func in self._aggregations.items():
                values = [r.get(field) for r in rows if r.get(field) is not None]
                if not values:
                    agg_row[f"{field}_{agg_func}"] = None
                    continue
                try:
                    numeric = [float(v) for v in values]
                except (TypeError, ValueError):
                    numeric = []
                if agg_func == "count":
                    agg_row[f"{field}_count"] = len(values)
                elif agg_func == "sum" and numeric:
                    agg_row[f"{field}_sum"] = sum(numeric)
                elif agg_func == "avg" and numeric:
                    agg_row[f"{field}_avg"] = sum(numeric) / len(numeric)
                elif agg_func == "min" and numeric:
                    agg_row[f"{field}_min"] = min(numeric)
                elif agg_func == "max" and numeric:
                    agg_row[f"{field}_max"] = max(numeric)
                else:
                    agg_row[f"{field}_{agg_func}"] = None
            result.append(agg_row)
        return result


class JoinTransform(Transform):
    """두 데이터셋 조인."""

    def __init__(self, right_data: list[dict], join_key: str, join_type: str = "inner") -> None:
        self._right_data = right_data
        self._join_key = join_key
        self._join_type = join_type

    @property
    def name(self) -> str:
        return "join"

    def apply(self, data: list[dict]) -> list[dict]:
        right_index: dict = {}
        for row in self._right_data:
            key = row.get(self._join_key)
            if key is not None:
                right_index.setdefault(key, []).append(row)

        result = []
        for left_row in data:
            key = left_row.get(self._join_key)
            right_rows = right_index.get(key, [])

            if right_rows:
                for right_row in right_rows:
                    merged = {**left_row}
                    for k, v in right_row.items():
                        if k != self._join_key:
                            merged[f"r_{k}"] = v
                    result.append(merged)
            elif self._join_type == "left":
                result.append(dict(left_row))

        if self._join_type == "right":
            left_keys = {r.get(self._join_key) for r in data}
            for right_row in self._right_data:
                if right_row.get(self._join_key) not in left_keys:
                    result.append(dict(right_row))

        return result


class EnrichTransform(Transform):
    """룩업 테이블로 필드 추가."""

    def __init__(self, lookup_table: dict, key_field: str, enrich_fields: list[str]) -> None:
        self._lookup_table = lookup_table
        self._key_field = key_field
        self._enrich_fields = enrich_fields

    @property
    def name(self) -> str:
        return "enrich"

    def apply(self, data: list[dict]) -> list[dict]:
        result = []
        for row in data:
            new_row = dict(row)
            key = row.get(self._key_field)
            lookup = self._lookup_table.get(key, {})
            for ef in self._enrich_fields:
                new_row[ef] = lookup.get(ef)
            result.append(new_row)
        return result


class DeduplicateTransform(Transform):
    """중복 레코드 제거."""

    def __init__(self, key_fields: list[str], keep: str = "last") -> None:
        self._key_fields = key_fields
        self._keep = keep

    @property
    def name(self) -> str:
        return "deduplicate"

    def apply(self, data: list[dict]) -> list[dict]:
        seen: dict = {}
        for i, row in enumerate(data):
            key = tuple(row.get(k) for k in self._key_fields)
            seen[key] = i

        if self._keep == "first":
            seen_first: dict = {}
            for i, row in enumerate(data):
                key = tuple(row.get(k) for k in self._key_fields)
                if key not in seen_first:
                    seen_first[key] = i
            indices = set(seen_first.values())
        else:
            indices = set(seen.values())

        return [row for i, row in enumerate(data) if i in indices]


class TypeCastTransform(Transform):
    """필드 타입 변환."""

    _CASTERS = {
        "int": int,
        "float": float,
        "str": str,
        "date": str,  # 단순 문자열 변환
    }

    def __init__(self, field_types: dict) -> None:
        self._field_types = field_types

    @property
    def name(self) -> str:
        return "typecast"

    def apply(self, data: list[dict]) -> list[dict]:
        result = []
        for row in data:
            new_row = dict(row)
            for field, type_name in self._field_types.items():
                if field in new_row and new_row[field] is not None:
                    caster = self._CASTERS.get(type_name, str)
                    try:
                        new_row[field] = caster(new_row[field])
                    except (ValueError, TypeError):
                        pass
            result.append(new_row)
        return result


class TransformChain(Transform):
    """변환 체인 (순차적 변환)."""

    def __init__(self, transforms: list[Transform] | None = None) -> None:
        self._transforms: list[Transform] = list(transforms or [])

    @property
    def name(self) -> str:
        return "chain"

    def apply(self, data: list[dict]) -> list[dict]:
        result = data
        for t in self._transforms:
            result = t.apply(result)
        return result

    def validate(self, data: list[dict]) -> bool:
        return all(t.validate(data) for t in self._transforms)

    def add(self, transform: Transform) -> None:
        self._transforms.append(transform)
