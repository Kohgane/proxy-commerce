"""tests/test_category_classifier.py — 카테고리 자동 분류 + 편집 페이지 UI/엔드포인트."""
from __future__ import annotations

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


def test_classify_keyword_rules():
    from src.seller_console.category_classifier import classify
    assert classify("포터 가죽 백팩 데일리")["code"] == "BAG"
    assert classify("녹차 티백 100개입")["code"] == "FOD"
    assert classify("무선 블루투스 이어폰")["code"] == "ELC"
    assert classify("1인용 리클라이너 소파 흔들의자")["code"] == "HOM"


def test_classify_unknown_is_gen_zero_conf():
    from src.seller_console.category_classifier import classify
    r = classify("zzzz qqqq 1234")
    assert r["code"] == "GEN" and r["confidence"] == 0.0


def test_classify_empty():
    from src.seller_console.category_classifier import classify
    assert classify("")["code"] == "GEN"


def test_classify_endpoint(client):
    r = client.post("/seller/collect/classify", json={"title": "녹차 티백"})
    d = r.get_json()
    assert d["ok"] is True and d["code"] == "FOD"
    assert "차" in d["matched"]


def _item(title="포터 백팩"):
    return {"id": "x", "title": title, "url": "https://u", "image_url": "",
            "price": "10", "currency": "USD", "extra_json": "{}"}


def test_edit_page_shows_category_select_and_suggestion(client):
    with patch("src.seller_console.collect_history_store.get", return_value=_item()), \
         patch("src.seller_console.market_credentials.is_connected", return_value=True):
        html = client.get("/seller/collect/preview/x").get_data(as_text=True)
    assert "editCategory" in html
    assert "자동 분류" in html
    assert 'value="BAG" selected' in html  # 가방 자동 추천 선택됨


def test_save_persists_category(client):
    saved = {}
    def _update(item_id, **kw):
        saved.update(kw)
        return True
    with patch("src.seller_console.collect_history_store.get", return_value=_item()), \
         patch("src.seller_console.collect_history_store.update", side_effect=_update):
        r = client.post("/seller/collect/preview/x/save",
                        json={"title": "포터 백팩", "category_code": "BAG"})
    assert r.get_json()["ok"] is True
    import json as _json
    extra = _json.loads(saved["extra_json"])
    assert extra["category_code"] == "BAG"


def test_classify_returns_suggested_keywords(client):
    r = client.post("/seller/collect/classify", json={"title": "포터 가죽 백팩"})
    d = r.get_json()
    assert d["code"] == "BAG"
    assert isinstance(d.get("suggested_keywords"), list) and len(d["suggested_keywords"]) >= 5
    assert "가방" in d["suggested_keywords"]


def test_suggest_keywords_per_category():
    from src.seller_console.category_classifier import suggest_keywords
    assert "선물세트" in suggest_keywords("FOD")
    assert "데일리백" in suggest_keywords("BAG")
    # 미지정/GEN도 일반 키워드 반환
    assert len(suggest_keywords("GEN")) >= 5


def test_edit_page_renders_keyword_chips(client):
    item = {"id": "x", "title": "포터 백팩", "url": "https://u", "image_url": "",
            "price": "10", "currency": "USD", "extra_json": "{}"}
    with patch("src.seller_console.collect_history_store.get", return_value=item), \
         patch("src.seller_console.market_credentials.is_connected", return_value=True):
        html = client.get("/seller/collect/preview/x").get_data(as_text=True)
    assert "keywordChips" in html
    assert "전체 추가" in html
    assert "renderKeywordChips" in html
