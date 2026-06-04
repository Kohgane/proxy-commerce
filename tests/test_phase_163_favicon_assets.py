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
        "manifest.webmanifest",
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
        assert "manifest.webmanifest" in text
        assert ("?v=168" in text) or ("v='168'" in text)
        assert '#1e1b4b' in text


def test_favicon_svg_uses_orbit_globe_design():
    text = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")
    # v9: thick orbits (stroke-width 20), bright globe fill (#2a5aaa), top-half clip
    assert 'linearGradient id="bg"' in text
    assert 'clipPath id="top-half"' in text
    assert 'stroke="#fbbf24"' in text
    assert 'stroke="#a3e635"' in text
    assert '#2a5aaa' in text
    assert ">K<" not in text


def test_manifest_icon_files_are_served():
    from src.order_webhook import app

    with app.test_client() as client:
        manifest_resp = client.get("/seller/static/manifest.webmanifest")
        assert manifest_resp.status_code == 200
        manifest = json.loads(manifest_resp.data)
        for icon in manifest.get("icons", []):
            icon_resp = client.get(icon["src"])
            assert icon_resp.status_code == 200


def test_favicon_generation_script_exists():
    text = Path("scripts/gen_favicon_assets.py").read_text(encoding="utf-8")
    assert "cairosvg" in text
    assert "favicon.svg" in text


def test_public_templates_use_cache_busted_favicon_links():
    targets = [
        Path("src/auth/templates/auth/login.html"),
        Path("src/auth/templates/auth/signup.html"),
        Path("src/auth/templates/auth/magic_link_fallback.html"),
        Path("src/auth/templates/auth/magic_link_request.html"),
        Path("src/auth/templates/auth/diagnostic_token_issued.html"),
        Path("src/auth/templates/auth/reset.html"),
        Path("src/onboarding/templates/onboarding.html"),
        Path("src/legal/templates/legal/privacy.html"),
        Path("src/legal/templates/legal/terms.html"),
        Path("src/shop/templates/shop/base.html"),
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "favicon.svg?v=168" in text
        assert "favicon.ico?v=168" in text
        assert "apple-touch-icon.png?v=168" in text
        assert "manifest.webmanifest?v=168" in text
        assert 'content="#1e1b4b"' in text
