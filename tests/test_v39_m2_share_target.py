"""tests/test_v39_m2_share_target.py — v39-M M2: 공유로 수집(Web Share Target) → 편집 드로어 진입.

manifest share_target.action = /seller/collect/share. 공유 URL 수집 성공 시 편집 화면(drawer)으로 redirect.
북마클릿 /collect/quick은 '수집됨' 확인 유지(가짜 성공 0 · 실패는 정직 안내).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

STATIC = Path("src/seller_console/static")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("fn", ["manifest.json", "manifest.webmanifest"])
def test_manifest_share_target_points_to_share_route(fn):
    m = json.loads((STATIC / fn).read_text(encoding="utf-8"))
    st = m["share_target"]
    assert st["action"] == "/seller/collect/share"
    # M3(오너 2026-09-28): 안드로이드 공유 시트는 **POST 폼**(title·text·url). 아이폰 단축어는 같은 라우트에 GET ?text=.
    assert st["method"] == "POST" and st["enctype"] == "application/x-www-form-urlencoded"
    assert st["params"] == {"title": "title", "text": "text", "url": "url"}


def test_share_success_shows_result_with_editor_link(client, monkeypatch):
    """M3(오너 2026-09-28): 성공하면 편집 드로어로 튕기지 않고 **결과 화면** — 편집은 버튼 하나.
    (수집은 붙여넣기와 같은 판단점 `collect_input` → 정상 수집이면 `collect_one_url`.)"""
    import src.api.extension_api as ext
    import src.seller_console.collect_history_store as _chs
    monkeypatch.setattr(_chs, "find_by_product_key", lambda *a, **k: None)
    monkeypatch.setattr(ext, "collect_one_url", lambda url, seller_id="", source="": {
        "ok": True, "url": url, "item_id": "shareitem1", "title": "티"})
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/collect/share?u=https://temu.com/p/abc", follow_redirects=False)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'data-state="collected"' in body and "티" in body
    assert "/seller/collect/preview/shareitem1?drawer=1&from=share" in body


def test_share_failure_is_honest_not_fake(client, monkeypatch):
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_collect_real_draft", lambda url, translate=True: None)
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    # 메타도 없으면 가짜 성공 아닌 정직 안내(편집 리다이렉트 없음)
    r = client.get("/seller/collect/share?u=https://temu.com/p/x", follow_redirects=False)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "고가수집기" in body or "읽지 못" in body


def test_bookmarklet_quick_still_shows_confirmation(client, monkeypatch):
    # 북마클릿 흐름은 편집으로 리다이렉트하지 않고 '수집됨' 확인 페이지(오너 결정 유지)
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_collect_real_draft",
                        lambda url, translate=True: {"title": "T", "title_ko": "티", "price": "1",
                                                     "currency": "USD", "images": [], "source": "bookmarklet"})
    monkeypatch.setattr(views, "_register_discovery_candidate_from_collection", lambda *a, **k: None)
    import src.seller_console.collect_history_store as _chs; monkeypatch.setattr(_chs, "append", lambda **k: "bm1")
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/collect/quick?u=https://temu.com/p/abc", follow_redirects=False)
    assert r.status_code == 200            # 리다이렉트 아님 — 확인 페이지
    assert "수집 이력" in r.get_data(as_text=True)
