"""tests/test_collect_history_filters.py — 수집 이력 검색/정렬/상태/페이지당 (Phase 242, 브리프 §3)."""
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
def _clear_store():
    from src.seller_console import collect_history_store as chs
    chs._in_memory.clear()
    yield
    chs._in_memory.clear()


def _seed(chs):
    chs.append(source="manual", url="https://shop/bag", title="가죽 가방", price="300", currency="USD", seller_id="default")
    chs.append(source="extension", url="https://shop/shoe", title="운동화", price="100", currency="USD", seller_id="default")
    a = chs.append(source="manual", url="https://shop/old", title="보관 상품", price="50", currency="USD", seller_id="default")
    chs.update(a, seller_id="default", status="archived")


def test_search_filters_by_title(client):
    from src.seller_console import collect_history_store as chs
    _seed(chs)
    html = client.get("/seller/collect/history?q=가방").get_data(as_text=True)
    assert "가죽 가방" in html
    assert "운동화" not in html


def test_status_filter_archived(client):
    from src.seller_console import collect_history_store as chs
    _seed(chs)
    html = client.get("/seller/collect/history?status=archived").get_data(as_text=True)
    assert "보관 상품" in html
    assert "가죽 가방" not in html


def test_sort_price_high_orders_rows(client):
    from src.seller_console import collect_history_store as chs
    _seed(chs)
    html = client.get("/seller/collect/history?sort=price_high").get_data(as_text=True)
    # 가장 비싼 '가죽 가방'(300)이 '운동화'(100)보다 먼저 등장
    assert html.index("가죽 가방") < html.index("운동화")


def test_pagination_limits_rows(client):
    from src.seller_console import collect_history_store as chs
    for i in range(5):
        chs.append(source="manual", url=f"https://shop/{i}", title=f"상품{i}", price=str(i), seller_id="default")
    html = client.get("/seller/collect/history?per_page=20&page=1").get_data(as_text=True)
    # per_page 옵션 + 페이지네이션 컨텍스트 존재
    assert "name=\"per_page\"" in html


def test_no_results_message_when_filtered_empty(client):
    from src.seller_console import collect_history_store as chs
    _seed(chs)
    html = client.get("/seller/collect/history?q=존재하지않는검색어").get_data(as_text=True)
    assert "조건에 맞는 수집 항목이 없습니다" in html
