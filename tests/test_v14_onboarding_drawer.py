"""tests/test_v14_onboarding_drawer.py — v14 P0 가드: 모바일 드로어 닫기 + 온보딩 정직 자동체크."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
CSS = Path("src/seller_console/static/seller.css").read_text(encoding="utf-8")
WIZ = Path("src/seller_console/templates/onboarding_wizard.html").read_text(encoding="utf-8")


def test_drawer_overlay_closes_outside_tap():
    # 오버레이가 실제로 화면을 덮도록 base 규칙(position:fixed) + onclick 닫기
    assert "sidebar-overlay" in BASE
    assert 'onclick="closeSidebar()"' in BASE
    assert "position: fixed" in CSS and ".sidebar-overlay" in CSS
    # 스크롤 잠금 + ESC + 스와이프 닫기
    assert "kgp-drawer-open" in BASE and "kgp-drawer-open" in CSS
    assert "Escape" in BASE
    assert "touchend" in BASE and "closeSidebar()" in BASE


def test_onboarding_no_new_tab_inplace():
    # v14: 새 탭/새 창 금지 — window.open(_blank) 제거
    assert "window.open" not in WIZ
    assert "_blank" not in WIZ


def test_onboarding_no_fake_completion():
    # 링크 클릭만으로 완료 처리(markDone) 금지 — 실제 상태로만 자동 체크
    assert "markDone" not in WIZ
    assert "autoDone: LOGGED_IN" in WIZ          # 구글 로그인 실제 완료 반영
    assert "autoDone: MARKETS > 0" in WIZ         # 마켓 연결 실제 완료 반영


def test_onboarding_intro_explains_market_connect():
    assert "‘마켓 연동’이란" in WIZ or "마켓 연동’이란" in WIZ


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_wizard_renders(client):
    html = client.get("/seller/start").get_data(as_text=True)
    assert "마켓 연동" in html and "/auth/google/start" in html
