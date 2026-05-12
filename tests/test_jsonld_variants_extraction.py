from __future__ import annotations


def test_extract_size_color_from_name_handles_dash_and_slash():
    from src.ai_listing.jsonld_parser import extract_size_color_from_name

    parsed = extract_size_color_from_name("EIGHT BALL HOODIE - WOOD ASH / S")
    assert parsed["color"] == "WOOD ASH"
    assert parsed["size"] == "S"


def test_extract_variants_reads_explicit_fields_and_identifiers():
    from src.ai_listing.jsonld_parser import extract_variants

    variants = extract_variants([
        {
            "name": "EIGHT BALL HOODIE • MALACHITE GREEN • XXL",
            "sku": "SKU-XXL-GREEN",
            "gtin13": "1234567890123",
            "offers": {"price": "120.00", "priceCurrency": "USD"},
        }
    ])
    assert variants[0]["color"] == "MALACHITE GREEN"
    assert variants[0]["size"] == "XXL"
    assert variants[0]["sku"] == "SKU-XXL-GREEN"
    assert variants[0]["gtin"] == "1234567890123"
