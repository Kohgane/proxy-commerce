"""tests/test_v40_a_root_favicon_bm_install.py — v40-A: 도메인 루트 파비콘 + /bm/install 단축.

크롬은 북마클릿 드래그 시 페이지 파비콘을 상속한다. 루트 /favicon.ico가 404(회색)면 상속도 회색 →
브릿지 마크 favicon.ico를 루트에서 서빙(상속 보강). /bm/install은 설치 페이지(브릿지 파비콘) 단축 경로.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_root_favicon_serves_bridge_ico(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert "image" in r.headers.get("Content-Type", "")
    # 정적 브릿지 favicon.ico와 동일 바이트(브릿지 마크)
    from pathlib import Path
    ico = Path("src/seller_console/static/favicon.ico").read_bytes()
    assert r.data == ico and len(r.data) > 0


def test_bm_install_redirects_to_bookmarklet(client):
    r = client.get("/bm/install")
    assert r.status_code == 302
    assert "/seller/bookmarklet" in r.headers.get("Location", "")


def test_bookmarklet_page_still_has_bridge_favicon_and_iconly(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/bookmarklet").get_data(as_text=True)
    assert "favicon.ico?v=179" in html or "favicon-48.png" in html   # 설치 페이지 파비콘=브릿지(v39-B)
    from pathlib import Path
    tpl = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
    assert 'title="&#8203;"' in tpl                                   # 글자 없이 아이콘만(제로폭)
