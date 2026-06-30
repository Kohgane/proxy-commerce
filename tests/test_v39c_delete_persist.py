"""tests/test_v39c_delete_persist.py — v39 C: 삭제한 토큰/상품 재진입 부활 박멸.

- 토큰: 별칭(user_id↔email)으로 발급돼도 본인 목록에 보이고(표시) 삭제되며(revoke), 시트 revoked=true 영속.
- 수집 상품: bulk-delete가 관용 스코프로 실제 커밋 + 프론트는 서버 재조회(부활 방지).
- 가짜 성공 0: 커밋 실패면 ok=False / deleted=0 정직.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ── 토큰: 관용 식별자 매칭(부활 방지) — 시트 모킹 ──
class _FakeWS:
    def __init__(self, rows):
        self.header = ["token_hash", "user_id", "scopes_json", "created_at",
                       "last_used_at", "expires_at", "revoked"]
        self.rows = rows
        self.updates = []

    def get_all_records(self):
        return [dict(zip(self.header, r)) for r in self.rows]

    def update_cell(self, row_idx, col, val):
        self.updates.append((row_idx, col, val))
        self.rows[row_idx - 2][6] = val  # revoked 컬럼(0-base 6)


@pytest.fixture
def pt_sheet(monkeypatch):
    import src.auth.personal_tokens as pt
    # 토큰은 email로 발급됨(user_id 세션과 별칭)
    ws = _FakeWS([["h1", "demo@goga.kr", "[]", "2026-06-01", "", "2027-06-01", "false"]])
    monkeypatch.setattr(pt, "_SHEET_ID", "sheet-x", raising=False)
    monkeypatch.setattr(pt, "_get_worksheet", lambda: ws)
    return pt, ws


def test_token_listed_and_revoked_via_alias(pt_sheet):
    pt, ws = pt_sheet
    # 세션 식별자 집합엔 user_id(u1)와 email(demo@goga.kr) 둘 다 — 토큰은 email로 발급됨
    ids = {"u1", "demo@goga.kr"}
    # exact user_id(u1)만으론 안 보이지만, 관용 집합으론 보인다(표시 스코프)
    assert pt.list_tokens("u1") == []
    listed = pt.list_tokens("u1", user_ids=ids)
    assert len(listed) == 1 and listed[0]["token_hash"] == "h1"
    # 삭제도 관용 매칭으로 성공 → 시트 revoked=true 영속 커밋(부활 0)
    assert pt.revoke_token("h1", "u1", user_ids=ids) is True
    assert ws.rows[0][6] == "true"
    # 재진입(재조회) 시 활성 아님(이력으로)
    again = pt.list_tokens("u1", user_ids=ids)
    assert again[0]["revoked"] is True


def test_revoke_fake_success_zero_when_no_sheet(monkeypatch):
    import src.auth.personal_tokens as pt
    monkeypatch.setattr(pt, "_SHEET_ID", "", raising=False)
    # 시트 미설정 = 커밋 불가 → 가짜 성공 0(False)
    assert pt.revoke_token("h1", "u1", user_ids={"u1"}) is False


# ── 수집 상품 bulk-delete: 관용 스코프 커밋 + 프론트 서버 재조회 ──
def test_collected_delete_durable_alias_scope():
    import src.seller_console.collect_history_store as ch
    # 인메모리 폴백분: 항목이 email로 저장됨(세션은 user_id)
    ch._in_memory[:] = [
        {"id": "x1", "seller_id": "demo@goga.kr", "title": "A", "url": "u", "status": "ok"},
        {"id": "x2", "seller_id": "other@x.kr", "title": "B", "url": "u", "status": "ok"},
    ]
    # 관용 식별자로 삭제 → 본인 것(x1)만 삭제, 타셀러(x2) 보존
    deleted = ch.delete(["x1", "x2"], seller_ids={"u1", "demo@goga.kr"})
    assert deleted == 1
    ids = [r["id"] for r in ch._in_memory]
    assert "x1" not in ids and "x2" in ids


def test_bulk_delete_route_reloads_and_honest(client_fixture=None):
    # 프론트(JS)는 서버 deleted>0일 때만 location.reload, 0이면 정직 경고(부활 방지) — 템플릿 가드
    hist = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    assert "location.reload()" in hist
    assert "삭제된 항목이 없습니다" in hist          # 0건 정직 안내(가짜 성공 0)
