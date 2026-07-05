"""tests/test_v45_supabase_backup.py — 이관 3단계 마무리: PG → Sheets 읽기전용 백업.

PG가 1차 저장소가 된 뒤 Sheets는 읽기전용 백업(일 1회 덤프). 정직: PG/시트 미설정이면 가짜 성공 0.
PG 실덤프 검증은 DATABASE_URL 설정 시만(로컬 PG), 나머지 계약/폴백은 상시.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_PG = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")


# ── 가짜 Google Sheets(덤프 캡처) ───────────────────────────────────────────────
class _FakeWS:
    def __init__(self):
        self.rows = None
    def clear(self):
        self.rows = None
    def update(self, _cell, values):
        self.rows = values


class _FakeSheet:
    def __init__(self):
        self.ws = {}
    def worksheet(self, name):
        if name not in self.ws:
            raise KeyError(name)
        return self.ws[name]
    def add_worksheet(self, title, rows, cols):
        self.ws[title] = _FakeWS()
        return self.ws[title]


def test_backup_disabled_when_no_pg(monkeypatch):
    from src.db import backup, pg
    monkeypatch.setattr(pg, "pg_enabled", lambda: False)
    out = backup.backup_to_sheets(sheet_id="x")
    assert out["ok"] is False and "PG" in out["reason"]


def test_backup_no_sheet_id(monkeypatch):
    from src.db import backup, pg
    monkeypatch.setattr(pg, "pg_enabled", lambda: True)
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    out = backup.backup_to_sheets(sheet_id=None)
    assert out["ok"] is False and "GOOGLE_SHEET_ID" in out["reason"]


def test_contract_source():
    src = Path("src/db/backup.py").read_text(encoding="utf-8")
    # 4개 이관 테이블 백업
    for t in ("collect_history", "user_tokens", "market_links", "orders"):
        assert f'"{t}"' in src
    # market_links는 암호문(enc_blob)만 — 평문 컬럼 없음
    assert "enc_blob" in src
    # 읽기 전용: PG UPDATE/INSERT/DELETE 없음
    assert "UPDATE " not in src and "INSERT " not in src and "DELETE " not in src
    cron = Path("src/pricing/cron.py").read_text(encoding="utf-8")
    assert '@cron_bp.post("/supabase-backup")' in cron


@pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정 — PG 덤프 테스트 skip")
def test_backup_dumps_rows(monkeypatch):
    import src.db.pg as pg
    import src.utils.sheets as sheets
    from src.db import backup, collect_history_pg as ch

    pg.reset_state()
    assert pg.pg_enabled()
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE collect_history")
    ch.append(source="ext", url="https://x.com/g-1", title="백업행", price="1000", seller_id="u1")

    fake = _FakeSheet()
    monkeypatch.setattr(sheets, "open_sheet_object", lambda _sid: fake)
    out = backup.backup_to_sheets(sheet_id="sid")

    assert out["ok"] is True
    assert out["tables"]["collect_history"] >= 1
    body = fake.ws["_backup_collect_history"].rows
    assert body[0][:2] == ["id", "user_id"]          # 헤더
    assert any("백업행" in str(v) for r in body[1:] for v in r)   # 실제 행 덤프됨
    assert "_backup_meta" in fake.ws                  # 메타 기록
    pg.reset_state()
