"""src/data_exchange/export_template.py — 내보내기 템플릿."""
from __future__ import annotations

import datetime
import uuid


class ExportTemplate:
    """내보내기 템플릿 관리."""

    def __init__(self) -> None:
        self._templates: dict[str, dict] = {}

    def create(self, name: str, fields: list, format_: str = "json") -> dict:
        """새 템플릿을 생성한다."""
        template = {
            "template_id": str(uuid.uuid4()),
            "name": name,
            "fields": fields,
            "format": format_,
            "created_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        self._templates[template["template_id"]] = template
        return template

    def get(self, template_id: str) -> dict:
        """템플릿을 조회한다."""
        return self._templates.get(template_id, {})

    def list_templates(self) -> list:
        """모든 템플릿 목록을 반환한다."""
        return list(self._templates.values())
