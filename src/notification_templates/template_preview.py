"""src/notification_templates/template_preview.py — 템플릿 미리보기."""
from __future__ import annotations

from .template_renderer import TemplateRenderer


class TemplatePreview:
    """템플릿 미리보기."""

    _sample_data = {
        'name': '홍길동',
        'order_id': 'ORD-001',
        'product_name': '샘플 상품',
        'amount': '50,000',
        'date': '2024-01-01',
        'tracking_number': 'TRK-12345',
        'msg': '안녕하세요',
        'show': True,
    }

    def __init__(self) -> None:
        self._renderer = TemplateRenderer()

    def preview(self, tmpl: dict) -> dict:
        """템플릿 미리보기를 반환한다."""
        body_preview = self._renderer.render(tmpl.get('body', ''), self._sample_data)
        return {
            'name': tmpl.get('name', ''),
            'channel': tmpl.get('channel', ''),
            'subject': self._renderer.render(tmpl.get('subject', ''), self._sample_data),
            'body_preview': body_preview,
        }
