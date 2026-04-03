"""src/data_exchange/data_transformer.py — 데이터 변환기."""
from __future__ import annotations


class DataTransformer:
    """데이터 변환기."""

    def transform(self, data: list, mapping: dict | None = None, filters: list | None = None) -> list:
        """데이터를 매핑과 필터를 적용해 변환한다."""
        result = list(data)

        if filters:
            for f in filters:
                field = f.get("field", "")
                op = f.get("op", "eq")
                value = f.get("value")
                if op == "eq":
                    result = [r for r in result if isinstance(r, dict) and r.get(field) == value]
                elif op == "ne":
                    result = [r for r in result if isinstance(r, dict) and r.get(field) != value]
                elif op == "gt":
                    result = [r for r in result if isinstance(r, dict) and r.get(field, 0) > value]
                elif op == "lt":
                    result = [r for r in result if isinstance(r, dict) and r.get(field, 0) < value]

        if mapping:
            transformed = []
            for row in result:
                if isinstance(row, dict):
                    new_row = {mapping.get(k, k): v for k, v in row.items()}
                    transformed.append(new_row)
                else:
                    transformed.append(row)
            result = transformed

        return result
