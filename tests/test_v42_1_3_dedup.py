"""tests/test_v42_1_3_dedup.py — v42 1-3: 중복 수집 방지(상품 고유키 정규화).

같은 상품 두 번 수집 → 목록에 1건 + '이미 수집한 상품' 안내. Temu goods-id/아마존 ASIN 키,
쿼리스트링(_oak_mp_inf 등 트래킹) 제거로 같은 상품을 같은 키로 인식.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.product_key import normalize_product_key as K  # noqa: E402


# ── 키 정규화 ──
def test_temu_goods_id_ignores_tracking_query():
    a = K("https://www.temu.com/kr/g-601150655669129.html?_oak_mp_inf=abc&refer=x")
    b = K("https://www.temu.com/kr/g-601150655669129.html")
    c = K("https://www.temu.com/kr/p.html?goods_id=601150655669129&z=1")
    assert a == b == c == "temu:goods:601150655669129"


def test_amazon_asin_marketplace_scoped():
    assert K("https://www.amazon.com/dp/B08N5WRWNW?ref=x") == "amazon.com:asin:B08N5WRWNW"
    assert K("https://www.amazon.com/gp/product/B08N5WRWNW/") == "amazon.com:asin:B08N5WRWNW"
    # 다른 마켓플레이스는 다른 키(마켓별 구분).
    assert K("https://www.amazon.co.jp/dp/B08N5WRWNW") != K("https://www.amazon.com/dp/B08N5WRWNW")


def test_generic_fallback_strips_query_and_trailing_slash():
    assert K("https://shop.ex.com/products/chair?utm=fb") == K("https://shop.ex.com/products/chair/")


# ── 서버 중복 방지 ──
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _clear():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def test_second_collect_is_duplicate_one_row(client):
    _clear()
    body = {"url": "https://www.temu.com/kr/g-601150655669129.html",
            "title": "접이식 차량용 책상", "price": "61144", "currency": "KRW"}
    r1 = client.post("/api/v1/collect/extension", json=body)
    assert r1.status_code == 200 and r1.get_json()["ok"] is True
    assert r1.get_json().get("duplicate") is not True
    # 같은 상품, 다른 트래킹 쿼리로 재수집 → duplicate 안내, 새 행 0.
    body2 = dict(body, url="https://www.temu.com/kr/g-601150655669129.html?_oak_mp_inf=zzz")
    r2 = client.post("/api/v1/collect/extension", json=body2)
    j2 = r2.get_json()
    assert j2["ok"] is True and j2["duplicate"] is True
    assert "이미 수집" in j2["message"]
    assert j2["item_id"] == r1.get_json()["item_id"]     # 기존 항목을 가리킴

    from src.seller_console import collect_history_store as ch
    rows = ch.list_items(seller_ids={"u1"})
    assert len(rows) == 1                                # 목록에 1건만


def test_different_products_not_deduped(client):
    _clear()
    client.post("/api/v1/collect/extension", json={
        "url": "https://www.temu.com/kr/g-111111111111111.html", "title": "A", "price": "1", "currency": "KRW"})
    r = client.post("/api/v1/collect/extension", json={
        "url": "https://www.temu.com/kr/g-222222222222222.html", "title": "B", "price": "2", "currency": "KRW"})
    assert r.get_json().get("duplicate") is not True
    from src.seller_console import collect_history_store as ch
    assert len(ch.list_items(seller_ids={"u1"})) == 2


def test_find_by_product_key_matches_old_rows(client):
    """예전 행(키 미저장)도 url을 그때 정규화해 매칭."""
    _clear()
    from src.seller_console import collect_history_store as ch
    ch.append(source="extension", url="https://www.amazon.com/dp/B08N5WRWNW?ref=old",
              title="구행", seller_id="u1")
    hit = ch.find_by_product_key("https://www.amazon.com/dp/B08N5WRWNW", seller_ids={"u1"})
    assert hit is not None and hit["title"] == "구행"
