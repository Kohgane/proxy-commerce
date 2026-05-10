"""tests/test_dashboard_widget_data.py — 대시보드 위젯 데이터 real/empty/mock 분기 테스트 (Phase 142)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSafeCallMockHandling:
    def test_mock_hidden_when_show_mock_off(self, monkeypatch):
        """DASHBOARD_SHOW_MOCK=0 시 is_mock=True 데이터는 empty 상태로 변환."""
        monkeypatch.setenv("DASHBOARD_SHOW_MOCK", "0")
        # widgets 모듈 재로드 (env var 반영)
        import importlib
        import src.seller_console.widgets as widgets_mod
        importlib.reload(widgets_mod)

        # is_mock=True 를 반환하는 함수
        def _mock_fn():
            return {"value": 100, "is_mock": True}

        result = widgets_mod._safe_call(_mock_fn)
        assert result.get("is_mock") is False
        assert result.get("status") == "empty"

    def test_mock_shown_when_show_mock_on(self, monkeypatch):
        """DASHBOARD_SHOW_MOCK=1 시 is_mock=True 데이터 그대로 반환."""
        monkeypatch.setenv("DASHBOARD_SHOW_MOCK", "1")
        import importlib
        import src.seller_console.widgets as widgets_mod
        importlib.reload(widgets_mod)

        def _mock_fn():
            return {"value": 100, "is_mock": True}

        result = widgets_mod._safe_call(_mock_fn)
        assert result.get("is_mock") is True

    def test_exception_returns_empty_when_show_mock_off(self, monkeypatch):
        """DASHBOARD_SHOW_MOCK=0 시 예외 발생 → empty 상태 반환."""
        monkeypatch.setenv("DASHBOARD_SHOW_MOCK", "0")
        import importlib
        import src.seller_console.widgets as widgets_mod
        importlib.reload(widgets_mod)

        def _fail_fn():
            raise RuntimeError("connection error")

        result = widgets_mod._safe_call(_fail_fn)
        assert result.get("is_mock") is False
        assert result.get("status") == "empty"

    def test_exception_returns_mock_when_show_mock_on(self, monkeypatch):
        """DASHBOARD_SHOW_MOCK=1 시 예외 발생 → mock 반환."""
        monkeypatch.setenv("DASHBOARD_SHOW_MOCK", "1")
        import importlib
        import src.seller_console.widgets as widgets_mod
        importlib.reload(widgets_mod)

        def _fail_fn():
            raise RuntimeError("connection error")

        result = widgets_mod._safe_call(_fail_fn)
        assert result.get("is_mock") is True

    def test_real_data_passthrough(self, monkeypatch):
        """실제 데이터(is_mock=False)는 변경 없이 반환."""
        monkeypatch.setenv("DASHBOARD_SHOW_MOCK", "0")
        import importlib
        import src.seller_console.widgets as widgets_mod
        importlib.reload(widgets_mod)

        def _real_fn():
            return {"gmv": 1000000, "is_mock": False}

        result = widgets_mod._safe_call(_real_fn)
        assert result.get("is_mock") is False
        assert result.get("gmv") == 1000000


class TestBuildWidgets:
    def test_build_all_widgets_returns_list(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_SHOW_MOCK", "0")
        import importlib
        import src.seller_console.widgets as widgets_mod
        importlib.reload(widgets_mod)

        with patch("src.seller_console.widgets.get_today_kpi", return_value={"is_mock": False}), \
             patch("src.seller_console.widgets.get_collect_queue_status", return_value={"is_mock": False}), \
             patch("src.seller_console.widgets.get_market_product_status", return_value={"is_mock": False}), \
             patch("src.seller_console.widgets.get_sourcing_alerts", return_value={"is_mock": False}), \
             patch("src.seller_console.widgets.get_returns_cs_status", return_value={"is_mock": False}), \
             patch("src.seller_console.widgets.get_auto_purchase_queue", return_value={"is_mock": False}), \
             patch("src.seller_console.widgets.get_fx_rates", return_value={"is_mock": False}):
            widgets = widgets_mod.build_all_widgets()

        assert isinstance(widgets, list)
        assert len(widgets) >= 7
