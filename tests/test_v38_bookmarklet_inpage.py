"""tests/test_v38_bookmarklet_inpage.py — v38 #5: 북마클릿 새 창 금지 → 인페이지 소형 알림."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BM = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_bookmarklet_no_new_window():
    # 새 창/팝업/리다이렉트 금지
    assert "window.open" not in BM
    assert "_blank" not in BM
    assert "collect/receiver" not in BM   # postMessage 새 탭 경로 제거


def test_bookmarklet_background_fetch_with_token():
    # 백그라운드 fetch(/api/v1/collect/extension) + 내 토큰(Bearer)
    assert "/api/v1/collect/extension" in BM
    assert "'Bearer '+T" in BM
    # 토큰 발급 흐름(1회)
    assert "/seller/me/tokens/generate" in BM
    assert "KGP_TOKEN" in BM


def test_bookmarklet_inpage_toast():
    # 인페이지 소형 토스트(고가수집기 위치 근처) + CSP 차단 시 인페이지 안내(새 창 0)
    assert "kgpbm" in BM
    assert "position:fixed" in BM
    assert "보안정책(CSP)" in BM


def test_bookmarklet_renders(client):
    assert client.get("/seller/bookmarklet").status_code == 200
