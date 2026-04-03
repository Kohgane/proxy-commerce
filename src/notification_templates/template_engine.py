"""src/notification_templates/template_engine.py — 템플릿 엔진."""
from __future__ import annotations

from .template_renderer import TemplateRenderer


class TemplateEngine:
    """템플릿 엔진."""

    def __init__(self) -> None:
        self._renderer = TemplateRenderer()

    def render(self, template_str: str, variables: dict) -> str:
        """템플릿을 렌더링한다."""
        return self._renderer.render(template_str, variables)
