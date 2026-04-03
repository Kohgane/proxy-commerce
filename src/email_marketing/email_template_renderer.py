"""이메일 본문 렌더링."""
from __future__ import annotations
import re

class EmailTemplateRenderer:
    def render(self, template: str, variables: dict) -> str:
        result = template
        for key, val in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(val))
        # Remove unreplaced placeholders
        result = re.sub(r'\{\{[^}]+\}\}', '', result)
        return result
