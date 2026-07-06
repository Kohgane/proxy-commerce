"""tests/test_v45_p1_bulk_delete.py — 벌크 삭제(PG-only 전환 후).

P1(시트 행밀림·부분삭제) 우회코드(batchUpdate·_contiguous_blocks·_sheets_write)는 PG-only
전환으로 제거됐다 — PG는 소프트삭제(단일 UPDATE)라 행밀림 원천 소멸. 인메모리(개발/테스트)
경로의 벌크 삭제 계약만 검증한다: 전건 소멸·셀러 스코프 격리·int 하위호환·재조회 부활 0.
(PG durable 삭제·부활 0은 test_v45_supabase_stage1에서 로컬 PG로 검증.)
"""
from __future__ import annotations

import pytest


@pytest.fixture
def store():
    import src.seller_console.collect_history_store as mod
    mod._in_memory[:] = []
    yield mod
    mod._in_memory[:] = []


def _seed(mod, n, seller="u1"):
    return [mod.append(source="extension", url=f"https://x.com/g-{i}", title=f"상품{i}", seller_id=seller)
            for i in range(n)]


def test_bulk_delete_all_gone(store):
    ids = _seed(store, 20)
    removed = store.delete_ids(ids, seller_ids={"u1"})
    assert sorted(removed) == sorted(ids)                 # 전건 삭제 id 반환
    assert store.list_items(days=30, seller_ids={"u1"}) == []
    assert store.existing_ids(ids, seller_ids={"u1"}) == set()   # 재조회 부활 0


def test_delete_scope_blocks_other_seller(store):
    a = store.append(source="extension", url="https://x.com/a", title="A", seller_id="u1")
    b = store.append(source="extension", url="https://x.com/b", title="B", seller_id="u2")
    removed = store.delete_ids([a, b], seller_ids={"u1"})
    assert removed == [a]                                 # 타 셀러(b) 미삭제
    assert [r["id"] for r in store.list_items(days=30, seller_ids={"u2"})] == [b]


def test_delete_int_wrapper_backcompat(store):
    ids = _seed(store, 3)
    assert store.delete(ids, seller_ids={"u1"}) == 3      # int 반환 하위호환
