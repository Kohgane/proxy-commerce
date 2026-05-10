"""tests/test_sidebar_links.py — 사이드바 X 라우트 매핑 일치 확인 (Phase 144)."""
from __future__ import annotations

import re
import pytest


SIDEBAR_LINKS = [
    ("/seller/sourcing/watches", "소싱"),
    ("/seller/sourcing/candidates", "후보"),
    ("/seller/listing/history", "등록 이력"),
    ("/seller/media/queue", "이미지"),
    ("/seller/ads/campaigns", "광고"),
    ("/seller/pricing/rules", "가격"),
    ("/seller/cs/inbox", "CS"),
    ("/seller/analytics", "BI"),
]


@pytest.fixture(scope="module")
def sidebar_html():
    """_base.html 내용."""
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "src", "seller_console", "templates", "_base.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def app():
    import os
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    return wh.app


class TestSidebarLinksPresent:
    """사이드바에 Phase 143/144 메뉴 항목이 존재하는지 확인."""

    @pytest.mark.parametrize("url,label_hint", SIDEBAR_LINKS)
    def test_sidebar_contains_link(self, sidebar_html, url, label_hint):
        assert url in sidebar_html, (
            f"사이드바에 '{url}' 링크 누락 — _base.html에 메뉴 추가 필요"
        )

    def test_sourcing_watches_in_sidebar(self, sidebar_html):
        assert "/seller/sourcing/watches" in sidebar_html

    def test_sourcing_candidates_in_sidebar(self, sidebar_html):
        assert "/seller/sourcing/candidates" in sidebar_html

    def test_listing_history_in_sidebar(self, sidebar_html):
        assert "/seller/listing/history" in sidebar_html

    def test_media_queue_in_sidebar(self, sidebar_html):
        assert "/seller/media/queue" in sidebar_html

    def test_ads_campaigns_in_sidebar(self, sidebar_html):
        assert "/seller/ads/campaigns" in sidebar_html


class TestSidebarLinksMatchRoutes:
    """사이드바 링크 ↔ 실제 라우트 매핑 일치 확인."""

    @pytest.mark.parametrize("url,label_hint", SIDEBAR_LINKS)
    def test_sidebar_link_route_exists(self, app, url, label_hint):
        """사이드바 링크 URL에 해당하는 라우트가 앱에 등록되어 있는지 확인."""
        with app.test_request_context():
            try:
                from werkzeug.exceptions import MethodNotAllowed
            except ImportError:
                MethodNotAllowed = Exception
            try:
                from werkzeug.routing import RequestRedirect
            except ImportError:
                RequestRedirect = Exception
            try:
                from werkzeug.routing import NotFound
            except ImportError:
                from werkzeug.exceptions import NotFound
            try:
                adapter = app.url_map.bind("localhost")
                endpoint, _ = adapter.match(url, method="GET")
                assert endpoint, f"사이드바 링크 {url} → 등록된 라우트 없음"
            except NotFound:
                pytest.fail(f"사이드바 링크 {url} → 404 (라우트 미등록)")
            except (RequestRedirect, MethodNotAllowed):
                pass  # 리다이렉트/POST-only는 허용
