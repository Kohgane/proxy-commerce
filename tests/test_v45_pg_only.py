"""tests/test_v45_pg_only.py — PG-only 전환: Sheets 폴백·우회코드 제거 + 프로덕션 부팅 가드.

- collect_history_store에서 Sheets 경로/우회코드(P1 batchUpdate·P2 _sheets_write·읽기캐시) 제거.
- 프로덕션(APP_ENV=production)에서 DATABASE_URL 없으면 부팅 실패(조용한 폴백 금지).
- 개발/테스트(APP_ENV 미설정)는 인메모리 허용(무회귀).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

STORE = Path("src/seller_console/collect_history_store.py").read_text(encoding="utf-8")


def test_sheets_workaround_removed_from_store():
    # Sheets 경로/우회코드 심볼이 스토어에서 사라졌다
    for sym in ("_sheets_write", "_contiguous_blocks", "_read_sheet_records",
                "_get_worksheet", "get_quota_stats", "batch_update", "deleteDimension",
                "_ensure_headers", "_SHEET_ID"):
        assert sym not in STORE, f"제거됐어야 할 Sheets 심볼 잔존: {sym}"
    # PG 위임 + 인메모리는 유지
    assert "_pg_backend" in STORE and "_in_memory" in STORE


def test_boot_guard_source():
    ow = Path("src/order_webhook.py").read_text(encoding="utf-8")
    assert 'APP_ENV' in ow and "production" in ow
    assert "부팅 조건" in ow or "부팅 실패" in ow


def test_production_boot_fails_without_db():
    # 별도 프로세스: APP_ENV=production + DATABASE_URL 없음 → import 실패(부팅 가드)
    env = dict(os.environ)
    env["APP_ENV"] = "production"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT", "SUPABASE_DB_URL"):
        env.pop(k, None)
    env["SECRET_KEY"] = "x"  # 세션 경고 회피
    r = subprocess.run(
        [sys.executable, "-c", "import src.order_webhook"],
        capture_output=True, text=True, env=env, cwd=os.getcwd(), timeout=120,
    )
    assert r.returncode != 0, "프로덕션 + DATABASE_URL 없음인데 부팅 성공(조용한 폴백 — 금지)"
    assert "DATABASE_URL" in (r.stderr + r.stdout)


def test_dev_boot_ok_without_db():
    # APP_ENV 미설정(개발/테스트) → DB 없어도 인메모리로 부팅 OK
    env = dict(os.environ)
    for k in ("APP_ENV", "DATABASE_URL", "DATABASE_URL_DIRECT", "SUPABASE_DB_URL"):
        env.pop(k, None)
    env["SECRET_KEY"] = "x"
    r = subprocess.run(
        [sys.executable, "-c", "import src.order_webhook; print('BOOT_OK')"],
        capture_output=True, text=True, env=env, cwd=os.getcwd(), timeout=120,
    )
    assert r.returncode == 0 and "BOOT_OK" in r.stdout, r.stderr[-800:]
