"""Z9 후속 PG 실측 — 사전검증 잡 1회 = DB 연결 1회(pg-suite 레인, DATABASE_URL 설정 시만).

13:31 KST 운영: 잡 한 번에 db_conn 19 · db_connect 385ms. 로컬 PG16 같은 입구(네이버 1마켓):
고치기 전 잡 스레드 연결 9 → 고친 뒤 1. 잡 스레드는 요청 풀(`_pool`)을 빌리지 않는다.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import threading

import pytest

from tests._pv_helper import prevalidate as _pvh

_PG_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
_has_pg = bool(_PG_URL and _PG_URL.startswith("postgres"))


@pytest.mark.skipif(not _has_pg, reason="로컬 PostgreSQL(DATABASE_URL) 설정 시만")
def test_prevalidate_job_opens_one_connection(monkeypatch, caplog):
    from src.db import pg
    pg.reset_state()
    assert pg.pg_enabled()
    import src.seller_console.views as V
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    import src.uploaders.naver_categories as NC
    import urllib.request
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setattr(NC, "describe", lambda *a, **k: {})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    main = threading.get_ident()
    job_opens, pool_from_job = [], []
    orig = pg._connect

    def rec(url, **kw):
        if threading.get_ident() != main:
            job_opens.append(threading.current_thread().name)
        return orig(url, **kw)
    monkeypatch.setattr(pg, "_connect", rec)
    pool = pg._persistent_pool()
    if pool is not None:
        orig_get = pool.getconn

        def getconn(*a, **k):
            if threading.get_ident() != main:
                pool_from_job.append(threading.current_thread().name)
            return orig_get(*a, **k)
        monkeypatch.setattr(pool, "getconn", getconn)
    caplog.set_level(logging.INFO, logger=V.logger.name)
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="z9b-pg-seller")
    body = {"product": {"title_ko": "플리츠 미니멀 여성 여름 세트", "naver_category_id": "50000805", "price": 168,
                        "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"], "description": "상세 설명"},
            "markets": ["smartstore"]}
    with app.app_context():
        d = _pvh(c, body)
    assert d.get("state") == "done", d
    assert len(job_opens) == 1, job_opens                       # 잡 전체(마켓 스레드 포함) 연결 1
    assert not pool_from_job                                    # 요청 풀과 분리
    line = next(r.getMessage() for r in caplog.records if "[PV] job=" in r.getMessage() and " done " in r.getMessage())
    perf = json.loads(line.split("perf=", 1)[1])
    assert perf["counts"]["db_conn"] == 1 and perf["counts"]["db_query"] >= 5, perf
    assert perf["segments_ms"].get("db_connect", 0) > 0          # 잡 줄이 그 1회를 잰다
