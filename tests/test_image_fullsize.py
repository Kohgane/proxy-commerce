from __future__ import annotations

import pytest

from src.collectors.image_fullsize import to_fullsize


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://m.media-amazon.com/images/I/81AbCd._AC_US40_.jpg",
            "https://m.media-amazon.com/images/I/81AbCd.jpg",
        ),
        (
            "https://m.media-amazon.com/images/I/81AbCd._SS40_.jpg",
            "https://m.media-amazon.com/images/I/81AbCd.jpg",
        ),
        (
            "https://m.media-amazon.com/images/I/81AbCd._SX200_.png?quality=85",
            "https://m.media-amazon.com/images/I/81AbCd.png?quality=85",
        ),
        (
            "https://m.media-amazon.com/images/I/81AbCd._CR0,0,300,300_.jpg",
            "https://m.media-amazon.com/images/I/81AbCd.jpg",
        ),
        (
            "https://m.media-amazon.com/images/I/81AbCd._AC_SL1500_.jpg?v=1",
            "https://m.media-amazon.com/images/I/81AbCd.jpg?v=1",
        ),
        (
            "https://m.media-amazon.com/images/I/81AbCd.jpg",
            "https://m.media-amazon.com/images/I/81AbCd.jpg",
        ),
    ],
)
def test_amazon_fullsize(url: str, expected: str) -> None:
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://ae01.alicdn.com/kf/item.jpg_220x220.jpg",
            "https://ae01.alicdn.com/kf/item.jpg",
        ),
        (
            "https://ae01.alicdn.com/kf/item.jpg_50x50.jpg",
            "https://ae01.alicdn.com/kf/item.jpg",
        ),
        (
            "https://ae01.alicdn.com/kf/item.jpg_.webp",
            "https://ae01.alicdn.com/kf/item.jpg",
        ),
        (
            "https://ae01.alicdn.com/kf/item.jpg_220x220.jpg_.webp",
            "https://ae01.alicdn.com/kf/item.jpg",
        ),
        (
            "https://ae01.alicdn.com/kf/item.jpg",
            "https://ae01.alicdn.com/kf/item.jpg",
        ),
    ],
)
def test_aliexpress_fullsize(url: str, expected: str) -> None:
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://img.alicdn.com/bao/uploaded/i1/item.jpg_60x60.jpg", "https://img.alicdn.com/bao/uploaded/i1/item.jpg"),
        ("https://img.alicdn.com/bao/uploaded/i1/item.jpg_400x400q90.jpg", "https://img.alicdn.com/bao/uploaded/i1/item.jpg"),
        ("https://img.alicdn.com/bao/uploaded/i1/item.jpg_.webp", "https://img.alicdn.com/bao/uploaded/i1/item.jpg"),
        ("https://img.alicdn.com/bao/uploaded/i1/item.jpg@100w_100h_1e_1c.jpg", "https://img.alicdn.com/bao/uploaded/i1/item.jpg"),
        ("https://img.alicdn.com/bao/uploaded/i1/item.jpg", "https://img.alicdn.com/bao/uploaded/i1/item.jpg"),
    ],
)
def test_taobao_tmall_1688_fullsize(url: str, expected: str) -> None:
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://img.kwcdn.com/product/temu/item_400x400.jpg", "https://img.kwcdn.com/product/temu/item.jpg"),
        ("https://img.kwcdn.com/product/temu/item_800x800q80.jpg?source=search", "https://img.kwcdn.com/product/temu/item.jpg?source=search"),
        ("https://img.kwcdn.com/product/temu/item.jpg", "https://img.kwcdn.com/product/temu/item.jpg"),
        ("https://a.example.com/item_400x400.jpg", "https://a.example.com/item_400x400.jpg"),
    ],
)
def test_temu_and_unknown_fullsize(url: str, expected: str) -> None:
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://thumbnail.image.rakuten.co.jp/@0_mall/shop/cabinet/item.jpg?_ex=128x128", "https://thumbnail.image.rakuten.co.jp/@0_mall/shop/cabinet/item.jpg"),
        ("https://thumbnail.image.rakuten.co.jp/@0_mall/shop/cabinet/item.jpg?_ex=128x128&resize=1", "https://thumbnail.image.rakuten.co.jp/@0_mall/shop/cabinet/item.jpg?resize=1"),
        ("https://item.rakuten.co.jp/shop/item.jpg", "https://item.rakuten.co.jp/shop/item.jpg"),
    ],
)
def test_rakuten_fullsize(url: str, expected: str) -> None:
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://cdn.shopify.com/s/files/1/0001/image_100x.jpg?v=123", "https://cdn.shopify.com/s/files/1/0001/image.jpg?v=123"),
        ("https://cdn.shopify.com/s/files/1/0001/image_100x200.png?width=100&height=100&v=123", "https://cdn.shopify.com/s/files/1/0001/image.png?v=123"),
        ("https://cdn.shopify.com/s/files/1/0001/image.jpg?v=123", "https://cdn.shopify.com/s/files/1/0001/image.jpg?v=123"),
    ],
)
def test_shopify_fullsize(url: str, expected: str) -> None:
    assert to_fullsize(url) == expected


def test_unknown_domain_is_unchanged() -> None:
    url = "https://images.example.com/photo_400x400.jpg?width=400"
    assert to_fullsize(url) == url
