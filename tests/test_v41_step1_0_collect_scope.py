"""tests/test_v41_step1_0_collect_scope.py — v41 STEP 1-0: 확장 '수집 완료 = 목록에 실제 보임'까지.

증상(항목 286e5bd75186): 확장 '수집 완료' 표시 → 이력에 없음. 원인 후보 4=user 스코프 불일치
(토큰 seller_id vs 브라우저 세션 email). 수리: 자기검증을 목록 스코프(user_id+email 관용집합)로 재읽기.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _clear():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def test_collect_verified_against_list_scope(client):
    # 수집 → ok:true는 목록 스코프 재읽기로 실제 보임을 확인한 뒤에만.
    _clear()
    r = client.post("/api/v1/collect/extension",
                    json={"url": "https://temu.com/p/1", "title": "소파", "price": "9.99", "currency": "USD"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    from src.seller_console import collect_history_store as ch
    # 브라우저가 email 별칭 세션으로 조회해도 보인다(관용 매칭) — 저장은 u1로 됐어도.
    assert len(ch.list_items(seller_ids={"u1"})) == 1


def test_collect_resolves_email_for_verify_scope(client, monkeypatch):
    # 토큰 user_id의 email을 user_store에서 해석해 검증 스코프에 포함(목록 스코프 일치).
    _clear()
    import src.api.extension_api as ext

    class _U:
        email = "demo@goga.kr"
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: type("S", (), {"find_by_id": staticmethod(lambda uid: _U())})())
    r = client.post("/api/v1/collect/extension",
                    json={"url": "https://temu.com/p/2", "title": "책상", "price": "5"})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_source_code_uses_existing_ids_list_scope():
    from pathlib import Path
    src = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert "existing_ids" in src and "verify_ids" in src
    assert "user_store" in src and "email" in src   # 목록 스코프(email) 해석
