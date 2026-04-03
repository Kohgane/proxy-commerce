"""tests/test_notification_templates.py — Phase 81: 알림 템플릿 엔진 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.notification_templates import (
    TemplateEngine,
    TemplateManager,
    TemplateRenderer,
    TemplateLocalization,
    TemplatePreview,
    NotificationTemplate,
    TemplateVariable,
)


class TestTemplateRenderer:
    def test_render_variable(self):
        renderer = TemplateRenderer()
        result = renderer.render('안녕하세요 {{name}}님', {'name': '홍길동'})
        assert result == '안녕하세요 홍길동님'

    def test_render_if_true(self):
        renderer = TemplateRenderer()
        result = renderer.render('{% if show %}보임{% endif %}', {'show': True})
        assert '보임' in result

    def test_render_if_false(self):
        renderer = TemplateRenderer()
        result = renderer.render('{% if show %}보임{% endif %}', {'show': False})
        assert '보임' not in result

    def test_render_missing_var(self):
        renderer = TemplateRenderer()
        result = renderer.render('{{missing}}', {})
        assert result == ''


class TestTemplateEngine:
    def test_render(self):
        engine = TemplateEngine()
        result = engine.render('주문 {{order_id}} 완료', {'order_id': 'ORD-001'})
        assert 'ORD-001' in result


class TestTemplateManager:
    def test_create_and_get(self):
        mgr = TemplateManager()
        mgr.create(name='welcome', channel='email', subject='환영합니다', body='안녕하세요 {{name}}님')
        tmpl = mgr.get('welcome')
        assert tmpl is not None
        assert tmpl['name'] == 'welcome'
        assert tmpl['channel'] == 'email'

    def test_list(self):
        mgr = TemplateManager()
        mgr.create(name='t1', channel='email', subject='s1', body='b1')
        mgr.create(name='t2', channel='sms', subject='s2', body='b2')
        templates = mgr.list()
        assert len(templates) == 2

    def test_update(self):
        mgr = TemplateManager()
        mgr.create(name='t1', channel='email', subject='s1', body='b1')
        mgr.update('t1', subject='updated')
        tmpl = mgr.get('t1')
        assert tmpl['subject'] == 'updated'
        assert tmpl['version'] == 2

    def test_delete(self):
        mgr = TemplateManager()
        mgr.create(name='t1', channel='email', subject='s1', body='b1')
        mgr.delete('t1')
        assert mgr.get('t1') is None

    def test_get_missing(self):
        mgr = TemplateManager()
        assert mgr.get('nonexistent') is None


class TestTemplateLocalization:
    def test_supported_locales(self):
        loc = TemplateLocalization()
        locales = loc.supported_locales()
        assert 'ko' in locales
        assert 'en' in locales

    def test_set_and_get_locale_template(self):
        loc = TemplateLocalization()
        loc.set_locale_template('welcome', 'en', 'Welcome', 'Hello {{name}}')
        result = loc.get_locale_template('welcome', 'en')
        assert result is not None
        assert result['subject'] == 'Welcome'

    def test_translate_missing(self):
        loc = TemplateLocalization()
        result = loc.translate('nonexistent', 'ko')
        assert result == {}


class TestTemplatePreview:
    def test_preview(self):
        preview = TemplatePreview()
        tmpl = {
            'name': 'test',
            'channel': 'email',
            'subject': '안녕 {{name}}',
            'body': '주문 {{order_id}} 완료',
        }
        result = preview.preview(tmpl)
        assert result['name'] == 'test'
        assert '홍길동' in result['subject']
        assert 'ORD-001' in result['body_preview']


class TestModels:
    def test_template_variable(self):
        var = TemplateVariable(name='name', default='홍길동', required=True)
        assert var.name == 'name'
        assert var.required is True

    def test_notification_template(self):
        tmpl = NotificationTemplate(
            name='test', channel='email', subject='제목', body='내용'
        )
        assert tmpl.locale == 'ko'
        assert tmpl.version == 1
