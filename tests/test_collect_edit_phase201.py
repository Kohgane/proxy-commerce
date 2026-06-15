"""tests/test_collect_edit_phase201.py — ④ 수집→확인·수정→업로드 중간 편집 (Phase 201).

- collect_history_store.update: 단건 필드 갱신 + 셀러 격리
- POST /seller/collect/preview/<id>/save: 편집 저장(extra_json 머지) + item 갱신
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_store_update_inmemory_and_seller_isolation():
    from src.seller_console import collect_history_store as store

    item_id = store.append(
        source="manual", url="https://shop.example.com/p",
        title="old", price="10", currency="USD", seller_id="s1",
    )
    assert store.update(item_id, seller_id="s1", title="new", price="20", extra_json='{"a":1}') is True

    got = store.get(item_id, seller_id="s1")
    assert got["title"] == "new"
    assert got["price"] == "20"
    assert got["extra_json"] == '{"a":1}'

    # 타 셀러는 갱신 불가
    assert store.update(item_id, seller_id="other", title="hack") is False
    # 허용되지 않은 필드만 주면 False
    assert store.update(item_id, seller_id="s1", bogus="x") is False


def test_save_merges_extra_and_updates_item(client):
    item = {
        "id": "abc", "url": "https://shop.example.com/p", "source": "manual",
        "title": "old", "price": "10", "currency": "USD",
        "image_url": "https://shop.example.com/old.jpg",
        "extra_json": '{"description":"d","images":["https://shop.example.com/old.jpg"],"brand":"ACME"}',
        "seller_id": "",
    }
    captured = {}

    def fake_update(item_id, *, seller_id=None, **fields):
        captured.update(fields)
        captured["_id"] = item_id
        return True

    with patch("src.seller_console.collect_history_store.get", return_value=item), \
         patch("src.seller_console.collect_history_store.update", side_effect=fake_update):
        resp = client.post(
            "/seller/collect/preview/abc/save",
            data=json.dumps({
                "title": "새 제목", "price": "25", "currency": "USD",
                "description": "새 설명",
                "images": ["https://shop.example.com/1.jpg", "https://shop.example.com/2.jpg", "  "],
                "options": [{"name": "색상", "values": ["블랙", "화이트"]}, {"name": "", "values": ["무시"]}],
            }),
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True

    # extra_json 머지 검증
    extra = json.loads(captured["extra_json"])
    assert extra["title"] == "새 제목"
    assert extra["title_ko"] == "새 제목"
    assert extra["description"] == "새 설명"
    assert extra["description_ko"] == "새 설명"
    assert extra["images"] == ["https://shop.example.com/1.jpg", "https://shop.example.com/2.jpg"]
    assert extra["options"] == [{"name": "색상", "values": ["블랙", "화이트"]}]
    assert extra["brand"] == "ACME"  # 기존 값 보존
    assert extra["edited"] is True

    # item 상위 컬럼 갱신 검증
    assert captured["title"] == "새 제목"
    assert captured["price"] == "25"
    assert captured["image_url"] == "https://shop.example.com/1.jpg"  # 첫 이미지 = 대표


def test_save_options_accepts_comma_string(client):
    item = {"id": "x1", "url": "https://e.com/p", "title": "t", "extra_json": "{}", "seller_id": ""}
    captured = {}
    with patch("src.seller_console.collect_history_store.get", return_value=item), \
         patch("src.seller_console.collect_history_store.update",
               side_effect=lambda i, **k: captured.update(k) or True):
        resp = client.post(
            "/seller/collect/preview/x1/save",
            data=json.dumps({"title": "t", "options": [{"name": "사이즈", "values": "S, M, L"}]}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    extra = json.loads(captured["extra_json"])
    assert extra["options"] == [{"name": "사이즈", "values": ["S", "M", "L"]}]


def test_save_missing_item_404(client):
    with patch("src.seller_console.collect_history_store.get", return_value=None):
        resp = client.post(
            "/seller/collect/preview/none/save",
            data=json.dumps({"title": "x"}),
            content_type="application/json",
        )
    assert resp.status_code == 404


def test_preview_page_has_editable_fields(client):
    item = {
        "id": "abc123", "collected_at": "2026-05-06T10:00:00+00:00", "source": "manual",
        "domain": "shop.example.com", "url": "https://shop.example.com/p",
        "title": "Editable Product", "image_url": "https://shop.example.com/i.jpg",
        "price": "50.00", "currency": "USD", "status": "ok",
        "extra_json": '{"description":"desc","options":[{"name":"색상","values":["블랙"]}]}',
    }
    with patch("src.seller_console.collect_history_store.get", return_value=item):
        resp = client.get("/seller/collect/preview/abc123")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # 편집 입력 필드 존재
    assert 'id="editTitle"' in html
    assert 'id="editPrice"' in html
    assert 'id="editDescription"' in html
    assert 'id="imageRows"' in html
    assert 'id="optionRows"' in html
    assert "변경사항 저장" in html
