"""tests/test_shop_cart.py — 자체몰 카트 테스트 (Phase 131).

세션 기반 카트 add/update/remove/summary 검증.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Flask 테스트 앱 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """카트용 최소 Flask 앱."""
    from flask import Flask
    _app = Flask(__name__)
    _app.secret_key = "test-secret-key"
    _app.config["TESTING"] = True
    return _app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def cart_in_context(app):
    """앱 컨텍스트 내에서 Cart 인스턴스 반환."""
    from src.shop.cart import Cart
    with app.test_request_context("/"):
        yield Cart()


# ---------------------------------------------------------------------------
# 1. Cart 기본 동작
# ---------------------------------------------------------------------------

class TestCartBasic:
    def test_import(self):
        from src.shop.cart import Cart, get_cart
        assert Cart is not None
        assert get_cart is not None

    def test_empty_cart(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            assert cart.count() == 0
            assert cart.items() == []

    def test_add_item(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            from flask import session
            cart = Cart()
            cart.add("test-slug", qty=2)
            assert cart.count() == 2

    def test_add_same_slug_increments(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("test-slug", qty=2)
            cart.add("test-slug", qty=3)
            assert cart.count() == 5

    def test_add_different_slugs(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("slug-a", qty=1)
            cart.add("slug-b", qty=2)
            assert cart.count() == 3

    def test_update_qty(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("test-slug", qty=2)
            cart.update("test-slug", qty=5)
            assert cart.count() == 5

    def test_update_to_zero_removes(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("test-slug", qty=2)
            cart.update("test-slug", qty=0)
            assert cart.count() == 0

    def test_remove_item(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("slug-a", qty=1)
            cart.add("slug-b", qty=2)
            cart.remove("slug-a")
            assert cart.count() == 2

    def test_clear(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("slug-a", qty=3)
            cart.add("slug-b", qty=2)
            cart.clear()
            assert cart.count() == 0

    def test_add_with_options(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("test-slug", qty=1, options={"size": "XS"})
            cart.add("test-slug", qty=1, options={"size": "M"})
            # 다른 옵션은 다른 아이템
            assert cart.count() == 2

    def test_add_invalid_qty_ignored(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            cart.add("test-slug", qty=0)
            assert cart.count() == 0
            cart.add("test-slug", qty=-1)
            assert cart.count() == 0


# ---------------------------------------------------------------------------
# 2. Cart.summary()
# ---------------------------------------------------------------------------

class TestCartSummary:
    def test_empty_summary(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            s = cart.summary()
            assert s["subtotal_krw"] == 0
            assert s["total_krw"] == 0
            assert s["item_count"] == 0
            assert s["items"] == []

    def test_summary_keys(self, app):
        from src.shop.cart import Cart
        with app.test_request_context("/"):
            cart = Cart()
            s = cart.summary()
            assert "subtotal_krw" in s
            assert "shipping_fee_krw" in s
            assert "total_krw" in s
            assert "item_count" in s
            assert "items" in s


# ---------------------------------------------------------------------------
# 3. Cart._item_key
# ---------------------------------------------------------------------------

class TestItemKey:
    def test_no_options(self):
        from src.shop.cart import Cart
        assert Cart._item_key("test-slug", {}) == "test-slug"

    def test_with_options(self):
        from src.shop.cart import Cart
        key = Cart._item_key("test-slug", {"size": "XS", "color": "blue"})
        assert "test-slug" in key
        assert "size=XS" in key
        assert "color=blue" in key

    def test_options_sorted(self):
        from src.shop.cart import Cart
        key1 = Cart._item_key("slug", {"b": "2", "a": "1"})
        key2 = Cart._item_key("slug", {"a": "1", "b": "2"})
        assert key1 == key2


# ---------------------------------------------------------------------------
# 4. get_cart 헬퍼
# ---------------------------------------------------------------------------

def test_get_cart_outside_context():
    """컨텍스트 없이도 Cart 인스턴스 반환."""
    from src.shop.cart import get_cart
    cart = get_cart()
    assert cart is not None
