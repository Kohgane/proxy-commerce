"""src/notification_templates/template_manager.py — 템플릿 관리자."""
from __future__ import annotations


class TemplateManager:
    """템플릿 관리자."""

    def __init__(self) -> None:
        self._templates: dict[str, dict] = {}

    def create(
        self,
        name: str,
        channel: str,
        subject: str,
        body: str,
        variables: list | None = None,
        locale: str = 'ko',
    ) -> dict:
        """템플릿을 생성한다."""
        tmpl = {
            'name': name,
            'channel': channel,
            'subject': subject,
            'body': body,
            'variables': variables or [],
            'locale': locale,
            'version': 1,
        }
        self._templates[name] = tmpl
        return dict(tmpl)

    def list(self) -> list:
        """템플릿 목록을 반환한다."""
        return list(self._templates.values())

    def get(self, name: str) -> dict | None:
        """템플릿을 반환한다."""
        return self._templates.get(name)

    def update(self, name: str, **kwargs) -> dict:
        """템플릿을 업데이트한다."""
        tmpl = self._templates[name]
        for key, val in kwargs.items():
            tmpl[key] = val
        tmpl['version'] = tmpl.get('version', 1) + 1
        return dict(tmpl)

    def delete(self, name: str) -> None:
        """템플릿을 삭제한다."""
        self._templates.pop(name, None)
