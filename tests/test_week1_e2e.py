"""tests/test_week1_e2e.py — Tests for the E2E runner."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.run_e2e import run_e2e
from schemas.product import Product


def _make_product(**kwargs):
    defaults = dict(
        source="test",
        source_product_id="TEST-001",
        source_url="https://example.com/p/1",
        brand="TestBrand",
        title="Sample Product",
        description="desc",
        currency="USD",
        cost_price=89.99,
        images=["https://example.com/img.jpg"],
        stock_status="in_stock",
    )
    defaults.update(kwargs)
    return Product(**defaults)


class TestRunE2E:
    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            run_e2e(source="nonexistent_source")

    def test_unknown_pricing_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown pricing preset"):
            run_e2e(source="test", pricing_preset="ultra_premium")

    def test_dry_run_with_test_source(self):
        """Full e2e dry-run with the built-in 'test' source."""
        result = run_e2e(source="test", pricing_preset="standard", dry_run=True)

        assert result["source"] == "test"
        assert result["dry_run"] is True
        assert result["collect_success"] >= 0
        assert "priced" in result
        assert "published" in result

    def test_result_has_expected_keys(self):
        result = run_e2e(source="test", dry_run=True)
        expected_keys = {
            "source", "pricing_preset", "dry_run",
            "total", "collect_success", "collect_failed",
            "priced", "pricing_errors", "published", "publish_errors", "results",
        }
        assert expected_keys.issubset(result.keys())

    def test_pricing_applied_to_collected_products(self):
        """Sell price should be set after the pricing step."""
        result = run_e2e(source="test", pricing_preset="entry", dry_run=True)
        for pub_result in result.get("results", []):
            if pub_result.get("dry_run"):
                payload = pub_result.get("payload", {})
                assert "regular_price" in payload
                price_str = payload["regular_price"]
                assert float(price_str) > 0.0

    def test_publish_results_contain_dry_run_flag(self):
        result = run_e2e(source="test", dry_run=True)
        for pub_result in result.get("results", []):
            assert pub_result.get("dry_run") is True
