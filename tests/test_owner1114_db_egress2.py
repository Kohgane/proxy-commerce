"""감독 11-14 — #1016 뒤 24h: 남은 무거운 목록(extra_json째) 37회 · 연결 1.3배 → 둘 다 줄인다.

1. `list_items(extra_keys=[…])` — 부른 쪽이 쓰는 extra 칸만(`images_count`는 장수만) · PG·인메모리 같은 모양
2. 매일 쓰는 목록 4곳(용어집 후보 · 재보강 순번 · 보강 현황 · 텔레그램 /verdict)은 그 칸만
3. 연결 재사용 — 백그라운드 풀 1개 상시(1시간 유휴) · 요청 풀 유휴 1800초 · 포크한 워커는 마스터 풀을 버리고 새로
"""
from __future__ import annotations

import json
import os

import pytest


def test_keys_select_sql_and_args():
    from src.db import collect_history_pg as C
    cols, args = C._keys_select(["glossary_candidates", "images_count", "price", "price"])
    assert "jsonb_build_object(" in cols and "AS extra_json" in cols and "extra_json," not in cols.split("jsonb_build_object")[0]
    assert "jsonb_array_length(extra_json->'images')" in cols
    assert args == ["glossary_candidates", "glossary_candidates", "price", "price"]   # 중복 키는 한 번


def test_in_memory_extra_keys_projection(monkeypatch):
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    monkeypatch.setattr(S, "_in_memory", [])
    S.append(source="extension", url="https://x.com/g-77", title="a", seller_id="u1",
             extra={"glossary_candidates": [{"orig": "红", "value": "빨강"}], "images": ["a", "b", "c"],
                    "images_ko": [{"idx": 0, "boxes": ["big"] * 50}], "price": "12"})
    row = S.list_items(seller_ids={"u1"}, extra_keys=["glossary_candidates", "images_count", "price"])[0]
    ex = json.loads(row["extra_json"])
    assert ex == {"glossary_candidates": [{"orig": "红", "value": "빨강"}], "images_count": 3, "price": "12"}
    assert row["url"] == "https://x.com/g-77" and row["title"] == "a"                        # 칸은 그대로


def test_enrich_axes_same_from_projection_as_full():
    from src.collectors.collect_status import enrich_axes
    from src.seller_console import views as V
    full = {"enrich_state": "pending", "mode": "simple", "enriched": False, "price": "9", "images": ["a", "b"],
            "enrich_attempts": 1, "enrich_blocked_reason": "", "images_ko": [{"x": 1}]}
    proj = {k: full.get(k) for k in V._ENRICH_KEYS if k != "images_count"}
    proj["images_count"] = len(full["images"])
    assert enrich_axes(proj) == enrich_axes(full)


@pytest.mark.parametrize("fn_name, must", [
    ("glossary_candidates", "glossary_candidates"),
    ("_enrich_queue_position", "_ENRICH_KEYS"),
    ("sourcing_media_queue", "_ENRICH_KEYS"),
])
def test_daily_list_callers_ask_only_their_keys(fn_name, must):
    import inspect
    from src.seller_console import views as V
    fn = getattr(V, fn_name, None)
    if fn is None:                                                        # 라우트 함수 이름이 다르면 소스에서 찾는다
        fn = next(f for n, f in inspect.getmembers(V, inspect.isfunction) if "보강 현황 조회 실패" in inspect.getsource(f))
    from tests._ast_probe import names_in, string_constants_in
    assert must in (names_in(fn) | string_constants_in(fn))


def test_telegram_verdict_asks_two_keys():
    from src.api import telegram_collect as T
    from tests._ast_probe import string_constants_in
    assert {"item_id_taobao", "site_item_id"} <= string_constants_in(T._handle_verdict)


def test_pool_defaults_keep_connections(monkeypatch):
    from src.db import pg
    seen = {}

    class FakePool:
        def __init__(self, **kw):
            seen.update(kw)

        @staticmethod
        def check_connection(c):
            return None
    import psycopg_pool
    monkeypatch.setattr(psycopg_pool, "ConnectionPool", FakePool)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:1/db")
    for k in ("PG_BG_POOL_MIN", "PG_BG_POOL_IDLE", "PG_POOL_RECYCLE", "PG_BG_POOL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(pg, "_bg_pool", None)
    monkeypatch.setattr(pg, "_bg_pool_checked", False)
    assert pg._background_pool() is not None
    assert seen["min_size"] == 1 and seen["max_idle"] == 3600 and seen["max_size"] == 2


def test_forked_worker_drops_the_masters_pool(monkeypatch):
    from src.db import pg
    made = []

    class FakePool:
        def __init__(self, **kw):
            made.append(os.getpid())

        @staticmethod
        def check_connection(c):
            return None
    import psycopg_pool
    monkeypatch.setattr(psycopg_pool, "ConnectionPool", FakePool)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:1/db")
    monkeypatch.delenv("PG_BG_POOL", raising=False)
    master = object()
    monkeypatch.setattr(pg, "_bg_pool", master)
    monkeypatch.setattr(pg, "_bg_pool_checked", True)
    monkeypatch.setattr(pg, "_bg_pool_pid", os.getpid() + 1)                # 「다른 프로세스(마스터)가 만든 풀」
    p = pg._background_pool()
    assert p is not master and made == [os.getpid()]
    assert pg._background_pool() is p and len(made) == 1                     # 같은 프로세스에선 그대로
