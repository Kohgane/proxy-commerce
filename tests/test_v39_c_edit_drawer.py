"""tests/test_v39_c_edit_drawer.py — v39 C: 수집품목 클릭 → 인페이지 편집 드로어(새 창/원본 이동 0)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

HIST = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_list_click_opens_drawer_not_navigation():
    # 목록 클릭은 드로어 오픈(라우트 이동/새 창 아님). 썸네일·제목·편집 버튼 모두 kgp-open-drawer.
    assert "kgp-open-drawer" in HIST
    assert 'class="kgp-drawer"' in HIST and "kgp-drawer-iframe" in HIST
    # 제목/도메인이 더 이상 원본 사이트로 새 탭 이동하지 않음(원본은 드로어 '원본 보기'에서만)
    assert 'target="_blank" rel="noopener noreferrer">{{ it.domain' not in HIST
    assert "openItemDrawer" in HIST
    # 원본 보기는 드로어 안에 1개(여기만 새 탭)
    assert 'id="kgpDrawerOrigin"' in HIST and "원본 보기" in HIST


def test_preview_has_drawer_embed_mode():
    # ?drawer=1이면 콘솔 chrome 숨김 + 저장 시 부모(목록)에 postMessage
    assert "request.args.get('drawer')" in PREVIEW
    assert "preview-saved" in PREVIEW


def test_preview_route_allows_same_origin_framing(client):
    # 편집 페이지는 same-origin iframe 허용(SAMEORIGIN), 그 외는 DENY 유지(클릭재킹 방어).
    r = client.get("/seller/collect/preview/anyid?drawer=1")
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in r.headers.get("Content-Security-Policy", "")
    # 일반 페이지는 여전히 DENY
    r2 = client.get("/seller/collect/history")
    assert r2.headers.get("X-Frame-Options") == "DENY"


def test_history_renders(client):
    assert client.get("/seller/collect/history").status_code == 200
