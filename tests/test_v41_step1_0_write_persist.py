"""tests/test_v41_step1_0_write_persist.py — v41 STEP 1-0 write/delete 영속성 가드.

- 토큰 발급은 시트 커밋이 확인될 때만 성공.
- billing 저장은 시트 커밋이 확인될 때만 성공.
- collect_history 삭제는 재조회 후에도 부활하지 않는다.
- auth off 회귀는 유지된다.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _FakeTokenWorksheet:
    header = ["token_hash", "user_id", "scopes_json", "created_at", "last_used_at", "expires_at", "revoked"]

    def __init__(self):
        self.rows = []

    def row_values(self, index):
        if index == 1 and self.rows:
            return list(self.header)
        return []

    def insert_row(self, row, index=1):
        if row and row[0] == "token_hash":
            return
        self.rows.insert(max(index - 2, 0), list(row))

    def append_row(self, row):
        self.rows.append(list(row))

    def get_all_records(self):
        return [dict(zip(self.header, row)) for row in self.rows]

    def update_cell(self, row_idx, col, val):
        self.rows[row_idx - 2][col - 1] = val


class _FakeBillingWorksheet:
    header = ["seller_id", "plan", "token_balance"]

    def __init__(self):
        self.rows = []

    def row_values(self, index):
        if index == 1 and self.rows:
            return list(self.header)
        return []

    def insert_row(self, row, index=1):
        if row and row[0] == "seller_id":
            return
        self.rows.insert(max(index - 2, 0), list(row))

    def get_all_records(self):
        return [dict(zip(self.header, row)) for row in self.rows]

    def get_all_values(self):
        return [list(self.header)] + [list(row) for row in self.rows]

    def update_cell(self, row_idx, col, val):
        self.rows[row_idx - 2][col - 1] = val

    def append_row(self, row):
        self.rows.append(list(row))


class _FakeCollectWorksheet:
    header = [
        "id", "collected_at", "source", "domain", "url", "title",
        "image_url", "price", "currency", "status", "preview_url", "extra_json", "seller_id",
    ]

    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.id = 111
        self.spreadsheet = self

    def row_values(self, index):
        if index == 1 and self.rows:
            return list(self.header)
        return []

    def get_all_records(self):
        return [dict(zip(self.header, row)) for row in self.rows]

    def get_all_values(self):
        return [list(self.header)] + [list(row) for row in self.rows]

    def delete_rows(self, row_idx):
        del self.rows[row_idx - 2]

    def batch_update(self, body):
        # v45 P1: 단일 batchUpdate deleteDimension 삭제 시뮬레이트.
        # 0-based 행 인덱스(헤더=행0) → self.rows 인덱스 = zero-1.
        drop = set()
        for req in body.get("requests", []):
            rng = req["deleteDimension"]["range"]
            for zero in range(rng["startIndex"], rng["endIndex"]):
                drop.add(zero - 1)
        self.rows = [row for i, row in enumerate(self.rows) if i not in drop]


@pytest.fixture
def app_client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_token_append_failure_never_returns_raw_token(monkeypatch):
    import src.auth.personal_tokens as pt

    ws = _FakeTokenWorksheet()
    monkeypatch.setattr(pt, "_SHEET_ID", "sheet-test", raising=False)
    monkeypatch.setattr(pt, "_get_worksheet", lambda: ws)

    def _raise_append_error(row):
        raise RuntimeError("boom")

    monkeypatch.setattr(ws, "append_row", _raise_append_error)

    with pytest.raises(pt.TokenStoreCommitError):
        pt.generate_token("user-1")


def test_token_generate_then_validate_round_trip(monkeypatch):
    import src.auth.personal_tokens as pt

    ws = _FakeTokenWorksheet()
    monkeypatch.setattr(pt, "_SHEET_ID", "sheet-test", raising=False)
    monkeypatch.setattr(pt, "_get_worksheet", lambda: ws)
    pt._token_cache.clear()

    result = pt.generate_token("user-1", scopes=["collect.write"])
    validated = pt.validate_token(result["raw_token"], required_scopes=["collect.write"])

    assert validated is not None
    assert validated["user_id"] == "user-1"


def test_collect_history_delete_requery_no_respawn(monkeypatch):
    import src.seller_console.collect_history_store as ch

    ws = _FakeCollectWorksheet([
        ["x1", "2026-07-02T00:00:00+00:00", "extension", "taobao.com", "https://taobao.com/x1", "A", "", "", "", "ok", "", "{}", "u1"],
        ["x2", "2026-07-02T00:00:00+00:00", "extension", "taobao.com", "https://taobao.com/x2", "B", "", "", "", "ok", "", "{}", "u2"],
    ])
    monkeypatch.setattr(ch, "_SHEET_ID", "sheet-test", raising=False)
    monkeypatch.setattr(ch, "_get_worksheet", lambda: ws)
    ch._in_memory[:] = []

    deleted = ch.delete(["x1", "x2"], seller_ids={"u1"})
    assert deleted == 1
    assert [row["id"] for row in ch.list_items(days=30, seller_ids={"u1"})] == []
    assert [row["id"] for row in ch.list_items(days=30, seller_ids={"u2"})] == ["x2"]


def test_billing_commit_failure_is_honest(monkeypatch):
    from src.seller_console import billing_store as bs

    ws = _FakeBillingWorksheet()
    monkeypatch.setattr(bs, "_SHEET_ID", "sheet-test", raising=False)
    monkeypatch.setattr(bs, "_get_worksheet", lambda: ws)

    def _raise_append_error(row):
        raise RuntimeError("boom")

    monkeypatch.setattr(ws, "append_row", _raise_append_error)

    with pytest.raises(bs.BillingCommitError):
        bs.set_plan("seller-1", "plus")


def test_auth_off_regression_keeps_seller_route_open(app_client):
    resp = app_client.get("/seller/me/tokens")
    assert resp.status_code == 200
