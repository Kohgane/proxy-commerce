"""src/form_builder/form_manager.py — 폼 CRUD + 버전 관리."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .form_definition import FormDefinition, FormField, FieldType


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class FormManager:
    """폼 CRUD + 버전 관리."""

    def __init__(self) -> None:
        self._forms: Dict[str, FormDefinition] = {}
        self._history: Dict[str, List[dict]] = {}  # form_id -> version snapshots

    def create(self, name: str, fields: List[dict] = None,
               validation_rules: dict = None, description: str = "") -> FormDefinition:
        """새 폼 생성."""
        for form in self._forms.values():
            if form.name == name:
                raise ValueError(f"이미 존재하는 폼: {name}")
        parsed_fields = [FormField.from_dict(f) for f in (fields or [])]
        form = FormDefinition(
            name=name,
            fields=parsed_fields,
            validation_rules=validation_rules or {},
            description=description,
        )
        self._forms[form.form_id] = form
        self._history[form.form_id] = [form.to_dict()]
        return form

    def get(self, form_id: str) -> Optional[FormDefinition]:
        return self._forms.get(form_id)

    def get_by_name(self, name: str) -> Optional[FormDefinition]:
        for form in self._forms.values():
            if form.name == name:
                return form
        return None

    def update(self, form_id: str, **kwargs) -> FormDefinition:
        """폼 수정 (버전 자동 증가)."""
        form = self._forms.get(form_id)
        if form is None:
            raise KeyError(f"폼 없음: {form_id}")
        if "name" in kwargs:
            form.name = kwargs["name"]
        if "description" in kwargs:
            form.description = kwargs["description"]
        if "fields" in kwargs:
            form.fields = [FormField.from_dict(f) for f in kwargs["fields"]]
        if "validation_rules" in kwargs:
            form.validation_rules = kwargs["validation_rules"]
        form.version += 1
        form.updated_at = _now_iso()
        self._history[form_id].append(form.to_dict())
        return form

    def delete(self, form_id: str) -> None:
        if form_id not in self._forms:
            raise KeyError(f"폼 없음: {form_id}")
        del self._forms[form_id]
        self._history.pop(form_id, None)

    def list(self) -> List[dict]:
        return [f.to_dict() for f in self._forms.values()]

    def get_version_history(self, form_id: str) -> List[dict]:
        if form_id not in self._history:
            raise KeyError(f"폼 없음: {form_id}")
        return list(self._history[form_id])
