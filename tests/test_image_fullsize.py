import pytest

from src.collectors.image_fullsize import to_fullsize


@pytest.mark.parametrize(
    "url",
    [
        "https://m.media-amazon.com/images/I/71abc._AC_US40_.jpg",
        "https://m.media-amazon.com/images/I/71abc._SS40_.jpg",
        "https://m.media-amazon.com/images/I/71abc._SX200_.jpg",
        "https://m.media-amazon.com/images/I/71abc._SY300_.jpg",
        "https://m.media-amazon.com/images/I/71abc._AC_SL1500_.jpg",
        "https://images-na.ssl-images-amazon.com/images/I/71abc._AC_UL320_.jpg",
    ],
)
def test_amazon_thumbnail_tokens(url):
    expected_host = "m.media-amazon.com" if "m.media-amazon.com" in url else "images-na.ssl-images-amazon.com"
    assert to_fullsize(url) == f"https://{expected_host}/images/I/71abc.jpg"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://ae01.alicdn.com/kf/S12ab.jpg_220x220.jpg", "https://ae01.alicdn.com/kf/S12ab.jpg"),
        ("https://ae01.alicdn.com/kf/S12ab.jpg_350x350q75.jpg", "https://ae01.alicdn.com/kf/S12ab.jpg"),
        ("https://ae01.alicdn.com/kf/S12ab.jpg_.webp", "https://ae01.alicdn.com/kf/S12ab.jpg"),
        ("https://ae01.alicdn.com/kf/S12ab.jpg_Q90.jpg_.avif", "https://ae01.alicdn.com/kf/S12ab.jpg"),
        ("https://ae-pic-a1.aliexpress-media.com/kf/S12ab.jpg_640x640q90.jpg", "https://ae-pic-a1.aliexpress-media.com/kf/S12ab.jpg"),
    ],
)
def test_aliexpress_thumbnail_tails(url, expected):
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://img.alicdn.com/imgextra/i1/O1CN01x.jpg_60x60.jpg", "https://img.alicdn.com/imgextra/i1/O1CN01x.jpg"),
        ("https://img.alicdn.com/imgextra/i1/O1CN01x.jpg_400x400q90.jpg", "https://img.alicdn.com/imgextra/i1/O1CN01x.jpg"),
        ("https://img.alicdn.com/imgextra/i1/O1CN01x.jpg_.webp", "https://img.alicdn.com/imgextra/i1/O1CN01x.jpg"),
        ("https://gw.alicdn.com/imgextra/i1/O1CN01x.jpg_q50.jpg_.webp", "https://gw.alicdn.com/imgextra/i1/O1CN01x.jpg"),
        ("//img.alicdn.com/imgextra/i1/O1CN01x.jpg_60x60.jpg", "https://img.alicdn.com/imgextra/i1/O1CN01x.jpg"),
    ],
)
def test_alicdn_thumbnail_tails(url, expected):
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://cbu01.alicdn.com/img/ibank/2024/1.jpg_.webp",
        "https://cbu01.alicdn.com/img/ibank/2024/1.220x220.jpg",
        "https://cbu01.alicdn.com/img/ibank/2024/1.search.jpg",
        "https://cbu01.alicdn.com/img/ibank/2024/1.summ.jpg",
        "https://cbu01.alicdn.com/img/ibank/2024/1.jpg",
    ],
)
def test_1688_thumbnail_tails(url):
    assert to_fullsize(url) in {
        "https://cbu01.alicdn.com/img/ibank/2024/1.jpg",
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://img.kwcdn.com/product/fancy/a.jpg?imageView2/2/w/300/q/70/format/webp",
        "https://img.kwcdn.com/product/fancy/a.jpg?imageMogr2/thumbnail/300x300",
        "https://img.kwcdn.com/product/fancy/a.jpg?imageView2/2/w/800",
        "https://img.kwcdn.com/product/fancy/a.jpg?imageMogr2/crop/800x800",
        "https://img.kwcdn.com/product/fancy/a.jpg?imageView2/2/w/1200/h/1200",
    ],
)
def test_temu_query_processing(url):
    assert to_fullsize(url) == "https://img.kwcdn.com/product/fancy/a.jpg"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://thumbnail.image.rakuten.co.jp/@0_mall/shop/item.jpg?_ex=128x128", "https://thumbnail.image.rakuten.co.jp/shop/item.jpg"),
        ("https://thumbnail.image.rakuten.co.jp/@0_mall/shop/item.jpg?_ex=128x128&size=large", "https://thumbnail.image.rakuten.co.jp/shop/item.jpg?size=large"),
        ("https://thumbnail.image.rakuten.co.jp/@0_mall/shop/item.jpg", "https://thumbnail.image.rakuten.co.jp/shop/item.jpg"),
        ("https://thumbnail.image.rakuten.co.jp/@1_mall/shop/item.jpg?_ex=128x128", "https://thumbnail.image.rakuten.co.jp/@1_mall/shop/item.jpg"),
        ("https://thumbnail.image.rakuten.co.jp/shop/item.jpg?_ex=128x128", "https://thumbnail.image.rakuten.co.jp/shop/item.jpg"),
    ],
)
def test_rakuten_thumbnail(url, expected):
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://cdn.shopify.com/products/a_100x.jpg", "https://cdn.shopify.com/products/a.jpg"),
        ("https://cdn.shopify.com/products/a_100x100.jpg", "https://cdn.shopify.com/products/a.jpg"),
        ("https://cdn.shopify.com/products/a_small.jpg", "https://cdn.shopify.com/products/a.jpg"),
        ("https://cdn.shopify.com/products/a.jpg?width=200", "https://cdn.shopify.com/products/a.jpg"),
        ("https://cdn.shopify.com/products/a.jpg?width=200&height=300&v=1", "https://cdn.shopify.com/products/a.jpg?v=1"),
    ],
)
def test_shopify_thumbnail(url, expected):
    assert to_fullsize(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/image.jpg",
        "https://cdn.example.com/product/photo_100x100.jpg",
        "https://m.media-amazon.com/images/I/71abc.jpg",
        "https://img.alicdn.com/imgextra/i1/O1CN01x.jpg",
        "https://cdn.shopify.com/products/a.jpg?v=1",
    ],
)
def test_original_and_unknown_urls_are_unchanged(url):
    assert to_fullsize(url) == url


@pytest.mark.parametrize("value", [None, "", 0])
def test_empty_values(value):
    assert to_fullsize(value) == ""


def test_scheme_relative_alicdn():
    assert to_fullsize("//img.alicdn.com/imgextra/i1/O1CN01x.jpg_60x60.jpg") == "https://img.alicdn.com/imgextra/i1/O1CN01x.jpg"
