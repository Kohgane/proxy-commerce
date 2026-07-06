"""tests/test_v24_collect_history_persist.py — v24 P0: 수집 성공인데 이력 0 버그 가드.

원인: append가 시트 쓰기 실패 시 _in_memory로 폴백하는데, list_items/get은 시트만 읽어
폴백 행을 못 봤다 → '수집 완료' 토스트는 뜨는데 이력 0(가짜 성공처럼 보임).
수정: 조회를 시트+인메모리 합집합(_all_rows)으로 → 저장 위치와 무관하게 같은 워커에서 보인다.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def store(monkeypatch):
    mod = importlib.import_module("src.seller_console.collect_history_store")
    # 깨끗한 인메모리
    mod._in_memory[:] = []
    yield mod
    mod._in_memory[:] = []


def test_append_visible_in_history_inmemory(store):
    """PG-only 전환 후: 인메모리(개발/테스트) 경로에서 append→목록/단건/카운터 즉시 반영.
    (Sheets 쓰기 실패 폴백 개념은 제거 — PG는 트랜잭션 커밋으로 durable.)"""
    item_id = store.append(
        source="extension", url="https://taobao.com/item/123",
        title="테스트 상품", price="100", currency="CNY", seller_id="u1",
    )
    assert item_id
    ids = {"u1", "u1@example.com"}
    items = store.list_items(days=30, seller_ids=ids)
    assert len(items) == 1 and items[0]["id"] == item_id
    assert store.get(item_id, seller_ids=ids) is not None
    summ = store.summary(days=30, seller_ids=ids)
    assert summ["total"] == 1 and summ["by_source"]["extension"] == 1


def test_lenient_seller_id_alias_matching(store, monkeypatch):
    """저장 seller_id(user_id)와 조회 식별자(email 별칭)가 어긋나도 본인 이력은 보인다(v9)."""
    monkeypatch.setattr(store, "_SHEET_ID", None, raising=False)
    item_id = store.append(source="extension", url="https://x.com/p", title="t", seller_id="u1")
    # 조회는 user_id+email 집합으로(별칭 관용)
    items = store.list_items(days=30, seller_ids={"u1", "buyer@x.com"})
    assert len(items) == 1 and items[0]["id"] == item_id
    # 타 셀러 식별자로는 안 보임(누출 방지)
    assert store.list_items(days=30, seller_ids={"other", "o@x.com"}) == []
