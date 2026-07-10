"""tests/test_v52_ldjson_price.py — v52 STEP2: 서버 파서 ld+json 1차(북마클릿 가격 본체 수리).

수신 html의 <script type=application/ld+json> 전수 파싱 → schema.org Product(offers.price/currency·image·
aggregateRating·description·review). 우선순위 ld+json → og/meta → DOM. 가격 sanity 동일. 출처 sources=ldjson.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

API = Path("src/api/extension_api.py").read_text(encoding="utf-8")

_LD_HTML = (
    '<html><head><script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"Product","name":"프리미엄 가방",'
    '"image":["https://shop.com/1.jpg","https://shop.com/2.jpg"],'
    '"description":"이 제품은 고급 가죽으로 제작되었습니다 상세 설명 텍스트입니다",'
    '"offers":{"@type":"Offer","price":"89000","priceCurrency":"KRW"},'
    '"aggregateRating":{"ratingValue":"4.6","reviewCount":"152"},'
    '"review":[{"author":{"name":"김OO"},"reviewRating":{"ratingValue":5},"reviewBody":"만족스러운 구매였습니다"}]}'
    '</script></head><body></body></html>'
)


@pytest.fixture(autouse=True)
def _mem():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    yield


def test_ldjson_parses_product():
    from src.collectors.state_json import parse_ldjson
    r = parse_ldjson(_LD_HTML)
    assert r["price"] == "89000" and r["currency"] == "KRW"
    assert r["title"] == "프리미엄 가방" and len(r["images"]) == 2
    assert r["rating"] == "4.6" and r["review_count"] == "152"
    assert len(r["reviews"]) == 1 and "만족" in r["reviews"][0]["text"]


def test_ldjson_aggregate_offer_and_graph():
    from src.collectors.state_json import parse_ldjson
    r = parse_ldjson('<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"X","offers":{"@type":"AggregateOffer","lowPrice":"12000","priceCurrency":"KRW"}}]}</script>')
    assert r["price"] == "12000" and r["currency"] == "KRW"


def test_ldjson_empty_when_none():
    from src.collectors.state_json import parse_ldjson
    assert parse_ldjson("<html><body>no ldjson</body></html>") == {}


def test_e2e_bookmarklet_html_ldjson_to_db_with_source():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://shop.example.com/p", "title": "", "html": _LD_HTML}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            d = r.get_json()
            it = ch.get(d["item_id"], seller_ids={"u1"})
            ex = json.loads(it["extra_json"])
            assert it["price"] == "89000" and it["currency"] == "KRW"     # 북마클릿 가격 수집됨
            assert len(ex["images"]) == 2 and ex["rating"] == "4.6"
            srcs = {f["key"]: f["source"] for f in ex["collect_status"]["fields"]}
            assert srcs["price"] == "ld+json" and srcs["images"] == "ld+json"   # 출처 기록


def test_price_sanity_applies_to_ldjson():
    # ld+json 가격도 sanity(KRW<100) 거부 → needs_check.
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    html = '<script type="application/ld+json">{"@type":"Product","name":"x","offers":{"price":"9","priceCurrency":"KRW"}}</script>'
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://shop.example.com/g-9", "title": "x", "html": html}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            it = ch.get(r.get_json()["item_id"], seller_ids={"u1"})
            ex = json.loads(it["extra_json"])
            assert ex.get("price_status") == "needs_check"


def test_source_contract():
    assert "parse_ldjson" in API and '"ldjson"' in API      # ld+json 1차 + 출처 기록
    assert "_srv_src" in API                                  # 서버 출처 병합
