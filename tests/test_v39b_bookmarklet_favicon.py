"""tests/test_v39b_bookmarklet_favicon.py — v39 B: 북마클릿 파비콘/주입 UI 마크 + 정직 폴백.

B-1(확실): 북마클릿이 inject하는 토스트 아이콘 = 우리 브릿지 마크(우리가 DOM을 그림 → 100% 우리 마크).
B-2(최대치+정직): 설치 페이지 파비콘 = 신규 마크(상속 경로), 드래그 텍스트 '고가수집기',
  회색 아이콘일 수 있다는 정직 안내 + 1차 권장=확장.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_install_page_favicon_is_new_bridge_mark(client):
    # 설치 페이지는 _base.html 상속 → 신규 브릿지 파비콘(v=179), globe 0
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/bookmarklet").get_data(as_text=True)
    assert "favicon.ico?v=179" in html or "favicon.svg?v=179" in html
    assert "globe" not in BASE.lower()


def test_drag_anchor_text_is_gogasujipgi_with_mark():
    # 드래그 앵커 = '고가수집기' 텍스트 + 우리 마크 이미지(북마크 이름 상속)
    assert ">고가수집기</a>" in TPL
    assert 'favicon-32.png?v=179' in TPL          # 앵커/토스트에 우리 마크
    assert ">수집</a>" not in TPL                  # 옛 '수집' 단독 라벨 폐기


def test_injected_toast_carries_our_mark():
    # B-1: 인페이지 토스트가 우리 favicon(브릿지 마크)을 img로 주입
    assert "kgpbm" in TPL and "favicon-32.png" in TPL
    # 토스트는 텍스트 노드 분리(아이콘 + 메시지)
    assert "kgpbmx" in TPL


def test_honest_gray_icon_fallback_recommends_extension():
    assert "회색" in TPL                            # 회색 아이콘 가능성 정직 고지
    assert "고가수집기 확장" in TPL or "크롬 확장" in TPL
    assert "/seller/extension" in TPL               # 1차 권장 = 확장


def test_no_new_window_still_holds():
    # 새 창/팝업 0(v38 #5 유지) — window.open 미사용
    assert "window.open" not in TPL
