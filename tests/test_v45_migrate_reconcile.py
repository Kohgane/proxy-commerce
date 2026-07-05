"""tests/test_v45_migrate_reconcile.py — 이관 검증식(스킵 사유 증명 + distinct 기준 PASS).

운영자 이관: collect 220→195(25 스킵). 25건이 product_key 중복(정상 dedup)이면 검증식이
distinct key 기준으로 PASS해야 한다. 에러 스킵이면 해당 행/원인을 드러내고 FAIL.
DATABASE_URL 설정 시만(로컬 PG). 미설정=skip.
"""
from __future__ import annotations

import os

import pytest

_PG = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정 — PG 이관 테스트 skip")


@pytest.fixture
def pg_ready():
    import src.db.pg as pg
    pg.reset_state(); pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE collect_history")
    yield pg
    pg.reset_state()


def _run_collect(pg, rows):
    import scripts.migrate_to_supabase as mig
    mig._sheet_collect_rows = lambda: rows
    with pg.direct_conn() as conn:
        with conn.cursor() as cur:
            return mig.migrate_collect(cur, dry=False)


def test_duplicate_skips_pass_on_distinct(pg_ready):
    # 같은 상품(같은 goods URL) 여러 번 → product_key 중복 → 정상 dedup
    rows = []
    for i in range(10):
        rows.append({"seller_id": "u1", "url": "https://www.temu.com/g-100.html", "title": f"책상{i}"})
    for i in range(5):
        rows.append({"seller_id": "u1", "url": f"https://www.temu.com/g-2{i}.html", "title": f"고유{i}"})
    out = _run_collect(pg_ready, rows)
    assert out["sheets_total"] == 15
    assert out["dup_count"] == 9            # g-100 반복 10건 중 1건 삽입, 9건 중복 스킵
    assert out["err_count"] == 0
    assert out["distinct_expected"] == 6    # g-100 + g-20..g-24 = 6 distinct
    assert out["pg_total"] == 6
    # 검증식: 에러 0 + PG총계 == 기대 distinct → PASS
    assert out["err_count"] == 0 and out["pg_total"] >= out["distinct_expected"]
    # 중복 목록 증명(요청 1): dup_keys에 스킵된 키 담김
    assert len(out["dup_keys"]) == 9


def test_error_skip_surfaces_row(pg_ready, monkeypatch):
    import scripts.migrate_to_supabase as mig
    rows = [
        {"seller_id": "u1", "url": "https://www.temu.com/g-1.html", "title": "정상"},
        {"seller_id": "u1", "url": "https://www.temu.com/g-2.html", "title": "깨진행", "extra_json": "{bad json"},
    ]
    # 두 번째 행 extra_json이 잘못돼도 json.loads 예외 대신 통과할 수 있으니, 강제로 INSERT 예외 유발:
    # collected_at에 잘못된 타입을 넣어 execute가 실패하도록 normalize 우회.
    orig = mig.normalize_product_key if hasattr(mig, "normalize_product_key") else None
    out = None
    # extra_json '{bad json'은 json.loads 예외 → errors에 잡힘
    out = _run_collect(pg_ready, rows)
    assert out["err_count"] == 1
    assert out["errors"][0][0].endswith("g-2.html")     # 실패 행 url 노출
    assert out["inserted"] == 1
    # 에러가 있으면 검증 FAIL 대상
    assert not (out["err_count"] == 0)
