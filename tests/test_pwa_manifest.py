"""tests/test_pwa_manifest.py — PWA 매니페스트 점검 (Phase 164)."""
import json


def test_manifest_json_valid():
    """manifest.webmanifest이 유효한 JSON이어야 한다."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        manifest = json.load(f)
    assert isinstance(manifest, dict)


def test_manifest_has_name():
    """manifest.webmanifest에 name 필드가 있어야 한다 (KOHgogane)."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("name") == "KOHgogane"


def test_manifest_has_short_name():
    """manifest.webmanifest에 short_name 필드가 있어야 한다 (Percentiii)."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("short_name") == "Percentiii"


def test_manifest_has_icons():
    """manifest.webmanifest에 icons 필드가 있어야 한다 (192/512)."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        manifest = json.load(f)
    icons = manifest.get("icons", [])
    assert len(icons) >= 2
    sizes = {icon["sizes"] for icon in icons}
    assert "192x192" in sizes
    assert "512x512" in sizes
    srcs = {icon["src"] for icon in icons}
    assert "/seller/static/icon-192.png" in srcs
    assert "/seller/static/icon-512.png" in srcs


def test_manifest_has_theme_color():
    """manifest.webmanifest에 theme_color가 있어야 한다."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("theme_color") == "#020010"


def test_manifest_has_background_color():
    """manifest.webmanifest에 background_color가 있어야 한다."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest.get("background_color") == "#020010"


def test_manifest_display_standalone():
    """manifest.webmanifest의 display가 standalone이어야 한다."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
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
    """Flask 앱에서 manifest.webmanifest이 서빙되어야 한다."""
    from src.order_webhook import app
    with app.test_client() as client:
        resp = client.get("/seller/static/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("name") == "KOHgogane"


def test_legacy_manifest_json_matches_webmanifest():
    """manifest.json 백워드 호환본이 manifest.webmanifest와 동기화되는지 확인."""
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        canonical = json.load(f)
    with open("src/seller_console/static/manifest.json", encoding="utf-8") as f:
        legacy = json.load(f)
    assert legacy == canonical
