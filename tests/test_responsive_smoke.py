"""tests/test_responsive_smoke.py — 모바일 반응형 점검 (Phase 147)."""
import pytest


def test_base_html_has_viewport_meta():
    """_base.html에 viewport 메타태그가 존재해야 한다."""
    with open("src/seller_console/templates/_base.html", encoding="utf-8") as f:
        content = f.read()
    assert 'name="viewport"' in content
    assert "width=device-width" in content


def test_base_html_has_manifest_link():
    """_base.html에 PWA manifest 링크가 존재해야 한다."""
    with open("src/seller_console/templates/_base.html", encoding="utf-8") as f:
        content = f.read()
    assert 'rel="manifest"' in content


def test_base_html_has_hamburger_toggle():
    """_base.html에 모바일 햄버거 메뉴 버튼이 있어야 한다."""
    with open("src/seller_console/templates/_base.html", encoding="utf-8") as f:
        content = f.read()
    assert "sidebarToggle" in content
    assert "☰" in content


def test_base_html_has_drawer_sidebar():
    """사이드바가 모바일 drawer 클래스를 지원해야 한다."""
    with open("src/seller_console/templates/_base.html", encoding="utf-8") as f:
        content = f.read()
    assert "sidebarDrawer" in content


def test_seller_css_has_mobile_drawer():
    """seller.css에 모바일 drawer 스타일이 있어야 한다."""
    with open("src/seller_console/static/seller.css", encoding="utf-8") as f:
        content = f.read()
    assert ".sidebar.show" in content
    assert "max-width: 768px" in content or "max-width:768px" in content


def test_seller_css_has_min_touch_target():
    """버튼 최소 터치 영역 44px이 seller.css에 설정되어야 한다."""
    with open("src/seller_console/static/seller.css", encoding="utf-8") as f:
        content = f.read()
    assert "44px" in content


def test_seller_css_has_table_responsive():
    """table overflow-x:auto 래퍼가 seller.css에 있어야 한다."""
    with open("src/seller_console/static/seller.css", encoding="utf-8") as f:
        content = f.read()
    assert "overflow-x" in content


def test_base_html_has_service_worker_registration():
    """_base.html에 Service Worker 등록 스크립트가 있어야 한다."""
    with open("src/seller_console/templates/_base.html", encoding="utf-8") as f:
        content = f.read()
    assert "serviceWorker" in content
    assert "register" in content


def test_seller_page_renders_with_test_client():
    """셀러 콘솔 페이지가 정상적으로 렌더링되어야 한다."""
    from src.order_webhook import app
    with app.test_client() as client:
        resp = client.get("/seller/dashboard")
        # 리다이렉트이거나 200 OK 모두 허용
        assert resp.status_code in (200, 302, 301)


def test_me_notifications_route_exists():
    """푸시 알림 설정 페이지 라우트가 등록되어야 한다."""
    from src.order_webhook import app
    assert "seller_console.me_notifications" in app.view_functions


def test_inventory_omni_route_exists():
    """옴니채널 재고 라우트가 등록되어야 한다."""
    from src.order_webhook import app
    assert "seller_console.inventory_omni" in app.view_functions
