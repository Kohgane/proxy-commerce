"""tests/test_collect_groups.py — 수집 상품 그룹 관리 (Phase 247, v3 P1-5)."""
from __future__ import annotations

import json
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
    from src.seller_console import collect_history_store as chs
    from src.seller_console import collect_groups as cg
    chs._in_memory.clear()
    cg._in_memory.clear()
    yield
    chs._in_memory.clear()
    cg._in_memory.clear()


def test_group_crud(client):
    from src.seller_console import collect_groups as cg
    g = cg.create_group("s1", "여름신상")
    assert g and g["name"] == "여름신상"
    # 중복 이름 → 같은 그룹 반환
    g2 = cg.create_group("s1", "여름신상")
    assert g2["id"] == g["id"]
    assert len(cg.list_groups("s1")) == 1
    # 타 셀러 격리
    assert cg.list_groups("s2") == []
    assert cg.delete_group("s1", g["id"]) is True
    assert cg.list_groups("s1") == []


def test_create_group_route(client):
    r = client.post("/seller/collect/groups/create", json={"name": "가방류"})
    assert r.status_code == 200
    assert r.get_json()["group"]["name"] == "가방류"


def test_bulk_group_assign_and_new(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t1", seller_id="default")
    b = chs.append(source="manual", url="https://x/2", title="t2", seller_id="default")
    # 새 그룹 생성하며 배정
    r = client.post("/seller/collect/bulk-group",
                    json={"item_ids": [a, b], "group_name": "신상"})
    data = r.get_json()
    assert data["ok"] is True and data["updated"] == 2
    gid = data["group_id"]
    for it in chs._in_memory:
        assert json.loads(it["extra_json"])["group_id"] == gid


def test_history_filter_by_group(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="가방A", seller_id="default")
    chs.append(source="manual", url="https://x/2", title="기타B", seller_id="default")
    r = client.post("/seller/collect/bulk-group", json={"item_ids": [a], "group_name": "백"})
    gid = r.get_json()["group_id"]
    html = client.get(f"/seller/collect/history?group={gid}").get_data(as_text=True)
    assert "가방A" in html
    assert "기타B" not in html


def test_bulk_group_unassign(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t1", seller_id="default")
    r = client.post("/seller/collect/bulk-group", json={"item_ids": [a], "group_name": "G"})
    gid = r.get_json()["group_id"]
    # 그룹 해제(group_id 빈값, group_name 없음)
    client.post("/seller/collect/bulk-group", json={"item_ids": [a], "group_id": ""})
    assert "group_id" not in json.loads(chs._in_memory[0]["extra_json"])
    assert gid  # (생성됐던 id)


def test_history_page_has_group_ui(client):
    html = client.get("/seller/collect/history").get_data(as_text=True)
    # 빈 상태에서도 그룹 버튼 JS는 로드됨
    assert "bulkGroupBtn" in html
    assert "runBulkGroup" in html
