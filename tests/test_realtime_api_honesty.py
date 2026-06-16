"""tests/test_realtime_api_honesty.py — realtime API 정직성 (Phase 204 코드품질).

가짜 'SSE stream mock'/'connected' 제거 + 데모 메트릭 명시(is_demo) 검증.
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


def test_stream_is_honest_not_mock(client):
    """/stream은 가짜 connected/mock 대신 정직한 501을 반환."""
    resp = client.get("/api/v1/realtime/stream")
    assert resp.status_code == 501
    data = resp.get_json()
    assert data["ok"] is False
    assert data["implemented"] is False
    body = resp.get_data(as_text=True)
    assert "mock" not in body.lower()
    assert "connected" not in body.lower()


def test_metrics_flagged_as_demo(client):
    """/metrics는 무작위 데모 데이터임을 is_demo로 명시."""
    resp = client.get("/api/v1/realtime/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_demo"] is True
    assert "metrics" in data
    assert "orders" in data["metrics"]


def test_subscribe_marks_non_persistent(client):
    """/subscribe는 비지속(brokerless) 구독임을 명시."""
    resp = client.post("/api/v1/realtime/subscribe", json={"channel": "orders", "client_id": "c1"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["subscribed"] is True
    assert data["persistent"] is False
