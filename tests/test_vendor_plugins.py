"""tests/test_vendor_plugins.py — Porter/Memo Paris 벤더 플러그인 테스트."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.plugins.vendors.porter_plugin import PorterPlugin
from src.plugins.vendors.memo_paris_plugin import MemoParisPlugin
from src.plugins.validator import validate_plugin_class, validate_plugin_instance, check_compatibility


# ── Porter 플러그인 테스트 ──────────────────────────────────────

class TestPorterPlugin:
    def setup_method(self):
        self.plugin = PorterPlugin()

    def test_metadata(self):
        assert self.plugin.name == "porter"
        assert self.plugin.currency == "JPY"
        assert self.plugin.country == "JP"
        assert "yoshidakaban" in self.plugin.base_url

    def test_get_vendor_info(self):
        info = self.plugin.get_vendor_info()
        assert isinstance(info, dict)
        assert info["name"] == "porter"
        assert info["currency"] == "JPY"
        assert info["country"] == "JP"

    def test_fetch_products_returns_list(self):
        products = self.plugin.fetch_products()
        assert isinstance(products, list)

    def test_normalize_row(self):
        raw = {
            "title_ja": "タンカー 2WAYブリーフケース",
            "src_url": "https://www.yoshidakaban.com/product/100000.html",
            "price": "¥30,800",
            "category_ja": "タンカー",
            "images": "https://img.example.com/1.jpg",
            "stock": 1,
            "status": "active",
        }
        result = self.plugin.normalize_row(raw)
        assert result["buy_currency"] == "JPY"
        assert result["buy_price"] == 30800.0
        assert result["vendor"] == "PORTER"
        assert "PTR-" in result["sku"]

    def test_parse_price_yen(self):
        html = "<span>¥ 25,300</span>"
        price = self.plugin.parse_price(html)
        assert price == 25300.0

    def test_parse_price_no_match(self):
        assert self.plugin.parse_price("<p>Out of stock</p>") is None

    def test_get_shipping_estimate(self):
        days = self.plugin.get_shipping_estimate()
        assert isinstance(days, int)
        assert days > 0

    def test_check_stock_invalid_url(self):
        """잘못된 URL이면 False 반환."""
        result = self.plugin.check_stock("https://invalid.host.xyz/product/test")
        assert result is False

    def test_validator_passes(self):
        errors = validate_plugin_class(PorterPlugin)
        assert errors == []

    def test_instance_validator_passes(self):
        errors = validate_plugin_instance(self.plugin)
        assert errors == []

    def test_compatibility_check(self):
        assert check_compatibility(PorterPlugin) is True


# ── Memo Paris 플러그인 테스트 ─────────────────────────────────

class TestMemoParisPlugin:
    def setup_method(self):
        self.plugin = MemoParisPlugin()

    def test_metadata(self):
        assert self.plugin.name == "memo_paris"
        assert self.plugin.currency == "EUR"
        assert self.plugin.country == "FR"
        assert "memoparis" in self.plugin.base_url

    def test_get_vendor_info(self):
        info = self.plugin.get_vendor_info()
        assert isinstance(info, dict)
        assert info["name"] == "memo_paris"
        assert info["currency"] == "EUR"

    def test_fetch_products_returns_list(self):
        products = self.plugin.fetch_products()
        assert isinstance(products, list)

    def test_normalize_row(self):
        raw = {
            "title_en": "African Leather Eau de Parfum",
            "src_url": "https://www.memoparis.com/products/african-leather",
            "price": "€250.00",
            "fragrance_type": "Eau de Parfum",
            "images": "https://img.example.com/1.jpg",
            "volume": "75ml",
            "stock": 1,
            "status": "active",
        }
        result = self.plugin.normalize_row(raw)
        assert result["buy_currency"] == "EUR"
        assert result["buy_price"] == 250.0
        assert result["vendor"] == "MEMO_PARIS"
        assert "MMP-" in result["sku"]

    def test_parse_price_euro(self):
        html = "<span class='price'>€ 180,00</span>"
        price = self.plugin.parse_price(html)
        assert price is not None
        assert price > 0

    def test_get_shipping_estimate(self):
        days = self.plugin.get_shipping_estimate()
        assert isinstance(days, int)
        assert days > 0

    def test_check_stock_invalid_url(self):
        """잘못된 URL이면 False 반환."""
        result = self.plugin.check_stock("https://invalid.host.xyz/product/test")
        assert result is False

    def test_validator_passes(self):
        errors = validate_plugin_class(MemoParisPlugin)
        assert errors == []

    def test_instance_validator_passes(self):
        errors = validate_plugin_instance(self.plugin)
        assert errors == []

    def test_compatibility_check(self):
        assert check_compatibility(MemoParisPlugin) is True
