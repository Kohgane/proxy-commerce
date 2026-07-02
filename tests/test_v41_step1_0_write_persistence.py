"""tests/test_v41_step1_0_write_persistence.py — v41 STEP 1-0: write 영속성 근본 수리.

D-30 블로커 A: 삭제→재조회 부활. 근본=인메모리 쓰기 경로가 요청범위 캐시를 무효화 안 함 → 재조회 부활.
수리: 모든 쓰기(append/update/delete)가 캐시 무효화 + 삭제 후 재읽기 검증(write-then-verify). 실패 시 정직.
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


def _reset(ch):
    ch._in_memory[:] = []


def test_delete_invalidates_cache_within_request(client):
    """같은 요청 안에서 삭제 후 list_items 재조회 시 삭제 항목이 부활하지 않아야(캐시 무효화)."""
    import src.seller_console.collect_history_store as ch
    with client.application.test_request_context("/"):
        _reset(ch)
        ch.append(source="extension", url="u", title="A", seller_id="u1")
        iid = ch.append(source="extension", url="u2", title="B", seller_id="u1")
        # 캐시 채우기(첫 조회)
        rows1 = ch.list_items(seller_ids={"u1"})
        assert any(r["id"] == iid for r in rows1)
        # 삭제 → 같은 요청서 재조회
        ch.delete([iid], seller_ids={"u1"})
        rows2 = ch.list_items(seller_ids={"u1"})
        assert not any(r["id"] == iid for r in rows2), "삭제 항목이 캐시에서 부활함"


def test_existing_ids_write_then_verify(client):
    import src.seller_console.collect_history_store as ch
    with client.application.test_request_context("/"):
        _reset(ch)
        a = ch.append(source="extension", url="u", title="A", seller_id="u1")
        b = ch.append(source="extension", url="u2", title="B", seller_id="demo@x.kr")
        # 삭제 전: 둘 다 존재
        assert ch.existing_ids([a, b], seller_ids={"u1", "demo@x.kr"}) == {a, b}
        ch.delete([a], seller_ids={"u1", "demo@x.kr"})
        # 삭제 후: a는 사라지고 b만 남음(재읽기 검증)
        assert ch.existing_ids([a, b], seller_ids={"u1", "demo@x.kr"}) == {b}


def test_update_invalidates_cache(client):
    import src.seller_console.collect_history_store as ch
    with client.application.test_request_context("/"):
        _reset(ch)
        iid = ch.append(source="extension", url="u", title="Old", seller_id="u1")
        ch.list_items(seller_ids={"u1"})           # 캐시 채움
        ch.update(iid, seller_ids={"u1"}, title="New")
        rows = ch.list_items(seller_ids={"u1"})
        assert any(r["id"] == iid and r.get("title") == "New" for r in rows)


def test_bulk_delete_route_verifies_and_honest(client, monkeypatch):
    """라우트: 삭제 후 재읽기서 잔존하면 ok=False 정직(가짜 성공 0)."""
    import src.seller_console.collect_history_store as ch
    monkeypatch.setattr(ch, "delete", lambda *a, **k: 0)          # 삭제 0건(미영속 모사)
    monkeypatch.setattr(ch, "existing_ids", lambda *a, **k: {"x1"})  # 재읽기서 잔존
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.post("/seller/collect/bulk-delete", json={"item_ids": ["x1"]})
    d = r.get_json()
    assert d["ok"] is False and "삭제되지 않았" in d["error"]      # 정직 실패

    # 정상: 재읽기서 잔존 0 → ok
    monkeypatch.setattr(ch, "delete", lambda *a, **k: 1)
    monkeypatch.setattr(ch, "existing_ids", lambda *a, **k: set())
    r2 = client.post("/seller/collect/bulk-delete", json={"item_ids": ["x1"]})
    assert r2.get_json()["ok"] is True


def test_frontend_honest_on_delete_failure():
    from pathlib import Path
    hist = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    # 서버 ok=False면 정직 안내(가짜 성공 토스트 0) + 성공 시 서버 재조회(reload)
    assert "삭제된 항목이 없습니다" in hist or "data.error" in hist
    assert "location.reload()" in hist
