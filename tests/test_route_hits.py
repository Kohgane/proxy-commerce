"""tests/test_route_hits.py — 화면 방문 카운터(오너 부수 승인 2026-09-03).

계약: **로그 기반 · PII 0 · 별도 저장소 0 · 화면 0.** 계측이 요청을 죽이지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path("src/observability/route_hits.py")


@pytest.fixture(autouse=True)
def _clean():
    from src.observability import route_hits
    route_hits.reset()
    yield
    route_hits.reset()


def test_counts_endpoint_names_not_urls():
    """★ PII 0의 근거 — 세는 단위가 **엔드포인트 이름**이라 상품 id·셀러 id가 들어올 자리가 없다."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.observability import route_hits
    from src.order_webhook import app

    c = app.test_client()
    for _ in range(3):
        c.get("/seller/collect/history?q=비밀검색어&domain=x.com")
    snap = route_hits.snapshot()
    assert snap.get("seller_console.collect_history") == 3
    blob = " ".join(snap)
    assert "비밀검색어" not in blob and "?" not in blob and "/" not in blob


def test_only_html_get_is_counted():
    """API·정적·헬스체크는 '어느 화면을 자주 보나'와 무관하다 — 세지 않는다."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.observability import route_hits
    from src.order_webhook import app

    c = app.test_client()
    c.get("/health")
    c.get("/seller/markets")
    snap = route_hits.snapshot()
    assert any(k.startswith("seller_console.") for k in snap)
    assert not any("health" in k for k in snap)


def test_no_new_store_or_screen():
    """★ 저장소·스키마·화면을 만들지 않는다(오너 계약). 로그 한 줄이 산출물이다."""
    src = SRC.read_text(encoding="utf-8")
    for forbidden in ("import psycopg", "from src.db", "render_template", "CREATE TABLE",
                      "open(", "sqlite", "@bp.", "@app.route"):
        assert forbidden not in src, forbidden
    assert "logger.info" in src


def test_flush_writes_one_line_then_resets(caplog):
    """주기가 되면 1줄 찍고 비운다 — 같은 건수를 두 번 세지 않는다."""
    import logging

    from src.observability import route_hits
    route_hits.record("seller_console.orders")
    route_hits.record("seller_console.orders")
    route_hits.record("seller_console.markets_overview")
    assert route_hits.maybe_flush() == ""                       # 아직 주기 전
    with caplog.at_level(logging.INFO, logger="src.observability.route_hits"):
        line = route_hits.maybe_flush(now=route_hits._since + route_hits.FLUSH_EVERY_SEC + 1)
    assert "seller_console.orders=2" in line and "total=3" in line
    assert route_hits.snapshot() == {}                          # 찍고 비운다
    assert not re.search(r"https?://|/seller/", line)           # 로그에도 URL 0


def test_counter_never_kills_a_request(monkeypatch):
    """계측이 죽어도 화면은 산다."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.observability import route_hits
    from src.order_webhook import app

    monkeypatch.setattr(route_hits, "record",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert app.test_client().get("/seller/markets").status_code == 200


def test_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("ROUTE_HITS", "0")
    from src.observability import route_hits
    assert route_hits.enabled() is False
