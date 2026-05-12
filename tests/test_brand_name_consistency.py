from __future__ import annotations

from pathlib import Path


def test_brand_name_meta_tags_in_base_templates():
    targets = [
        Path("src/templates/_base_app.html"),
        Path("src/seller_console/templates/_base.html"),
        Path("src/dashboard/templates/base.html"),
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "og:site_name" in text
        assert "og:title" in text
        assert "_brand_name" in text
