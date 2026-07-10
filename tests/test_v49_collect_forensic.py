"""tests/test_v49_collect_forensic.py — v49 STEP4: 필드 수집 포렌식 + 서버 초기상태 JSON 파서.

분기 확정: 서버가 수신 html의 초기 상태 JSON(window.rawData 등)을 파싱 안 하던 것(유력)을 수리.
서버 파서(state_json)가 sku 가격·갤러리·옵션·상세·평점·리뷰 매핑. 확장·북마클릿 공통 경유(통일).
수신/전송 요약 로그. 가격 sanity(KRW<100 거부). 추가 API 호출 없음.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
SJ = Path("src/collectors/state_json.py").read_text(encoding="utf-8")

_TEMU_HTML = (
    '<html><body><script>window.rawData={"g":{"goodsName":"접이식 책상",'
    '"skuList":[{"salePrice":20605,"currency":"KRW","specValue":["블랙"]},'
    '{"salePrice":22000,"currency":"KRW","specValue":["화이트"]}],'
    '"galleryImages":["https://t.com/1.jpg","https://t.com/2.jpg","https://t.com/3.jpg"],'
    '"detailImages":["https://t.com/d1.jpg"],'
    '"avgRating":4.7,"reviewCount":328,'
    '"reviews":[{"reviewId":1,"rating":5,"comment":"튼튼합니다"},{"reviewId":2,"rating":4,"content":"배송 빠름"}]}};</script></body></html>'
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


# ── 서버 파서 ─────────────────────────────────────────────────
def test_state_json_parses_temu_fields():
    from src.collectors.state_json import parse_state_from_html
    r = parse_state_from_html(_TEMU_HTML)
    assert r["price"] == "20605" and r["currency"] == "KRW"    # 첫 유효 sku 가격
    assert len(r["images"]) == 3                                # 갤러리 전체
    assert r["detail_images"] == ["https://t.com/d1.jpg"]
    assert r["options"] and set(r["options"][0]["values"]) >= {"블랙", "화이트"}
    assert r["rating"] == "4.7" and r["review_count"] == "328"
    assert len(r["reviews"]) == 2
    _texts = " ".join(rv["text"] for rv in r["reviews"])
    assert "튼튼" in _texts and "배송" in _texts               # 순서 무관, 둘 다 수집
    assert r["title"] == "접이식 책상"


def test_state_json_cents_conversion_usd():
    # 소단위 통화(USD)에서 정수 큰 값은 ÷100(센트) — KRW는 그대로.
    from src.collectors.state_json import parse_state_from_html
    r = parse_state_from_html('<script>window.rawData={"skuList":[{"price":1299,"currency":"USD","spec":["A"]},{"price":1499,"currency":"USD","spec":["B"]}]}</script>')
    assert r["price"] == "12.99" and r["currency"] == "USD"


def test_state_json_empty_when_no_state():
    from src.collectors.state_json import parse_state_from_html
    assert parse_state_from_html("<html><body>no state here</body></html>") == {}
    assert parse_state_from_html("") == {}


# ── 서버 E2E: html → 초기상태 파싱 → DB ───────────────────────
def test_html_payload_server_parses_to_db():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            # v51: 서버 초기상태 파서는 **비-테무** 사이트용(테무는 rawData 없음 → 확장 Tier1 전용).
            #   이 케이스는 rawData를 인라인 임베드하는 일반 사이트 검증(비-temu URL).
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://shop.example.com/g-1", "title": "x", "html": _TEMU_HTML}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            d = r.get_json()
            assert d["ok"] is True
            it = ch.get(d["item_id"], seller_ids={"u1"})
            ex = json.loads(it["extra_json"])
            assert it["price"] == "20605" and it["currency"] == "KRW"   # 오너 기대 20,605
            assert len(ex["images"]) == 3 and ex["options"]
            assert ex["rating"] == "4.7" and ex["review_count"] == "328"


def test_price_sanity_krw_reject():
    # KRW<100(재고·리뷰 숫자 오인)은 확정 가격으로 저장 거부 → needs_check.
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://temu.com/g-9", "title": "x", "price": "9", "currency": "KRW"}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            d = r.get_json()
            it = ch.get(d["item_id"], seller_ids={"u1"})
            ex = json.loads(it["extra_json"])
            assert ex.get("price_status") == "needs_check"


# ── 소스 계약 ─────────────────────────────────────────────────
def test_source_contract_forensic_and_unified():
    assert "수신요약" in API and "초기상태 JSON 파싱" in API        # 서버 수신 요약 + 파싱 로그
    assert "parse_state_from_html" in API                          # 서버 파서 경유(확장·북마클릿 공통)
    assert "_merge_state_into_payload" in API
    assert "전송요약" in CS                                         # 확장 클라 콘솔 요약
    assert "전송요약" in VIEWS                                      # 북마클릿 클라 콘솔 요약
    # 추가 네트워크(API) 호출 없음 — 파서는 텍스트 파싱만
    assert "requests" not in SJ and "urlopen" not in SJ and "fetch" not in SJ
