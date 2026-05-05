"""tests/test_messaging_templates.py — 메시지 템플릿 테스트 (Phase 134)."""
import pytest


class TestTemplateStore:
    def test_get_returns_template(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        tpl = store.get("order_received", "email", "ko")
        assert tpl.body
        assert tpl.event == "order_received"
        assert tpl.locale == "ko"
        assert tpl.channel == "email"

    def test_template_renders_variables(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        tpl = store.get("order_received", "email", "ko")
        rendered = tpl.render({"order_id": "TEST-001", "name": "홍길동"})
        # 변수 치환 또는 원본 유지
        assert "TEST-001" in rendered or "{order_id}" not in rendered

    def test_locale_fallback_to_ko(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        # xx_unknown locale → 폴백
        tpl = store.get("order_received", "email", "xx_unknown")
        assert tpl.body  # 뭔가 반환되어야 함

    def test_event_fallback_to_inline(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        tpl = store.get("unknown_event", "email", "ko")
        assert tpl.body  # 인라인 폴백 또는 기본값

    def test_ko_order_received_has_order_id_var(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        tpl = store.get("order_received", "email", "ko")
        # 템플릿에 {order_id} 변수가 있어야 함
        assert "{order_id}" in tpl.body or "order_id" in tpl.body

    def test_ja_order_shipped_available(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        tpl = store.get("order_shipped", "email", "ja")
        assert tpl.body

    def test_en_refund_completed_available(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        tpl = store.get("refund_completed", "email", "en")
        assert tpl.body

    def test_cache_returns_same_instance(self):
        from src.messaging.templates import TemplateStore
        store = TemplateStore()
        tpl1 = store.get("order_received", "email", "ko")
        tpl2 = store.get("order_received", "email", "ko")
        assert tpl1 is tpl2  # 캐시 hit


class TestSafeDict:
    def test_missing_key_returns_placeholder(self):
        from src.messaging.templates import _SafeDict
        d = _SafeDict({"a": "1"})
        assert d["a"] == "1"
        assert d["missing_key"] == "{missing_key}"

    def test_render_with_missing_var_keeps_placeholder(self):
        from src.messaging.templates import MessageTemplate
        tpl = MessageTemplate(
            event="test",
            locale="ko",
            channel="email",
            body="주문번호: {order_id}, 이름: {name}",
        )
        rendered = tpl.render({"order_id": "TEST-001"})
        assert "TEST-001" in rendered
        assert "{name}" in rendered  # 누락 변수는 그대로


class TestInlineTemplates:
    def test_all_event_types_have_template(self):
        from src.messaging.templates import _INLINE_TEMPLATES
        events = [
            "order_received", "payment_confirmed", "order_shipped",
            "order_delivered", "refund_requested", "refund_completed",
            "out_of_stock", "cs_auto_reply",
        ]
        for event in events:
            assert event in _INLINE_TEMPLATES, f"Missing inline template: {event}"

    def test_templates_are_non_empty(self):
        from src.messaging.templates import _INLINE_TEMPLATES
        for event, body in _INLINE_TEMPLATES.items():
            assert body, f"Empty template: {event}"
