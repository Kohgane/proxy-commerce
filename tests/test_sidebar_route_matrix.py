from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


HREF_PATTERN = re.compile(r'href="([^"]+)"')
SIDEBAR_TEMPLATE = Path(__file__).resolve().parent.parent / "src" / "seller_console" / "templates" / "_base.html"


def _extract_links(html: str) -> list[str]:
    return sorted(
        {
            href
            for href in HREF_PATTERN.findall(html)
            if href.startswith("/") and not href.startswith("//")
        }
    )


def _template_sidebar_links() -> list[str]:
    return _extract_links(SIDEBAR_TEMPLATE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh

    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


def test_sidebar_menu_links_exist_in_dashboard_html(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    expected = [url for url in _template_sidebar_links() if url.startswith("/seller/")]
    for url in expected:
        assert url in html, f"사이드바 메뉴에 {url}이 누락"


def test_sidebar_link_route_is_not_404(client):
    for path in _template_sidebar_links():
        resp = client.get(path)
        assert resp.status_code != 404, f"사이드바 메뉴 {path}는 존재하지만 라우트가 404"
