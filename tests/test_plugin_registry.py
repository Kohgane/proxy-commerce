"""tests/test_plugin_registry.py — 플러그인 등록/조회/자동로드 테스트."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.plugins.base import VendorPlugin  # noqa: E402
from src.plugins.registry import register_vendor, get_registry  # noqa: E402


# ── 테스트용 더미 플러그인 ──────────────────────────────────────

class _DummyPlugin(VendorPlugin):
    name = "dummy_test"
    display_name = "Dummy Test Vendor"
    currency = "USD"
    country = "US"
    base_url = "https://example.com"

    def fetch_products(self):
        return [{"sku": "DUM-001"}]

    def check_stock(self, url: str) -> bool:
        return True

    def get_vendor_info(self) -> dict:
        return {"name": self.name, "currency": self.currency, "country": self.country}


class _AnotherPlugin(VendorPlugin):
    name = "another_test"
    display_name = "Another Test"
    currency = "EUR"
    country = "FR"
    base_url = "https://another.com"

    def fetch_products(self):
        return []

    def check_stock(self, url: str) -> bool:
        return False

    def get_vendor_info(self) -> dict:
        return {"name": self.name, "currency": self.currency, "country": self.country}


# ── 픽스처 ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_registry():
    """각 테스트마다 레지스트리를 초기화한다."""
    registry = get_registry()
    # 테스트 전 상태 저장
    before = dict(registry._registry)
    yield registry
    # 테스트 후 복원
    registry._registry.clear()
    registry._registry.update(before)


# ── 테스트 ────────────────────────────────────────────────────

class TestPluginRegistryRegister:
    def test_register_plugin(self, isolated_registry):
        isolated_registry.register(_DummyPlugin)
        assert isolated_registry.is_registered("dummy_test")

    def test_register_returns_class(self, isolated_registry):
        result = isolated_registry.register(_DummyPlugin)
        assert result is _DummyPlugin

    def test_register_non_vendorplugin_raises(self, isolated_registry):
        class NotAPlugin:
            name = "bad"
        with pytest.raises(ValueError):
            isolated_registry.register(NotAPlugin)  # type: ignore

    def test_register_empty_name_raises(self, isolated_registry):
        class EmptyNamePlugin(VendorPlugin):
            name = ""
            display_name = ""
            currency = ""
            country = ""
            base_url = ""

            def fetch_products(self):
                return []

            def check_stock(self, url):
                return False

            def get_vendor_info(self):
                return {}

        with pytest.raises(ValueError):
            isolated_registry.register(EmptyNamePlugin)


class TestPluginRegistryLookup:
    def setup_method(self):
        registry = get_registry()
        registry.register(_DummyPlugin)
        registry.register(_AnotherPlugin)

    def test_get_returns_class(self, isolated_registry):
        cls = isolated_registry.get("dummy_test")
        assert cls is _DummyPlugin

    def test_get_unknown_returns_none(self, isolated_registry):
        assert isolated_registry.get("nonexistent") is None

    def test_get_instance_returns_instance(self, isolated_registry):
        instance = isolated_registry.get_instance("dummy_test")
        assert isinstance(instance, _DummyPlugin)

    def test_get_instance_unknown_returns_none(self, isolated_registry):
        assert isolated_registry.get_instance("nonexistent") is None

    def test_list_all(self, isolated_registry):
        names = isolated_registry.list_all()
        assert "dummy_test" in names
        assert "another_test" in names

    def test_list_plugins_metadata(self, isolated_registry):
        plugins = isolated_registry.list_plugins()
        names = [p["name"] for p in plugins]
        assert "dummy_test" in names

    def test_is_registered_true(self, isolated_registry):
        assert isolated_registry.is_registered("dummy_test") is True

    def test_is_registered_false(self, isolated_registry):
        assert isolated_registry.is_registered("nonexistent") is False


class TestRegisterVendorDecorator:
    def test_decorator_registers_class(self, isolated_registry):
        @register_vendor
        class MyPlugin(VendorPlugin):
            name = "decorator_test"
            display_name = "Decorator Test"
            currency = "KRW"
            country = "KR"
            base_url = "https://test.kr"

            def fetch_products(self):
                return []

            def check_stock(self, url):
                return True

            def get_vendor_info(self):
                return {"name": self.name, "currency": self.currency, "country": self.country}

        assert isolated_registry.is_registered("decorator_test")

    def test_decorator_returns_class(self, isolated_registry):
        @register_vendor
        class AnotherPlugin(VendorPlugin):
            name = "another_decorator_test"
            display_name = "Another Decorator Test"
            currency = "JPY"
            country = "JP"
            base_url = "https://test.jp"

            def fetch_products(self):
                return []

            def check_stock(self, url):
                return True

            def get_vendor_info(self):
                return {"name": self.name, "currency": self.currency, "country": self.country}

        assert AnotherPlugin.name == "another_decorator_test"


class TestPluginRegistryLen:
    def test_len(self, isolated_registry):
        before = len(isolated_registry)
        isolated_registry.register(_DummyPlugin)
        assert len(isolated_registry) == before + 1

    def test_clear(self, isolated_registry):
        isolated_registry.register(_DummyPlugin)
        isolated_registry.clear()
        assert len(isolated_registry) == 0
