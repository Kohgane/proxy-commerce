"""tests/test_v45_supabase_stage1.py — 이관 1단계: collect_history + user_tokens → Postgres.

검증: 삭제→재조회→부활 0 / 토큰 저장→재시작→유지 / 같은 상품 재수집→중복 0.
SUPABASE_DB_URL(테스트용 PG) 설정 시에만 실행(미설정이면 skip — CI collect-only·기본 로컬은 Sheets 폴백).
"""
from __future__ import annotations

import os

import pytest

_PG = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="SUPABASE_DB_URL 미설정 — PG 이관 테스트 skip")


@pytest.fixture
def pgclean():
    import src.db.pg as pg
    pg.reset_state()
    assert pg.pg_enabled(), "PG 연결 실패"
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE collect_history")
        cur.execute("TRUNCATE user_tokens")
    yield pg
    pg.reset_state()


# ── collect_history ──────────────────────────────────────────────────────────
def test_append_durable_and_listed(pgclean):
    from src.seller_console import collect_history_store as ch
    iid, durable = ch.append(source="extension", url="https://temu.com/g-1.html",
                             title="소파", price="1000", currency="KRW", seller_id="u1", return_durable=True)
    assert durable is True and iid
    assert len(ch.list_items(days=30, seller_ids={"u1"})) == 1


def test_soft_delete_no_resurrect(pgclean):
    from src.seller_console import collect_history_store as ch
    ids = [ch.append(source="extension", url=f"https://temu.com/g-{i}.html", title=f"t{i}",
                     seller_id="u1") for i in range(5)]
    deleted = ch.delete_ids(ids[:3], seller_ids={"u1"})
    assert set(deleted) == set(ids[:3])
    assert ch.existing_ids(ids[:3], seller_ids={"u1"}) == set()   # 검증: 사라짐
    # 5회 재조회 — 부활 0
    for _ in range(5):
        assert len(ch.list_items(days=30, seller_ids={"u1"})) == 2


def test_dedup_same_product_no_duplicate(pgclean):
    from src.seller_console import collect_history_store as ch
    url = "https://temu.com/g-777.html"
    a = ch.append(source="extension", url=url, title="A", seller_id="u1")
    found = ch.find_by_product_key(url, seller_ids={"u1"})
    assert found and found["id"] == a
    b = ch.append(source="extension", url=url, title="A again", seller_id="u1")
    assert b == a                                        # 같은 id(중복 0)
    assert len(ch.list_items(days=30, seller_ids={"u1"})) == 1


def test_scope_isolation(pgclean):
    from src.seller_console import collect_history_store as ch
    mine = ch.append(source="extension", url="https://x.com/mine.html", title="mine", seller_id="u1")
    ch.append(source="extension", url="https://x.com/other.html", title="other", seller_id="u2")
    assert ch.get(mine, seller_ids={"u1"}) is not None
    assert ch.get(mine, seller_ids={"u2"}) is None       # 타 셀러 접근 차단
    assert ch.delete_ids([mine], seller_ids={"u2"}) == []  # 타 셀러 삭제 0


# ── user_tokens ──────────────────────────────────────────────────────────────
def test_token_persist_across_restart(pgclean):
    from src.auth import personal_tokens as pt
    r = pt.generate_token("u1", scopes=["collect.write"])
    assert r["durable"] is True
    raw = r["raw_token"]
    assert pt.validate_token(raw, ["collect.write"])["user_id"] == "u1"
    # 재시작 시뮬: 캐시·연결 초기화 후에도 유지(영속)
    pt._token_cache.clear()
    pgclean.reset_state()
    assert pt.validate_token(raw, ["collect.write"])["user_id"] == "u1"


def test_token_revoke_history_kept(pgclean):
    from src.auth import personal_tokens as pt
    r = pt.generate_token("u1")
    assert pt.revoke_token(r["token_hash"], "u1") is True
    pt._token_cache.clear()
    assert pt.validate_token(r["raw_token"]) is None      # 회수 후 무효
    lst = pt.list_tokens("u1")
    assert len(lst) == 1 and lst[0]["revoked"] is True    # 이력 보존
