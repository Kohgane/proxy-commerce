"""src/cms/content_renderer.py — 마크다운→HTML 렌더러 (stdlib only)."""
from __future__ import annotations

import re


class ContentRenderer:
    """간단한 마크다운→HTML 변환."""

    def render(self, text: str) -> str:
        html = text
        # Headings
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        # Italic
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        # Newlines to <br>
        html = html.replace('\n', '<br>\n')
        return html
