"""tests/test_v43_1_delete_persist.py — v43-1: 삭제 부활 × 자동 새로고침.

삭제=서버 커밋+재조회 확인(v42 1-4). 폴링 여러 번 지나도 부활 0. 삭제 요청 중엔 폴링 반영 보류.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _seed(n):
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    ids = []
    for i in range(n):
        ids.append(ch.append(source="extension", url=f"https://temu.com/g-{i:015d}.html",
                             title=f"item{i}", seller_id="u1"))
    return ids


def test_delete_persists_no_resurrection_across_polls(client, monkeypatch):
    """삭제 후 목록/카운트를 여러 번(폴링) 재조회해도 삭제분이 되돌아오지 않는다."""
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(views, "_seller_id", lambda: "u1")
    ids = _seed(5)
    # 2건 삭제
    r = client.post("/seller/collect/bulk-delete", json={"item_ids": ids[:2]})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["deleted"] == 2

    from src.seller_console import collect_history_store as ch
    # 폴링을 5번 흉내내 반복 재조회 — 삭제분(ids[:2])이 절대 부활하지 않음.
    for _ in range(5):
        remaining = {it["id"] for it in ch.list_items(seller_ids={"u1"})}
        assert ids[0] not in remaining and ids[1] not in remaining
        cnt = client.get("/seller/collect/history/count").get_json()
        assert cnt["ok"] is True and cnt["total"] == 3


def test_delete_write_then_verify_honest_failure(client, monkeypatch):
    """삭제가 서버에 반영 안 되면(잔존) 정직 실패(가짜 성공 금지)."""
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(views, "_seller_id", lambda: "u1")
    ids = _seed(3)
    from src.seller_console import collect_history_store as ch
    # delete가 아무것도 못 지운 것처럼(잔존) 만들고 existing_ids가 여전히 반환 → 정직 실패.
    monkeypatch.setattr(ch, "delete", lambda item_ids, **kw: 0)
    monkeypatch.setattr(ch, "existing_ids", lambda item_ids, **kw: set(item_ids))
    r = client.post("/seller/collect/bulk-delete", json={"item_ids": [ids[0]]})
    assert r.status_code == 200
    assert r.get_json()["ok"] is False   # 부활 위험 = 정직 실패


def test_template_poll_holds_during_delete():
    html = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    # 폴링 apply/poll이 삭제 중(_kgpDeleting) 보류 + 삭제가 플래그 설정.
    assert "window._kgpDeleting" in html
    assert "if (window._kgpDeleting || reloading) return;" in html
    assert "reloading || window._kgpDeleting) return;" in html
    # 서버 총건수 하강 시 기준선 하강(부활 오탐 방지).
    assert "if (total < initialTotal) { initialTotal = total; return; }" in html
