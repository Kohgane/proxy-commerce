from __future__ import annotations

import json
from pathlib import Path


def test_seller_icon_assets_exist():
    base = Path("src/seller_console/static")
    for name in [
        "favicon.svg",
        "favicon.ico",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
    ]:
        assert (base / name).exists()


def test_base_templates_include_favicon_links():
    targets = [
        Path("src/seller_console/templates/_base.html"),
        Path("src/templates/_base_app.html"),
        Path("src/dashboard/templates/base.html"),
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert 'rel="icon"' in text
        assert "favicon.svg" in text
        assert "favicon.ico" in text
        assert 'rel="apple-touch-icon"' in text


def test_manifest_icon_files_are_served():
    from src.order_webhook import app

    with app.test_client() as client:
        manifest_resp = client.get("/seller/static/manifest.json")
        assert manifest_resp.status_code == 200
        manifest = json.loads(manifest_resp.data)
        for icon in manifest.get("icons", []):
            icon_resp = client.get(icon["src"])
            assert icon_resp.status_code == 200
