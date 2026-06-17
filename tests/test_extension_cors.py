"""tests/test_extension_cors.py — 북마클릿/확장 크로스오리진 수집 CORS 허용 검증.

CORS가 없으면 브라우저가 preflight를 막아 'Failed to fetch'로 수집이 실패한다.
"""
from __future__ import annotations

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


def test_extension_preflight_allows_cross_origin(client):
    """OPTIONS preflight에 Access-Control-Allow-Origin이 있어야 한다."""
    resp = client.options(
        "/api/v1/collect/extension",
        headers={
            "Origin": "https://www.yoshidakaban.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("Access-Control-Allow-Origin") in ("*", "https://www.yoshidakaban.com")


def test_extension_post_has_cors_header(client):
    """실제 POST 응답에도 CORS 헤더가 붙어야 한다(401이어도 헤더는 존재)."""
    resp = client.post(
        "/api/v1/collect/extension",
        headers={"Origin": "https://shop.example", "Content-Type": "application/json"},
        json={"url": "https://shop.example/p/1"},
    )
    # 토큰 없으면 401이지만 CORS 헤더는 있어야 브라우저가 응답을 읽을 수 있다
    assert resp.headers.get("Access-Control-Allow-Origin") in ("*", "https://shop.example")
