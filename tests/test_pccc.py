"""tests/test_pccc.py — 개인통관고유부호(PCCC) 입력·조회 (Phase 250, v3 P1-5)."""
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


@pytest.fixture(autouse=True)
def _clear():
    from src.seller_console import pccc_store as ps
    ps._in_memory.clear()
    yield
    ps._in_memory.clear()


def test_pccc_validation():
    from src.seller_console import pccc_store as ps
    assert ps.is_valid_pccc("P012345678901") is True
    assert ps.is_valid_pccc("p012345678901") is True
    assert ps.is_valid_pccc("P01234-5678 901".replace("-", "").replace(" ", "")) is True
    assert ps.is_valid_pccc("12345") is False
    assert ps.is_valid_pccc("PABCDEFGHIJKL") is False


def test_add_and_list_seller_scoped(client):
    from src.seller_console import pccc_store as ps
    ps.add("s1", name="홍길동", pccc="P012345678901", phone="010")
    ps.add("s2", name="김철수", pccc="P999999999999")
    s1 = ps.list_records("s1")
    assert len(s1) == 1 and s1[0]["name"] == "홍길동"
    assert ps.list_records("s2")[0]["name"] == "김철수"
    # 검색
    assert len(ps.list_records("s1", q="홍길")) == 1
    assert len(ps.list_records("s1", q="없는이름")) == 0


def test_add_route_valid(client):
    r = client.post("/seller/customs/pccc/add", json={"name": "홍길동", "pccc": "P012345678901"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True and data["valid_format"] is True


def test_add_route_bad_format_warns_but_saves(client):
    r = client.post("/seller/customs/pccc/add", json={"name": "홍길동", "pccc": "오타123"})
    data = r.get_json()
    assert data["ok"] is True
    assert data["valid_format"] is False
    assert data["message"]  # 형식 경고


def test_add_route_requires_fields(client):
    assert client.post("/seller/customs/pccc/add", json={"name": "", "pccc": ""}).status_code == 400


def test_delete_route(client):
    from src.seller_console import pccc_store as ps
    rec = ps.add("default", name="홍길동", pccc="P012345678901")
    r = client.post("/seller/customs/pccc/delete", json={"id": rec["id"]})
    assert r.get_json()["ok"] is True
    assert ps.list_records("default") == []


def test_pccc_page_and_nav(client):
    html = client.get("/seller/customs/pccc").get_data(as_text=True)
    assert "통관고유부호" in html
    nav = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/customs/pccc" in nav
