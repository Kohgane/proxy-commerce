"""src/form_builder/form_definition.py — 폼 정의 데이터클래스."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    CHECKBOX = "checkbox"
    DATE = "date"
    FILE = "file"
    ADDRESS = "address"
    EMAIL = "email"
    PHONE = "phone"
    TEXTAREA = "textarea"


@dataclass
class FormField:
    """폼 필드 정의."""
    name: str
    field_type: FieldType
    label: str
    required: bool = False
    options: List[Any] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    placeholder: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "field_type": self.field_type.value if isinstance(self.field_type, FieldType) else self.field_type,
            "label": self.label,
            "required": self.required,
            "options": self.options,
            "validation": self.validation,
            "placeholder": self.placeholder,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FormField":
        ft = data.get("field_type", "text")
        try:
            ft = FieldType(ft)
        except ValueError:
            ft = FieldType.TEXT
        return cls(
            name=data["name"],
            field_type=ft,
            label=data.get("label", data["name"]),
            required=data.get("required", False),
            options=data.get("options", []),
            validation=data.get("validation", {}),
            placeholder=data.get("placeholder", ""),
        )


@dataclass
class FormDefinition:
    """폼 정의."""
    name: str
    fields: List[FormField]
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    form_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "form_id": self.form_id,
            "name": self.name,
            "description": self.description,
            "fields": [f.to_dict() for f in self.fields],
            "validation_rules": self.validation_rules,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
