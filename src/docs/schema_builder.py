"""src/docs/schema_builder.py — 요청/응답 스키마 정의."""
from __future__ import annotations

from typing import Any, Dict


class SchemaBuilder:
    """요청/응답 스키마를 dict 기반으로 정의."""

    def build_from_dict(self, example: dict) -> dict:
        """예시 dict에서 JSON Schema 생성."""
        return {
            "type": "object",
            "properties": {
                key: self._infer_schema(value)
                for key, value in example.items()
            },
        }

    def _infer_schema(self, value: Any) -> dict:
        if isinstance(value, bool):
            return {"type": "boolean"}
        if isinstance(value, int):
            return {"type": "integer"}
        if isinstance(value, float):
            return {"type": "number"}
        if isinstance(value, list):
            if value:
                return {"type": "array", "items": self._infer_schema(value[0])}
            return {"type": "array"}
        if isinstance(value, dict):
            return self.build_from_dict(value)
        return {"type": "string"}

    def response_schema(self, description: str = "성공", example: dict = None) -> dict:
        schema = {"description": description}
        if example:
            schema["content"] = {
                "application/json": {"schema": self.build_from_dict(example)}
            }
        return schema

    def error_schema(self) -> dict:
        return {
            "description": "오류",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"error": {"type": "string"}},
                    }
                }
            },
        }
