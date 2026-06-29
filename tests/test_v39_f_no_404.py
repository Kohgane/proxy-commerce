"""tests/test_v39_f_no_404.py — v39 F: 수집 상세 404 박멸 → '수집 실패' 빈 상태(200)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_missing_preview_is_failure_state_not_404(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/collect/preview/does-not-exist-zzz")
    body = r.get_data(as_text=True)
    assert r.status_code == 200                      # 404 아님
    assert "수집 실패" in body and "다시 수집하기" in body
    assert 'href="/seller/collect"' in body          # 다시 수집
    assert "/seller/collect/history" in body         # 수집 이력으로


def test_missing_preview_drawer_mode_hides_chrome(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/collect/preview/missing?drawer=1")
    assert r.status_code == 200
    assert ".console-sidebar" in r.get_data(as_text=True)   # 드로어 모드 chrome 숨김 스타일


def test_route_no_abort_404():
    # collect_preview_by_id가 더 이상 abort(404)로 신뢰 깨지 않음
    seg = VIEWS[VIEWS.index("def collect_preview_by_id"):VIEWS.index("def collect_preview_by_id") + 900]
    assert "abort(404)" not in seg
    assert "collect_preview_missing.html" in seg


def test_e2e_extension_collect_then_preview_ok(client):
    # 확장 경로: 수집 → 같은 user 상세 드로어 200(정상 케이스 — 404 아님)
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    r = client.post("/api/v1/collect/extension", json={"url": "https://temu.com/p", "title": "테스트 상품"})
    item_id = r.get_json()["item_id"]
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    rp = client.get(f"/seller/collect/preview/{item_id}?drawer=1")
    assert rp.status_code == 200 and "수집 상품 편집" in rp.get_data(as_text=True)
