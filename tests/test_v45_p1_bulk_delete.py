"""tests/test_v45_p1_bulk_delete.py — v45 P1: 벌크 삭제 부분 실패 근본 수리.

증상: 20건 전체선택 삭제 → "삭제됨" → 몇 개 잔존 → 반복 삭제 필요 → 페이지 왕복 후 부활.
★근본 원인(오너 지목): 시트에서 **행마다 개별 delete_rows(N회 API 호출)** → 분당 쿼터(429)가
루프 중간에 터지면 일부만 삭제되고 나머지 잔존.
수리: **단일 batchUpdate 1회**(인접 행 구간 묶음 + 내림차순 deleteDimension → 원자성·쿼터 절약).
삭제 API가 **삭제된 id 목록**을 응답 → 프론트는 그 목록만 제거 → 재조회로 검증.

이 가드:
 ①시트 경로가 delete_rows 를 한 번도 안 부르고 batch_update 를 **정확히 1회** 호출.
 ②20건 전체선택 삭제 → 전건 소멸(재읽기 잔존 0) — 판정 재현.
 ③구간 묶음 헬퍼 정확성. ④delete_ids 가 실제 삭제 id 목록 반환·타셀러 차단.
"""
from __future__ import annotations

import importlib


def _fresh_store(monkeypatch, sheet_id="SHEET"):
    """인메모리 리셋 + (옵션) 시트 경로 활성화한 store 모듈 반환."""
    from src.seller_console import collect_history_store as store
    store._in_memory[:] = []
    if sheet_id is not None:
        monkeypatch.setattr(store, "_SHEET_ID", sheet_id)
    else:
        monkeypatch.setattr(store, "_SHEET_ID", None)
    return store


class FakeWorksheet:
    """deleteDimension batchUpdate 를 실제로 적용하는 최소 가짜 워크시트.

    values[0]=헤더. batch_update 가 요청된 행 구간을 제거해 '실제 삭제'를 시뮬레이트한다.
    delete_rows 가 호출되면 즉시 실패로 표시(개별 호출 금지 검증).
    """

    def __init__(self, headers, rows):
        self.values = [list(headers)] + [list(r) for r in rows]
        self.id = 999
        self.spreadsheet = self
        self.delete_rows_calls = 0
        self.batch_update_calls = 0
        self.last_requests = None

    # _ensure_headers 용
    def row_values(self, n):
        return self.values[0] if self.values else []

    def get_all_values(self):
        return [list(r) for r in self.values]

    def get_all_records(self):
        hdr = self.values[0]
        return [{hdr[i]: (row[i] if i < len(row) else "") for i in range(len(hdr))}
                for row in self.values[1:]]

    def delete_rows(self, r, *a, **k):
        # v45 P1: 개별 삭제는 금지 — 호출되면 카운트해서 테스트가 실패하게.
        self.delete_rows_calls += 1

    def batch_update(self, body):
        self.batch_update_calls += 1
        self.last_requests = body.get("requests", [])
        # deleteDimension 적용: 0-based [startIndex, endIndex) 행 제거.
        # 헤더가 values[0] 이므로 시트 1-based 행 r → values 인덱스 r-1.
        drop = set()
        for req in self.last_requests:
            rng = req["deleteDimension"]["range"]
            # deleteDimension 0-based 행 인덱스 = values 인덱스(헤더=행0).
            for zero in range(rng["startIndex"], rng["endIndex"]):
                drop.add(zero)
        self.values = [row for i, row in enumerate(self.values) if i not in drop]


def _make_ws(store, n, seller="u1"):
    hdr = store._HEADERS
    rows = []
    ids = []
    for k in range(n):
        iid = f"id{k:03d}"
        ids.append(iid)
        row = [""] * len(hdr)
        row[hdr.index("id")] = iid
        row[hdr.index("url")] = f"https://x.com/p{k}"
        row[hdr.index("title")] = f"상품{k}"
        row[hdr.index("seller_id")] = seller
        rows.append(row)
    return FakeWorksheet(hdr, rows), ids


def test_contiguous_blocks():
    from src.seller_console import collect_history_store as store
    assert store._contiguous_blocks([2, 3, 4, 7, 8]) == [(2, 4), (7, 8)]
    assert store._contiguous_blocks([5]) == [(5, 5)]
    assert store._contiguous_blocks([9, 2, 3]) == [(2, 3), (9, 9)]


def test_sheet_delete_uses_single_batchupdate_not_per_row(monkeypatch):
    """★핵심: 20건 삭제 = batch_update 1회, delete_rows 0회(부분 실패 원인 제거)."""
    store = _fresh_store(monkeypatch)
    ws, ids = _make_ws(store, 20)
    monkeypatch.setattr(store, "_get_worksheet", lambda: ws)

    removed = store.delete_ids(ids, seller_ids={"u1"})

    assert ws.delete_rows_calls == 0, "행마다 개별 delete_rows 호출은 금지(쿼터 429 부분삭제 원인)"
    assert ws.batch_update_calls == 1, "전건을 단일 batchUpdate 로 원자 삭제해야 함"
    assert set(removed) == set(ids)
    # 재읽기(판정) — 전부 소멸, 잔존 0(부활 없음)
    assert ws.get_all_records() == []
    assert store.existing_ids(ids, seller_ids={"u1"}) == set()


def test_batchupdate_ranges_descending_and_contiguous(monkeypatch):
    """인접 행은 한 구간으로 묶이고, 구간은 내림차순 적용(인덱스 밀림 0)."""
    store = _fresh_store(monkeypatch)
    ws, ids = _make_ws(store, 5)
    monkeypatch.setattr(store, "_get_worksheet", lambda: ws)
    # 데이터 5행(시트 2~6) 전부 삭제 → 인접 → 단일 구간 [1,5) 0-based
    store.delete_ids(ids, seller_ids={"u1"})
    reqs = ws.last_requests
    assert len(reqs) == 1
    rng = reqs[0]["deleteDimension"]["range"]
    assert rng["sheetId"] == 999 and rng["dimension"] == "ROWS"
    assert rng["startIndex"] == 1 and rng["endIndex"] == 6  # 시트행 2..6 → 0-based 1..5 포함


def test_delete_ids_scope_blocks_other_seller(monkeypatch):
    """타 셀러 행은 삭제 안 됨(누출/오삭제 0)."""
    store = _fresh_store(monkeypatch)
    hdr = store._HEADERS
    mine = [""] * len(hdr); mine[hdr.index("id")] = "mine"; mine[hdr.index("seller_id")] = "u1"
    other = [""] * len(hdr); other[hdr.index("id")] = "other"; other[hdr.index("seller_id")] = "u2"
    ws = FakeWorksheet(hdr, [mine, other])
    monkeypatch.setattr(store, "_get_worksheet", lambda: ws)

    removed = store.delete_ids(["mine", "other"], seller_ids={"u1"})
    assert removed == ["mine"]
    remaining = {r["id"] for r in ws.get_all_records()}
    assert remaining == {"other"}


def test_delete_int_wrapper_backcompat(monkeypatch):
    """delete()는 하위호환으로 삭제 건수(int) 반환."""
    store = _fresh_store(monkeypatch, sheet_id=None)  # 인메모리 경로
    iid = store.append(source="extension", url="https://x.com/p", title="t", seller_id="u1")
    assert store.delete([iid], seller_ids={"u1"}) == 1


def test_inmemory_bulk_delete_all_gone(monkeypatch):
    """시트 미설정(인메모리) 경로도 20건 전건 삭제 — 판정 재현."""
    store = _fresh_store(monkeypatch, sheet_id=None)
    ids = [store.append(source="extension", url=f"https://x.com/p{k}", title=f"t{k}", seller_id="u1")
           for k in range(20)]
    removed = store.delete_ids(ids, seller_ids={"u1"})
    assert set(removed) == set(ids)
    assert store.list_items(days=30, seller_ids={"u1"}) == []
    assert store.existing_ids(ids, seller_ids={"u1"}) == set()
