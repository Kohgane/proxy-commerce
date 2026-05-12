from __future__ import annotations

from decimal import Decimal


def test_normalize_jsonld_product_group_prefers_group_and_variants():
    from src.ai_listing.jsonld_parser import normalize_jsonld

    raw = [{
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "name": "ignore"},
            {
                "@type": "ProductGroup",
                "name": "EIGHT BALL HOODIE",
                "brand": {"name": "MARKET"},
                "category": "Hoodies",
                "description": "80% cotton, 20% polyester",
                "hasVariant": [{"@type": "Product", "name": "EIGHT BALL HOODIE - WOOD ASH / S"}],
            },
        ],
    }]

    normalized = normalize_jsonld(raw)
    assert normalized["name"] == "EIGHT BALL HOODIE"
    assert normalized["brand"]["name"] == "MARKET"
    assert normalized["category"] == "Hoodies"
    assert len(normalized["hasVariant"]) == 1


def test_extract_price_from_jsonld_uses_variant_offer_fallback():
    from src.ai_listing.jsonld_parser import extract_price_from_jsonld

    normalized = {
        "hasVariant": [
            {"name": "EIGHT BALL HOODIE - DUSK BLUE / M", "offers": {"price": "120.00", "priceCurrency": "USD"}}
        ]
    }

    price = extract_price_from_jsonld(normalized)
    assert price == {"amount": Decimal("120.00"), "currency": "USD", "source": "hasVariant[0].offers.price"}


def test_extract_material_prefers_percent_pattern():
    from src.ai_listing.jsonld_parser import extract_material

    material = extract_material("CALL UR CORNER POCKET... 80% cotton, 20% polyester, Oversized Fit")
    assert material == "80% cotton, 20% polyester"
