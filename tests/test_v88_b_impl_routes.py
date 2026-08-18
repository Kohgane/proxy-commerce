"""tests/test_v88_b_impl_routes.py — v88-B 구현: 라우트/워커/스키마 배선 (비-PG, CI 실행).

PG 미가동(이 환경)에서도 도는 계약: 백그라운드 비활성 시 동기 폴백(무회귀)·스키마 배선·워커 재시도 판정·드레인 no-op.
불변: 체인·요청예산 캡·쿼터 회계 무손대(이 트랙은 실행 위치 분리만).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_schema_stage5_wired_and_table():
    pg_src = Path("src/db/pg.py").read_text(encoding="utf-8")
    assert "schema_stage5.sql" in pg_src, "init_schema에 stage5 미배선"
    sql = Path("src/db/schema_stage5.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS translation_jobs" in sql
    assert "uq_txjob_active_idem" in sql and "FOR EACH ROW EXECUTE FUNCTION set_updated_at" in sql


def test_worker_retryable_causes():
    from src.seller_console.translate_worker import _retryable
    assert _retryable("rate_limit") and _retryable("transient") and _retryable("budget")
    assert not _retryable("auth") and not _retryable("quota")


def test_drain_noop_without_pg(monkeypatch):
    # DATABASE_URL 없으면(이 환경) 정직 no-op — 작업 처리 0.
    for v in ("DATABASE_URL", "SUPABASE_DB_URL"):
        monkeypatch.delenv(v, raising=False)
    from src.db import pg
    pg.reset_state()
    from src.seller_console.translate_worker import drain_once
    out = drain_once(limit=5)
    assert out["ok"] is False and out["processed"] == 0 and "pg" in out["reason"].lower()


def _client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    monkeypatch.setattr(V, "_seller_identities", lambda: {"u1"})
    from src.order_webhook import app
    return app.test_client()


def test_enqueue_falls_back_to_sync_when_flag_off(monkeypatch):
    monkeypatch.delenv("TRANSLATE_BACKGROUND", raising=False)
    c = _client(monkeypatch)
    r = c.post("/seller/collect/translate/enqueue", json={"item_ids": ["x1"]})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["background"] is False   # 동기 폴백(무회귀)


def test_enqueue_requires_items(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/seller/collect/translate/enqueue", json={"item_ids": []})
    assert r.status_code == 400


def test_status_empty_ids_ok(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/seller/collect/translate/status")
    assert r.status_code == 200 and r.get_json()["jobs"] == {}


def test_background_flag_requires_pg(monkeypatch):
    # flag on이어도 PG 미가동이면 비활성(무회귀).
    monkeypatch.setenv("TRANSLATE_BACKGROUND", "1")
    for v in ("DATABASE_URL", "SUPABASE_DB_URL"):
        monkeypatch.delenv(v, raising=False)
    from src.db import pg
    pg.reset_state()
    import src.seller_console.views as V
    assert V._background_translate_enabled() is False


def test_cron_translate_drain_route(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    for v in ("DATABASE_URL", "SUPABASE_DB_URL"):
        monkeypatch.delenv(v, raising=False)
    from src.db import pg
    pg.reset_state()
    from src.order_webhook import app
    r = app.test_client().post("/cron/translate-drain")
    assert r.status_code == 200
    d = r.get_json()
    assert d.get("ok") is False and "pg" in (d.get("reason", "").lower())   # 정직 no-op
