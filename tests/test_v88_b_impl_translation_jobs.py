"""tests/test_v88_b_impl_translation_jobs.py — v88-B 구현: translation_jobs 스토어 PG 계약(격리 레인).

DATABASE_URL 설정 시만 실행(pg-suite). 상태전이·idempotency·SKIP LOCKED 우선순위·재시도/터미널 실증.
"""
from __future__ import annotations

import os

import pytest

_PG = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정 — PG 계약 skip")


@pytest.fixture
def jobs():
    from src.db import pg, translation_jobs_pg as J
    pg.reset_state()
    assert pg.pg_enabled(), "PG 연결 실패"
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("DELETE FROM translation_jobs")
    yield J
    pg.reset_state()


def test_enqueue_lease_complete(jobs):
    r = jobs.enqueue("u1", "item-1", priority=5)
    assert r["job_id"] and r["status"] == "pending"
    leased = jobs.lease(10, worker_id="w1")
    assert len(leased) == 1 and leased[0]["item_id"] == "item-1"
    ok = jobs.complete(r["job_id"], provider="papago",
                       result={"title_ko": "쓰무기", "title_ok": True})
    assert ok
    st = jobs.get_by_ids([r["job_id"]], user_id="u1")
    assert st[r["job_id"]]["status"] == "success"
    assert st[r["job_id"]]["provider"] == "papago"
    assert st[r["job_id"]]["result"]["title_ko"] == "쓰무기"


def test_enqueue_idempotent_active(jobs):
    a = jobs.enqueue("u1", "item-dup")
    b = jobs.enqueue("u1", "item-dup")        # 활성 중복 → 같은 작업 재사용(중복 0)
    assert a["job_id"] == b["job_id"]
    # 미완 작업은 1건뿐.
    from src.db import pg
    with pg.query() as cur:
        cur.execute("SELECT count(*) FROM translation_jobs WHERE item_id='item-dup' AND status IN ('pending','running')")
        assert cur.fetchone()[0] == 1


def test_lease_priority_and_skip_locked(jobs):
    jobs.enqueue("u1", "low", priority=0)
    jobs.enqueue("u1", "high", priority=10)
    leased = jobs.lease(1, worker_id="w1")     # 우선순위 높은 것 먼저
    assert len(leased) == 1 and leased[0]["item_id"] == "high"
    # 두 번째 워커는 남은 low만(이미 리스된 high는 running → 안 잡힘).
    leased2 = jobs.lease(5, worker_id="w2")
    assert [x["item_id"] for x in leased2] == ["low"]


def test_fail_retry_then_terminal(jobs):
    r = jobs.enqueue("u1", "item-retry", max_attempts=2)
    jobs.lease(10, worker_id="w1")
    # rate_limit 재시도 → pending 복귀(attempts=1<2).
    assert jobs.fail(r["job_id"], cause="rate_limit", error="429", retryable=True) == "pending"
    st = jobs.get_by_ids([r["job_id"]])[r["job_id"]]
    assert st["status"] == "pending"
    # 다시 리스 → 재실패(attempts=2>=max) → 터미널 failed.
    jobs.lease(10, worker_id="w1")
    assert jobs.fail(r["job_id"], cause="rate_limit", error="429", retryable=True) == "failed"
    assert jobs.get_by_ids([r["job_id"]])[r["job_id"]]["status"] == "failed"


def test_fail_auth_is_terminal_no_retry(jobs):
    r = jobs.enqueue("u1", "item-auth", max_attempts=3)
    jobs.lease(10, worker_id="w1")
    assert jobs.fail(r["job_id"], cause="auth", error="키 무효", retryable=False) == "failed"
    st = jobs.get_by_ids([r["job_id"]])[r["job_id"]]
    assert st["status"] == "failed" and st["cause"] == "auth"


def test_get_by_ids_seller_isolation(jobs):
    r = jobs.enqueue("u1", "item-iso")
    # 다른 셀러로 조회 시 안 보임(격리).
    assert jobs.get_by_ids([r["job_id"]], user_id="u2") == {}
    assert r["job_id"] in jobs.get_by_ids([r["job_id"]], user_id="u1")


def test_drain_once_end_to_end(jobs, monkeypatch):
    """워커 드레인 실경로: 수집 항목 → 작업 등록 → drain → success + collect_history 번역 반영."""
    from src.seller_console import collect_history_store as ch
    # 원문(일본어) 수집 항목 저장(PG 모드).
    iid = ch.append(source="extension", url="https://item.rakuten.co.jp/x/9/",
                    title="표시본", price="1706", currency="JPY", seller_id="u1",
                    extra={"title": "元タイトル", "title_en": "元タイトル", "description": "元の説明"})
    jobs.enqueue("u1", str(iid))

    class _T:
        def translate_product(self, s):
            assert s["title"] == "元タイトル"       # #617 원문 소스
            return {"title_ko": "번역제목", "description_ko": "번역상세", "provider": "papago",
                    "attempts": [], "detected_lang": "ja"}
        def translate_options(self, o): return {"options": o, "provider": "none", "translated": False}
    import src.seller_console.ai.translator as _tr
    monkeypatch.setattr(_tr, "AITranslator", lambda: _T())
    monkeypatch.setenv("TRANSLATION_UNLIMITED", "1")     # 쿼터 우회(회계는 별 테스트)

    from src.seller_console.translate_worker import drain_once
    out = drain_once(limit=10)
    assert out["ok"] and out["success"] == 1, out
    # collect_history에 번역 반영 + 작업 success.
    import json as _j
    row = ch.get(str(iid), seller_ids={"u1"})
    ex = _j.loads(row.get("extra_json") or "{}")
    assert ex["title_ko"] == "번역제목" and ex["description_ko"] == "번역상세"
    assert ex["translated"] is True and ex["translation_provider"] == "papago"
