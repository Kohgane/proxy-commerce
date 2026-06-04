from __future__ import annotations

from pathlib import Path


def test_phase_164_preview_assets_exist():
    base = Path("src/seller_console/static/previews/phase164")
    expected = [
        "cand_a.svg",
        "cand_b.svg",
        "cand_c.svg",
        "cand_d.svg",
        "cand_a_512.png",
        "cand_a_32.png",
        "cand_a_32_simplified.png",
        "cand_b_512.png",
        "cand_b_32.png",
        "cand_c_512.png",
        "cand_c_32.png",
        "cand_d_512.png",
        "cand_d_32.png",
        "previews_contact_sheet.png",
        "index.html",
    ]
    for name in expected:
        assert (base / name).exists()
    assert Path("src/seller_console/static/previews/index.html").exists()


def test_phase_164_previews_served_via_static_route():
    from src.order_webhook import app

    with app.test_client() as client:
        resp = client.get("/seller/static/previews/phase164/cand_a_512.png")
        assert resp.status_code == 200
        assert resp.data[:8] == b"\x89PNG\r\n\x1a\n"

        index_resp = client.get("/seller/static/previews/phase164/index.html")
        assert index_resp.status_code == 200
        assert b"Phase 164 Favicon Previews" in index_resp.data
