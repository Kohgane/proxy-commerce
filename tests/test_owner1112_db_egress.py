"""오너 긴급 2026-11-12 — Supabase 무료 전송량 402(이번 주기 15.9GB/5GB · 94% Shared Pooler).

pg_stat_statements(130일 누적)로 본 상위:
- 수집 목록 폴링(`/collect/history/since`)이 부를 때마다 최신 60행을 extra_json(평균 15KB)째 — 263k행 ≈ 4GB
- 1회용 연결(쿼리마다 TCP+TLS+인증) — 풀러 `get_auth` 537k회
계약:
1. 폴링은 최신 수집 시각 한 칸부터 묻고, 새 것이 있을 때만 그 행을 축약 칸(lean)·커서 뒤만 읽는다
2. 목록 60초 프로세스 캐시 — 같은 조건은 DB를 다시 안 읽고, 이 프로세스의 쓰기는 바로 무효
3. 요청 밖 query()/tx()는 따로 된 작은 풀을 빌린다(요청 풀과 안 섞음) · 못 빌리면 1회용
4. 이미지 복사 크론은 접수된 행만 SQL에서 거른다
5. app_state LIKE·번역 큐 user_id 인덱스
"""
from __future__ import annotations

import contextlib
import json
import os

import pytest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_since_poll_reads_one_cell_when_nothing_new(client, monkeypatch):
    from src.seller_console import collect_history_store as S
    calls = []
    monkeypatch.setattr(S, "latest_created", lambda **kw: "2026-11-12T01:00:00+00:00")
    monkeypatch.setattr(S, "list_items", lambda **kw: calls.append(kw) or [])
    j = client.get("/seller/collect/history/since?after=2026-11-12T01:00:00%2B00:00").get_json()
    assert j["ok"] and j["count"] == 0 and calls == []                 # 새 것 없으면 행을 아예 안 읽는다
    j = client.get("/seller/collect/history/since").get_json()
    assert j["server_max"] == "2026-11-12T01:00:00+00:00" and calls == []   # 첫 호출(기준선)도 한 칸만


def test_since_poll_reads_only_new_rows_lean(client, monkeypatch):
    from src.seller_console import collect_history_store as S
    calls = []
    row = {"id": "n1", "url": "https://x.com/g-n1", "domain": "x.com", "title": "새 상품", "price": "1", "currency": "KRW",
           "source": "extension", "status": "ok", "collected_at": "2026-11-12T02:00:00+00:00", "image_url": "", "extra_json": "{}"}
    monkeypatch.setattr(S, "latest_created", lambda **kw: "2026-11-12T02:00:00+00:00")
    monkeypatch.setattr(S, "list_items", lambda **kw: calls.append(kw) or [dict(row)])
    j = client.get("/seller/collect/history/since?after=2026-11-12T01:00:00%2B00:00").get_json()
    assert j["count"] == 1 and "g-n1" in j["html"]
    assert calls and calls[0]["lean"] is True and calls[0]["created_after"] == "2026-11-12T01:00:00+00:00"
    assert calls[0]["limit"] == 20


def test_in_memory_created_after_and_extra_eq_and_latest(monkeypatch):
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    monkeypatch.setattr(S, "_in_memory", [])
    a = S.append(source="extension", url="https://x.com/g-1", title="a", seller_id="u1", extra={"images_copy_state": "queued"})
    b = S.append(source="extension", url="https://x.com/g-2", title="b", seller_id="u1", extra={"images_copy_state": "done"})
    rows = S.list_items(seller_ids={"u1"}, extra_eq={"images_copy_state": "queued"})
    assert [r["id"] for r in rows] == [a]
    at_a = S.get(a)["collected_at"]
    newer = S.list_items(seller_ids={"u1"}, created_after=at_a)
    assert a not in [r["id"] for r in newer]
    assert S.latest_created(seller_ids={"u1"}) == max(S.get(a)["collected_at"], S.get(b)["collected_at"])
    assert S.latest_created(seller_ids={"nobody"}) == ""


def test_pg_list_cache_hits_and_write_invalidates(monkeypatch):
    from src.db import collect_history_pg as C
    monkeypatch.setenv("CH_LIST_CACHE_SEC", "60")
    C._bump()
    reads = []

    def fake_db(**kw):
        reads.append(kw)
        return [{"id": "r1", "title": "t"}]
    monkeypatch.setattr(C, "_list_items_db", fake_db)
    a = C.list_items(seller_ids={"u1"}, limit=50, lean=True)
    a[0]["title"] = "바꿈"                                          # 돌려준 dict를 고쳐도 캐시는 그대로
    b = C.list_items(seller_ids={"u1"}, limit=50, lean=True)
    assert len(reads) == 1 and b[0]["title"] == "t"
    C.list_items(seller_ids={"u2"}, limit=50, lean=True)
    assert len(reads) == 2                                          # 조건이 다르면 따로

    @contextlib.contextmanager
    def fake_tx():
        yield None
    monkeypatch.setattr(C.pg, "tx", fake_tx)
    with C._wtx():                                                   # 이 프로세스의 쓰기 → 바로 무효
        pass
    C.list_items(seller_ids={"u1"}, limit=50, lean=True)
    assert len(reads) == 3
    monkeypatch.setenv("CH_LIST_CACHE_SEC", "0")                    # 끄면 매번 읽는다
    C.list_items(seller_ids={"u1"}, limit=50, lean=True)
    C.list_items(seller_ids={"u1"}, limit=50, lean=True)
    assert len(reads) == 5


def test_pg_writers_go_through_the_invalidating_wrapper():
    from src.db import collect_history_pg as C
    from tests._ast_probe import calls_in
    for fn in (C.append, C.set_attention, C.delete_ids, C.update, C.compare_swap_extra):
        names = calls_in(fn)
        assert "_wtx" in names and "pg.tx" not in names, fn.__name__


class _FakeCur:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, args=None):
        self.log.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _FakeCur(self.log)

    def transaction(self):
        self.log.append("TX")
        return contextlib.nullcontext()


class _FakePool:
    def __init__(self, give=True):
        self.give, self.got, self.put, self.log = give, 0, 0, []

    def getconn(self, timeout=None):
        if not self.give:
            raise TimeoutError("busy")
        self.got += 1
        return _FakeConn(self.log)

    def putconn(self, c):
        self.put += 1


def test_background_query_and_tx_borrow_from_the_separate_pool(monkeypatch):
    from src.db import pg
    pool = _FakePool()
    monkeypatch.setattr(pg, "_background_pool", lambda: pool)
    monkeypatch.setattr(pg, "_connect", lambda *a, **k: pytest.fail("1회용 연결을 열면 안 된다"))
    with pg.query() as cur:
        cur.execute("SELECT 1")
    with pg.tx() as cur:
        cur.execute("UPDATE x")
    assert pool.got == 2 and pool.put == 2 and pool.log == ["SELECT 1", "TX", "UPDATE x"]


def test_background_pool_busy_falls_back_to_one_off(monkeypatch):
    from src.db import pg
    monkeypatch.setattr(pg, "_background_pool", lambda: _FakePool(give=False))
    opened = []

    class _C(_FakeConn):
        def close(self):
            opened.append("closed")

        def commit(self):
            pass

        def rollback(self):
            pass
    monkeypatch.setattr(pg, "_connect", lambda *a, **k: opened.append("open") or _C([]))
    with pg.query() as cur:
        cur.execute("SELECT 1")
    assert opened == ["open", "closed"]


def test_background_pool_off_without_db_url(monkeypatch):
    from src.db import pg
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    assert pg._background_pool() is None
    monkeypatch.setenv("PG_BG_POOL", "0")
    assert pg._background_pool() is None


def test_media_cron_filters_queued_rows_in_sql(monkeypatch):
    from src.api import media_cron as M
    from src.seller_console import collect_history_store as S
    seen = []
    monkeypatch.setattr(S, "list_items", lambda **kw: seen.append(kw) or [])
    M._drain()
    assert seen and seen[0]["extra_eq"] == {"images_copy_state": "queued"}


def test_schema_stage20_indexes_are_applied():
    from src.db import pg
    assert "schema_stage20.sql" in pg.SCHEMA_FILES
    text = open(os.path.join(os.path.dirname(pg.__file__), "schema_stage20.sql"), encoding="utf-8").read()
    for idx in ("app_state (key text_pattern_ops)", "image_translate_queue (user_id)", "image_translate_usage (user_id)",
                "option_translate_queue (user_id)"):
        assert idx in text
