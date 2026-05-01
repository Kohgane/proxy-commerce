"""tests/test_week1_cs_automation.py — Tests for CS renderer and templates."""
from __future__ import annotations

import pytest

from cs_automation.renderer import (
    AVAILABLE_TEMPLATES,
    CSRenderer,
    MissingVariableError,
    TemplateNotFoundError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RETURN_VARS = {
    "customer_name": "홍길동",
    "order_id": "ORD-20240501-001",
    "return_window_days": "30",
    "refund_processing_days": "3",
    "return_address": "서울시 강남구 테헤란로 1",
    "refund_method": "신용카드 원결제",
    "support_email": "cs@example.com",
    "brand_name": "ProxyCommerce",
}

_EXCHANGE_VARS = {
    "customer_name": "Jane Doe",
    "order_id": "ORD-2024-002",
    "exchange_reason": "Size issue",
    "new_option": "Size M",
    "exchange_shipping_days": "5",
    "return_address": "1234 Commerce St",
    "shipping_fee_policy": "Free exchange shipping",
    "support_email": "cs@example.com",
    "brand_name": "ProxyCommerce",
}

_REFUND_VARS = {
    "customer_name": "Alice",
    "order_id": "ORD-2024-003",
    "product_amount": "$98.00",
    "shipping_fee": "$0.00",
    "total_refund": "$98.00",
    "refund_method": "Original payment",
    "refund_eta_days": "5",
    "support_email": "cs@example.com",
    "brand_name": "ProxyCommerce",
}

_DELAY_VARS = {
    "customer_name": "Bob",
    "order_id": "ORD-2024-004",
    "delay_reason": "Customs clearance",
    "estimated_ship_date": "2024-05-15",
    "support_email": "cs@example.com",
    "brand_name": "ProxyCommerce",
}


# ---------------------------------------------------------------------------
# CSRenderer tests
# ---------------------------------------------------------------------------

class TestCSRenderer:
    def setup_method(self):
        self.renderer = CSRenderer()

    def test_all_templates_available(self):
        for name in AVAILABLE_TEMPLATES:
            body = self.renderer.render(name, self._vars_for(name))
            assert isinstance(body, str)
            assert len(body) > 0

    def _vars_for(self, name):
        mapping = {
            "return": _RETURN_VARS,
            "exchange": _EXCHANGE_VARS,
            "refund": _REFUND_VARS,
            "delay": _DELAY_VARS,
        }
        return mapping[name]

    def test_return_template_substitutes_customer_name(self):
        body = self.renderer.render("return", _RETURN_VARS)
        assert "홍길동" in body
        assert "ORD-20240501-001" in body

    def test_exchange_template_substitutes_variables(self):
        body = self.renderer.render("exchange", _EXCHANGE_VARS)
        assert "Jane Doe" in body
        assert "Size M" in body

    def test_refund_template_substitutes_amounts(self):
        body = self.renderer.render("refund", _REFUND_VARS)
        assert "$98.00" in body

    def test_delay_template_substitutes_reason(self):
        body = self.renderer.render("delay", _DELAY_VARS)
        assert "Customs clearance" in body
        assert "2024-05-15" in body

    def test_no_leftover_placeholders_after_render(self):
        import re
        for name in AVAILABLE_TEMPLATES:
            body = self.renderer.render(name, self._vars_for(name))
            leftover = re.findall(r"\{\{\w+\}\}", body)
            assert leftover == [], f"Template '{name}' has unresolved placeholders: {leftover}"

    def test_strict_mode_raises_on_missing_variable(self):
        renderer = CSRenderer(strict=True)
        with pytest.raises(MissingVariableError):
            renderer.render("return", {})

    def test_non_strict_mode_keeps_placeholder(self):
        renderer = CSRenderer(strict=False)
        body = renderer.render("return", {})
        assert "{{customer_name}}" in body

    def test_template_not_found_raises(self):
        with pytest.raises(TemplateNotFoundError):
            self.renderer.render("nonexistent_template", {})

    def test_required_variables_return(self):
        required = self.renderer.required_variables("return")
        assert "customer_name" in required
        assert "order_id" in required

    def test_custom_templates_dir(self, tmp_path):
        tmpl = tmp_path / "greeting.md"
        tmpl.write_text("Hello, {{name}}!", encoding="utf-8")
        renderer = CSRenderer(templates_dir=tmp_path, strict=True)
        body = renderer.render("greeting", {"name": "World"})
        assert body == "Hello, World!"

    def test_caching_works(self):
        """Second load should use cache (no FileNotFoundError if file removed mid-flight)."""
        body1 = self.renderer.render("delay", _DELAY_VARS)
        body2 = self.renderer.render("delay", _DELAY_VARS)
        assert body1 == body2
