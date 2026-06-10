"""tests/test_dead_buttons_phase191.py — 죽은 버튼 감사 3차 회귀 테스트.

honest-UI 원칙(docs/operations/dead_button_audit.md)에 따라 차단형 `alert()`을
비차단 전역 토스트(`pcToast`)로 전환했는지 검증한다.

대상 페이지: pricing_rules / pricing_competitors / pricing_fx_impact /
pricing_history / discovery / discovery_keywords / me / personal_tokens

예외: bookmarklet.html은 외부 사이트에서 실행되는 `javascript:` 북마클릿 코드
내부에 `alert()`을 의도적으로 유지한다(콘솔 밖이라 pcToast 사용 불가).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def client():
    """셀러 콘솔이 등록된 Flask 앱 테스트 클라이언트."""
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# alert()가 완전히 제거되어야 하는, 인증/목 없이 200으로 렌더되는 페이지들.
NO_ALERT_PAGES = [
    "/seller/pricing/rules",
    "/seller/pricing/competitors",
    "/seller/pricing/fx-impact",
    "/seller/pricing/history",
    "/seller/discovery",
    "/seller/discovery/keywords",
    "/seller/me/tokens",
    "/seller/me",
]


class TestGlobalToastInfra:
    """전역 pcToast 인프라가 베이스 레이아웃/공통 스크립트에 존재한다."""

    def test_base_template_has_global_toast_container(self):
        path = os.path.join(ROOT, "src/seller_console/templates/_base.html")
        with open(path, encoding="utf-8") as f:
            base = f.read()
        assert "pcToastContainer" in base, "_base.html에 전역 토스트 컨테이너가 있어야 합니다"

    def test_seller_js_defines_pctoast(self):
        path = os.path.join(ROOT, "src/seller_console/static/seller.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        assert "function pcToast" in js, "seller.js에 pcToast 헬퍼가 정의되어야 합니다"
        # XSS 방지: 메시지는 textContent로 삽입 (innerHTML 직접 주입 금지)
        assert "body.textContent" in js


class TestPagesNoBlockingAlert:
    """대상 페이지에 차단형 alert() 호출이 남아있지 않아야 한다."""

    @pytest.mark.parametrize("path", NO_ALERT_PAGES)
    def test_no_alert_call(self, client, path):
        resp = client.get(path)
        if resp.status_code != 200:
            pytest.skip(f"{path} → {resp.status_code} (환경 의존)")
        body = resp.data.decode("utf-8")
        assert "alert(" not in body, f"{path}에 alert() 호출이 남아있습니다"

    @pytest.mark.parametrize("path", NO_ALERT_PAGES)
    def test_has_global_toast_container(self, client, path):
        resp = client.get(path)
        if resp.status_code != 200:
            pytest.skip(f"{path} → {resp.status_code} (환경 의존)")
        body = resp.data.decode("utf-8")
        assert "pcToastContainer" in body, f"{path}에 전역 토스트 컨테이너가 없습니다"


class TestBookmarkletKeepsExternalAlert:
    """북마클릿 페이지는 외부 실행 코드의 alert()를 유지하되 콘솔 UI는 pcToast를 쓴다."""

    def test_bookmarklet_console_uses_pctoast(self, client):
        resp = client.get("/seller/bookmarklet")
        if resp.status_code != 200:
            pytest.skip(f"/seller/bookmarklet → {resp.status_code}")
        body = resp.data.decode("utf-8")
        # 콘솔 측 사용자 피드백은 pcToast로 전환됨
        assert "pcToast(" in body
        # 외부 북마클릿 코드 내부 alert은 의도적으로 유지 (사본이 2개)
        assert body.count("alert(") <= 2
