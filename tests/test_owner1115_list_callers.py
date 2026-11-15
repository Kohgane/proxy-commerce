"""감독 11-15 #1018 24h 역행 — extra_json째 목록 236회·12,272행인데 pg_stat은 **누가** 불렀는지 못 가른다.

계약: 목록을 DB에서 읽을 때(캐시 미스)만 호출 함수별 [호출, 행]을 세고, 주기마다 워커당 app_state 한 줄로 낸다.
값은 코드 식별자·숫자뿐 · 기록 실패는 목록을 막지 않는다.
"""
from __future__ import annotations

import contextlib
import json

import pytest


class _Cur:
    def __init__(self, log, rows):
        self.log, self.rows = log, rows

    def execute(self, sql, args=None):
        self.log.append((sql, args))

    def fetchall(self):
        return self.rows


@pytest.fixture
def C(monkeypatch):
    from src.db import collect_history_pg as C
    monkeypatch.setattr(C, "_CALLER_COUNTS", {})
    monkeypatch.setattr(C, "_CALLER_STATE", {"flushed": 10 ** 12, "key": ""})   # 기본: 아직 낼 때 아님
    monkeypatch.setenv("CH_LIST_CACHE_SEC", "0")
    reads, writes = [], []

    @contextlib.contextmanager
    def q():
        yield _Cur(reads, [])

    @contextlib.contextmanager
    def tx():
        yield _Cur(writes, [])
    monkeypatch.setattr(C.pg, "query", q)
    monkeypatch.setattr(C.pg, "tx", tx)
    C._t_reads, C._t_writes = reads, writes
    return C


def a_view_that_lists(C, **kw):
    return C.list_items(seller_ids={"u1"}, **kw)


def test_counts_name_the_real_caller_and_mode(C):
    a_view_that_lists(C, days=90, limit=200)
    a_view_that_lists(C, days=90, limit=200)
    a_view_that_lists(C, lean=True, limit=20)
    a_view_that_lists(C, extra_keys=["price"], limit=5)
    me = f"{__name__.rsplit('.', 1)[-1]}.a_view_that_lists"
    assert C._CALLER_COUNTS == {f"{me}:full": [2, 0], f"{me}:lean": [1, 0], f"{me}:keys": [1, 0]}


def test_flush_upserts_one_row_per_worker(C, monkeypatch):
    monkeypatch.setitem(C._CALLER_STATE, "flushed", C.time.monotonic() - 10 ** 6)   # 주기 지남(부팅 직후 러너도 — monotonic은 0부터가 아니다)
    a_view_that_lists(C, days=90, limit=200)
    assert len(C._t_writes) == 1
    sql, args = C._t_writes[0]
    assert "INSERT INTO app_state" in sql and args[0].startswith("perf:chlist:")
    body = json.loads(args[1])
    assert list(body.values()) == [[1, 0]] and list(body)[0].endswith(".a_view_that_lists:full")
    a_view_that_lists(C, days=90, limit=200)                           # 다음 주기 전엔 안 쓴다
    assert len(C._t_writes) == 1


def test_flush_failure_does_not_break_the_list(C, monkeypatch):
    @contextlib.contextmanager
    def boom():
        raise RuntimeError("db down")
        yield
    monkeypatch.setattr(C.pg, "tx", boom)
    monkeypatch.setitem(C._CALLER_STATE, "flushed", C.time.monotonic() - 10 ** 6)
    assert a_view_that_lists(C, days=90, limit=200) == []


def test_cache_hit_is_not_counted(C, monkeypatch):
    monkeypatch.setenv("CH_LIST_CACHE_SEC", "60")
    C._bump()
    a_view_that_lists(C, days=90, limit=7)
    a_view_that_lists(C, days=90, limit=7)                             # 캐시 — DB를 안 읽었으니 안 센다
    assert sum(v[0] for v in C._CALLER_COUNTS.values()) == 1
