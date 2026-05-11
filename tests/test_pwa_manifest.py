"""tests/test_pwa_manifest.py — PWA 매니페스트 점검 (Phase 147)."""
import json
import pytest


def test_manifest_json_valid():
    """manifest.json이 유효한 JSON이어야 한다."""
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert isinstance(manifest, dict)


def test_manifest_has_name():
    """manifest.json에 name 필드가 있어야 한다 (Proxy Commerce)."""
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("name") == "Proxy Commerce"


def test_manifest_has_short_name():
    """manifest.json에 short_name 필드가 있어야 한다 (Percentiii)."""
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("short_name") == "Percentiii"


def test_manifest_has_icons():
    """manifest.json에 icons 필드가 있어야 한다 (192/512)."""
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    icons = manifest.get("icons", [])
    assert len(icons) >= 2
    sizes = {icon["sizes"] for icon in icons}
    assert "192x192" in sizes
    assert "512x512" in sizes


def test_manifest_has_theme_color():
    """manifest.json에 theme_color가 있어야 한다."""
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert "theme_color" in manifest


def test_manifest_has_background_color():
    """manifest.json에 background_color가 있어야 한다."""
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert "background_color" in manifest


def test_manifest_display_standalone():
    """manifest.json의 display가 standalone이어야 한다."""
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("display") == "standalone"


def test_service_worker_js_exists():
    """sw.js가 존재하고 기본 이벤트 리스너를 포함해야 한다."""
    with open("src/seller_console/static/sw.js", encoding="utf-8") as f:
        content = f.read()
    assert "install" in content
    assert "activate" in content
    assert "fetch" in content


def test_service_worker_handles_push():
    """sw.js가 Web Push 이벤트를 처리해야 한다."""
    with open("src/seller_console/static/sw.js", encoding="utf-8") as f:
        content = f.read()
    assert "push" in content
    assert "showNotification" in content


def test_service_worker_handles_notification_click():
    """sw.js가 notificationclick 이벤트를 처리해야 한다."""
    with open("src/seller_console/static/sw.js", encoding="utf-8") as f:
        content = f.read()
    assert "notificationclick" in content


def test_manifest_served_via_app():
    """Flask 앱에서 manifest.json이 서빙되어야 한다."""
    from src.order_webhook import app
    with app.test_client() as client:
        resp = client.get("/seller/seller/static/manifest.json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("name") == "Proxy Commerce"
