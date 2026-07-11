"""tests/test_v54_field_merge.py — v54 STEP3: 필드 병합 우선순위 + 상태 배지 5필드 카운트.

우선순위 명문화: tier1(확장 payload) > ld+json(서버) > tier2 DOM > og. 상태 배지는 드로어 5탭 기준
(가격·갤러리·옵션·상세·리뷰) — 제목 카운트 제외로 '7/7' 표기 오류 정리.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
API = Path("src/api/extension_api.py").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _mem():
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    yield


def test_badge_counts_five_fields_not_seven():
    from src.collectors.collect_status import compute_collect_status, FIELDS, TOTAL
    assert TOTAL == 5 and [k for k, _, _ in FIELDS] == ["price", "images", "options", "detail", "reviews"]
    full = {"title_ko": "상품", "price": "20605", "price_status": "", "images": ["a"],
            "options": [{"name": "색", "values": ["빨"]}], "detail_images": ["d"], "reviews": [{"text": "good"}]}
    st = compute_collect_status(full)
    assert st["filled"] == st["total"] == 5 and st["status"] == "성공"
    # 제목은 fields에 있으나 카운트 제외(count=False)
    title = [f for f in st["fields"] if f["key"] == "title"][0]
    assert title.get("count") is False


def test_detail_present_if_description_or_detail_images():
    from src.collectors.collect_status import compute_collect_status
    # 상세이미지만 있어도 '상세' present(테무 상세 본체).
    st = compute_collect_status({"price": "100", "images": ["a"], "detail_images": ["d1", "d2"]})
    labels = {f["key"]: f["ok"] for f in st["fields"]}
    assert labels["detail"] is True
    # 상세설명(≥20)만 있어도 present.
    st2 = compute_collect_status({"price": "100", "images": ["a"], "description": "x" * 40})
    assert {f["key"]: f["ok"] for f in st2["fields"]}["detail"] is True


def test_precedence_documented():
    assert "tier1 > ld+json > tier2" in API and "빈 필드만" in API


def test_tier1_payload_beats_ldjson():
    # 확장(tier1)이 보낸 price가 서버 ld+json(다른 price)보다 우선 + 라벨 tier1.
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    html = '<script type="application/ld+json">{"@type":"Product","name":"x","offers":{"price":"55000","priceCurrency":"KRW"}}</script>'
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://shop.example.com/p", "title": "책상",
                                        "price": "20605", "currency": "KRW", "images": ["https://s/1.jpg"],
                                        "field_sources": {"price": "tier1", "images": "tier1"}, "html": html}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            it = ch.get(r.get_json()["item_id"], seller_ids={"u1"})
            assert it["price"] == "20605"                 # tier1(payload) 우선 — ld+json 55000 아님
            ex = json.loads(it["extra_json"])
            srcs = {f["key"]: f["source"] for f in ex["collect_status"]["fields"]}
            assert srcs["price"] == "Tier1(API/상태)"     # 라벨도 tier1


def test_ldjson_fills_when_tier1_absent():
    # tier1이 안 보낸 필드는 ld+json이 채운다(우선순위 2).
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    html = '<script type="application/ld+json">{"@type":"Product","name":"x","offers":{"price":"55000","priceCurrency":"KRW"},"image":["https://s/a.jpg"]}</script>'
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://shop.example.com/p2", "title": "", "html": html}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            it = ch.get(r.get_json()["item_id"], seller_ids={"u1"})
            assert it["price"] == "55000"                 # tier1 없음 → ld+json
            ex = json.loads(it["extra_json"])
            srcs = {f["key"]: f["source"] for f in ex["collect_status"]["fields"]}
            assert srcs["price"] == "ld+json"
