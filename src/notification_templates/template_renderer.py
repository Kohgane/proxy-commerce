"""src/notification_templates/template_renderer.py — 템플릿 렌더러."""
from __future__ import annotations

import re


class TemplateRenderer:
    """템플릿 렌더러 (stdlib re 모듈만 사용)."""

    def render(self, template: str, variables: dict) -> str:
        """템플릿을 렌더링한다."""
        # Handle {% if condition %}...{% endif %} blocks
        def replace_if(m: re.Match) -> str:
            condition = m.group(1).strip()
            content = m.group(2)
            if variables.get(condition):
                return content
            return ''

        result = re.sub(
            r'\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}',
            replace_if,
            template,
            flags=re.DOTALL,
        )

        # Replace {{var}} with variable values
        def replace_var(m: re.Match) -> str:
            var_name = m.group(1).strip()
            return str(variables.get(var_name, ''))

        result = re.sub(r'\{\{(\w+)\}\}', replace_var, result)
        return result
