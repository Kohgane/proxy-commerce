from __future__ import annotations

from pathlib import Path


def test_phase_165_preview_assets_exist():
    base = Path("src/seller_console/static/previews/phase165")
    expected = [
        "orbit_lime.svg",
        "orbit_lime_512.png",
        "orbit_lime_32.png",
        "orbit_gold.svg",
        "orbit_gold_512.png",
        "orbit_gold_32.png",
        "phase165_contact_sheet.png",
        "index.html",
    ]
    for name in expected:
        assert (base / name).exists()


def test_previews_root_index_links_phase_165_static_url():
    text = Path("src/seller_console/static/previews/index.html").read_text(encoding="utf-8")
    assert "/seller/static/previews/phase165/index.html" in text


def test_phase_165_previews_served_via_seller_static_route():
    from src.order_webhook import app

    with app.test_client() as client:
        files = {
            "/seller/static/previews/phase165/orbit_lime_512.png": b"\x89PNG\r\n\x1a\n",
            "/seller/static/previews/phase165/orbit_lime_32.png": b"\x89PNG\r\n\x1a\n",
            "/seller/static/previews/phase165/orbit_gold_512.png": b"\x89PNG\r\n\x1a\n",
            "/seller/static/previews/phase165/orbit_gold_32.png": b"\x89PNG\r\n\x1a\n",
            "/seller/static/previews/phase165/phase165_contact_sheet.png": b"\x89PNG\r\n\x1a\n",
        }
        for url, prefix in files.items():
            resp = client.get(url)
            assert resp.status_code == 200
            assert resp.data[: len(prefix)] == prefix

        index_resp = client.get("/seller/static/previews/phase165/index.html")
        assert index_resp.status_code == 200
        assert b"Phase 165 Orbit Favicon Previews" in index_resp.data
