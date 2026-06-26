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


def test_sheet_write_failure_still_visible_in_history(store, monkeypatch):
    """시트가 설정됐지만 쓰기가 실패(폴백)해도 이력/카운터에 즉시 보여야 한다(가짜 성공 0)."""
    # 시트 설정됨으로 가장
    monkeypatch.setattr(store, "_SHEET_ID", "FAKE_SHEET", raising=False)

    # 시트 쓰기 실패: _get_worksheet().append_row 가 터짐
    class _WS:
        def append_row(self, *a, **k):
            raise RuntimeError("Sheets quota exceeded")

    monkeypatch.setattr(store, "_get_worksheet", lambda: _WS())
    monkeypatch.setattr(store, "_ensure_headers", lambda ws: None)
    # 시트 읽기는 비어 있음(쓰기 실패분이 시트에 없음)
    monkeypatch.setattr(store, "_read_sheet_records", lambda: [])

    item_id = store.append(
        source="extension", url="https://taobao.com/item/123",
        title="테스트 상품", price="100", currency="CNY", seller_id="u1",
    )
    assert item_id  # append는 항상 id 반환

    ids = {"u1", "u1@example.com"}
    # 핵심: 시트에 없어도(쓰기 실패 폴백) 같은 워커 이력 조회에 보여야 한다
    items = store.list_items(days=30, seller_ids=ids)
    assert len(items) == 1, "시트 쓰기 실패 폴백 행이 이력에서 사라짐(=가짜 성공 버그)"
    assert items[0]["id"] == item_id

    # 단건 조회(자기검증 경로)도 같은 결과
    assert store.get(item_id, seller_ids=ids) is not None

    # 카운터(summary)도 반영 — 0이면 '오늘/총수집' 0으로 보이던 증상
    summ = store.summary(days=30, seller_ids=ids)
    assert summ["total"] == 1
    assert summ["by_source"]["extension"] == 1


def test_lenient_seller_id_alias_matching(store, monkeypatch):
    """저장 seller_id(user_id)와 조회 식별자(email 별칭)가 어긋나도 본인 이력은 보인다(v9)."""
    monkeypatch.setattr(store, "_SHEET_ID", None, raising=False)
    item_id = store.append(source="extension", url="https://x.com/p", title="t", seller_id="u1")
    # 조회는 user_id+email 집합으로(별칭 관용)
    items = store.list_items(days=30, seller_ids={"u1", "buyer@x.com"})
    assert len(items) == 1 and items[0]["id"] == item_id
    # 타 셀러 식별자로는 안 보임(누출 방지)
    assert store.list_items(days=30, seller_ids={"other", "o@x.com"}) == []
