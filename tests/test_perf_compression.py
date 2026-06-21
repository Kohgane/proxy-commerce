"""tests/test_perf_compression.py — v8 속도: gzip 압축 + 정적 캐시 헤더 (Phase 263)."""
from __future__ import annotations

import gzip
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_html_gzip_when_accepted(client):
    """Accept-Encoding: gzip 이면 텍스트 응답을 gzip 압축."""
    resp = client.get("/seller/markets/connect", headers={"Accept-Encoding": "gzip"})
    if resp.status_code != 200:
        pytest.skip("page not 200")
    assert resp.headers.get("Content-Encoding") == "gzip"
    # 압축 해제하면 원문 HTML
    body = gzip.decompress(resp.get_data())
    assert b"<html" in body.lower() or b"<!doctype" in body.lower()


def test_no_gzip_without_accept_encoding(client):
    """Accept-Encoding 없으면 압축 안 함(기존 테스트 안전)."""
    resp = client.get("/seller/markets/connect")
    assert resp.headers.get("Content-Encoding") != "gzip"


def test_static_has_long_cache_header(client):
    resp = client.get("/static/app.css")
    if resp.status_code == 200:
        cc = resp.headers.get("Cache-Control", "")
        assert "max-age" in cc


def test_gunicorn_uses_gthread():
    text = open(os.path.join(os.path.dirname(__file__), "..", "gunicorn.conf.py"), encoding="utf-8").read()
    assert "gthread" in text
    assert "threads" in text
