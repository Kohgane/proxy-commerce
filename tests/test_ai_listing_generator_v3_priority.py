from __future__ import annotations


def test_jsonld_fields_override_ai_inference():
    from src.ai_listing.generator import build_listing_content, generate_title
    from src.ai_listing.price_suggester import suggest_price

    analysis = {
        "category": "패션",
        "brand": "AI Brand",
        "colors": ["블랙"],
        "keywords": ["티셔츠", "기본"],
        "estimated_price_range": {"min": 15000, "max": 45000},
        "json_ld_normalized": {
            "name": "EIGHT BALL HOODIE",
            "brand": {"name": "MARKET"},
            "category": "Hoodies",
            "description": "80% cotton, 20% polyester",
            "hasVariant": [
                {"name": "EIGHT BALL HOODIE - WOOD ASH / S", "offers": {"price": "120.00", "priceCurrency": "USD"}}
            ],
        },
        "source_price_krw": 165000,
        "source_price": {"amount": "120.00", "currency": "USD", "amount_krw": 165000, "rate": "1375"},
        "fx_rate": "1375",
    }

    listing = build_listing_content(analysis, "coupang", "kr")
    price = suggest_price(analysis, "coupang")

    assert generate_title(analysis, "coupang") == "EIGHT BALL HOODIE"
    assert listing["brand"] == "MARKET"
    assert listing["category_text"] == "후드티"
    assert "WOOD ASH" in listing["colors"]
    assert "S" in listing["sizes"]
    assert price["suggested_price_krw"] == 165000
