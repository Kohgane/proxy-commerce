"""src/db/backup.py — PG → Google Sheets 읽기전용 백업(이관 3단계 마무리).

Supabase Postgres가 1차 저장소가 된 뒤(1~3단계), Sheets는 **읽기전용 백업**으로 강등한다.
이 모듈은 PG의 각 이관 테이블(collect_history·user_tokens·market_links·orders) 전체를
`_backup_<table>` 워크시트에 **일 1회 스냅샷 덤프**한다(최신본 덮어쓰기). Render Cron이 호출.

정직 원칙:
- pg_enabled() 아니면 백업 대상 없음 → {"ok": False, "reason": ...} (가짜 성공 0).
- GOOGLE_SHEET_ID 미설정이면 백업 못 함 → 정직 사유.
- 실제 PG에서 읽은 행 수만 보고(집계 날조 0). market_links는 enc_blob(암호문)만 백업(평문 0).
- **읽기 전용**: 이 모듈은 PG에 쓰지 않는다(백업은 Sheets 쪽에만 기록).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from . import pg

logger = logging.getLogger(__name__)

# 백업할 테이블 → 컬럼(전체 행: 소프트삭제 포함, 완전 백업). 값은 Sheets용 text로 캐스팅.
_TABLES = {
    "collect_history": [
        "id", "user_id", "product_key", "source", "domain", "url", "title",
        "image_url", "price", "currency", "status", "preview_url", "extra_json",
        "deleted_at", "created_at", "updated_at",
    ],
    "user_tokens": [
        "id", "user_id", "token_hash", "token_prefix", "scopes", "status",
        "last_used_at", "expires_at", "deleted_at", "created_at", "updated_at",
    ],
    "market_links": [
        "id", "user_id", "market", "enc_blob", "is_encrypted",
        "deleted_at", "created_at", "updated_at",
    ],
    "orders": [
        "id", "order_id", "marketplace", "status", "placed_at", "paid_at",
        "buyer_name_masked", "buyer_phone_masked", "buyer_address_masked",
        "total_krw", "shipping_fee_krw", "items_json", "courier", "tracking_no",
        "shipped_at", "landed_cost_krw", "margin_krw", "margin_pct",
        "last_synced_at", "notes", "deleted_at", "created_at", "updated_at",
    ],
}

# 한 번에 덤프하는 최대 행 수(Sheets 안전 상한 — 초과분은 잘렸음을 정직 보고).
_MAX_ROWS = int(os.getenv("SUPABASE_BACKUP_MAX_ROWS", "50000") or 50000)


def _dump_table(table: str, cols: list) -> tuple:
    """PG에서 table의 전체 행을 읽어 (cols, rows(text 2차원), total, truncated) 반환."""
    with pg.query() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        total = int(cur.fetchone()[0])
        cur.execute(
            f"SELECT {', '.join(cols)} FROM {table} ORDER BY created_at LIMIT %s",
            (_MAX_ROWS,))
        rows = [["" if v is None else str(v) for v in row] for row in cur.fetchall()]
    return cols, rows, total, total > len(rows)


def _get_or_add_ws(sh, name: str, ncols: int):
    """워크시트 반환 — 없으면 생성(백업 전용이라 AUTO_BOOTSTRAP 무관 직접 생성)."""
    try:
        return sh.worksheet(name)
    except Exception:
        return sh.add_worksheet(title=name, rows=1000, cols=max(ncols, 10))


def backup_to_sheets(sheet_id: str = None) -> dict:
    """PG 각 테이블을 `_backup_<table>` 워크시트에 스냅샷 덤프(최신본 덮어쓰기).

    Returns: {"ok": bool, "at": iso, "tables": {name: count}, "truncated": [...], "reason"?}
    """
    if not pg.pg_enabled():
        return {"ok": False, "reason": "PG 미설정 — 백업 대상 없음(Sheets가 아직 1차 저장소)."}
    sid = sheet_id or os.getenv("GOOGLE_SHEET_ID")
    if not sid:
        return {"ok": False, "reason": "GOOGLE_SHEET_ID 미설정 — 백업 저장 위치 없음."}

    try:
        from src.utils.sheets import open_sheet_object
        sh = open_sheet_object(sid)
    except Exception as exc:
        logger.warning("백업 시트 열기 실패: %s", exc)
        return {"ok": False, "reason": "백업 대상 Google Sheets를 열 수 없습니다."}

    at = datetime.now(timezone.utc).isoformat()
    counts: dict = {}
    truncated: list = []
    for table, cols in _TABLES.items():
        try:
            _cols, rows, total, was_trunc = _dump_table(table, cols)
        except Exception as exc:
            logger.warning("백업 읽기 실패 %s: %s", table, exc)
            counts[table] = None   # 정직: 이 테이블은 백업 못 함
            continue
        try:
            ws = _get_or_add_ws(sh, f"_backup_{table}", len(cols))
            ws.clear()
            ws.update("A1", [cols] + rows)
            counts[table] = len(rows)
            if was_trunc:
                truncated.append({"table": table, "total": total, "dumped": len(rows)})
        except Exception as exc:
            logger.warning("백업 쓰기 실패 %s: %s", table, exc)
            counts[table] = None

    # 메타(시각·건수) — 복구/대조용
    try:
        meta = _get_or_add_ws(sh, "_backup_meta", 3)
        meta.clear()
        meta_rows = [["table", "rows", "backed_up_at"]]
        for t, c in counts.items():
            meta_rows.append([t, "실패" if c is None else str(c), at])
        meta.update("A1", meta_rows)
    except Exception as exc:
        logger.debug("백업 메타 기록 실패(무시): %s", exc)

    ok = any(c is not None for c in counts.values())
    return {"ok": ok, "at": at, "tables": counts, "truncated": truncated}
