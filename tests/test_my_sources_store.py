from __future__ import annotations

from src.seller_console import my_sources_store as store


def setup_function():
    store._in_memory.clear()


def test_normalize_domain_accepts_url_and_domain():
    assert store.normalize_domain("https://www.Example.com/item") == "example.com"
    assert store.normalize_domain("shop.example.co.kr") == "shop.example.co.kr"


def test_add_list_remove_source_in_memory():
    item = store.add_source("https://brandmall.example.com/product/1", label="브랜드몰")
    assert item["domain"] == "brandmall.example.com"

    items = store.list_sources()
    assert len(items) == 1
    assert items[0]["label"] == "브랜드몰"

    assert store.remove_source("brandmall.example.com") is True
    assert store.list_sources() == []
