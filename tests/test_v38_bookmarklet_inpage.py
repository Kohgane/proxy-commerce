"""tests/test_v38_bookmarklet_inpage.py — v38 #5: 북마클릿 새 창 금지 → 인페이지 소형 알림."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BM = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
# 파일 가져오기 방식 전환(#424): 인페이지 fetch/토스트 코드는 서버 헬퍼(_bookmarklet_js)가 생성 → views.py.
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_bookmarklet_no_new_window():
    # 새 창/팝업/리다이렉트 금지 (템플릿·서버 북마클릿 코드 둘 다)
    assert "window.open" not in BM
    assert "_blank" not in BM
    assert "collect/receiver" not in BM   # postMessage 새 탭 경로 제거
    assert "window.open" not in VIEWS.split("_bookmarklet_js")[1][:2500]


def test_bookmarklet_background_fetch_with_token():
    # 백그라운드 fetch(/api/v1/collect/extension) + 내 토큰(Bearer) — 서버가 baked
    assert "/api/v1/collect/extension" in VIEWS
    assert "'Bearer '+T" in VIEWS
    # 토큰 발급(Supabase 1단계)은 파일 받기 라우트에서
    assert "/seller/bookmarklet/file" in BM
    assert "generate_token" in VIEWS


def test_bookmarklet_inpage_toast():
    # 인페이지 소형 토스트 + CSP 차단 시 인페이지 안내(새 창 0) — 서버 북마클릿 코드
    assert "kgpbm" in VIEWS
    assert "position:fixed" in VIEWS
    assert "보안정책(CSP)" in VIEWS


def test_bookmarklet_renders(client):
    assert client.get("/seller/bookmarklet").status_code == 200
