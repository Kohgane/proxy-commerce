"""tests/test_collect_preview_pipeline_phase200.py — ③ 실 상세 추출 + 번역 (Phase 200).

목업 폴백 제거 검증:
- dispatcher/범용 스크래퍼 실 결과만 사용
- 한국어 번역(ai/translator.py) 연결
- 자동 추출 실패 시 목업 대신 정직한 안내
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _post(client, url, **kw):
    return client.post(
        "/seller/collect/preview",
        data=json.dumps({"url": url, **kw}),
        content_type="application/json",
    )


def test_translation_fills_title_ko_and_copy(client):
    """실 번역기 응답이 title_ko/description_ko 및 마켓 카피로 채워진다."""
    from src.seller_console.collectors.base import CollectorResult

    result = CollectorResult(
        success=True,
        url="https://brand.example.com/p/1",
        source="generic_og",
        title="Premium Running Shoes",
        description="Lightweight breathable mesh.",
        price=Decimal("89.00"),
        currency="USD",
        images=["https://brand.example.com/1.jpg"],
    )
    fake_tr = {
        "title_ko": "프리미엄 러닝화",
        "description_ko": "가볍고 통기성 좋은 메시.",
        "copy_coupang": "쿠팡 카피",
        "copy_smartstore": "스마트스토어 카피",
        "copy_11st": "11번가 카피",
        "provider": "openai",
    }
    with patch("src.seller_console.collectors.dispatcher.collect", return_value=result), \
         patch("src.seller_console.ai.translator.AITranslator.translate_product", return_value=fake_tr):
        resp = _post(client, "https://brand.example.com/p/1")

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    draft = data["draft"]
    assert draft["title_ko"] == "프리미엄 러닝화"
    assert draft["description_ko"] == "가볍고 통기성 좋은 메시."
    assert draft["translation_provider"] == "openai"
    assert draft["marketplace_copy"]["coupang"] == "쿠팡 카피"
    assert draft["is_mock"] is False


def test_stub_translation_keeps_original_and_hides_dummy_copy(client):
    """번역 키 미설정(stub) 시 원문 유지 + 더미 카피 미노출."""
    from src.seller_console.collectors.base import CollectorResult

    result = CollectorResult(
        success=True,
        url="https://brand.example.com/p/2",
        source="generic_og",
        title="Yoga Legging",
        description="High-waist legging.",
        price=Decimal("98.00"),
        currency="USD",
    )
    stub_tr = {
        "title_ko": "Yoga Legging",
        "description_ko": "High-waist legging.",
        "copy_coupang": "[stub] Yoga Legging",
        "copy_smartstore": "[stub] Yoga Legging",
        "copy_11st": "[stub] Yoga Legging",
        "provider": "stub",
    }
    with patch("src.seller_console.collectors.dispatcher.collect", return_value=result), \
         patch("src.seller_console.ai.translator.AITranslator.translate_product", return_value=stub_tr):
        resp = _post(client, "https://brand.example.com/p/2")

    data = json.loads(resp.data)
    draft = data["draft"]
    assert draft["title_ko"] == "Yoga Legging"
    assert draft["translation_provider"] == "stub"
    # stub의 [stub] 더미 카피는 노출하지 않음
    assert "marketplace_copy" not in draft


def test_universal_scraper_options_extracted(client):
    """dispatcher 미탐 시 범용 스크래퍼가 색상/옵션까지 추출."""
    from src.collectors.universal_scraper import ScrapedProduct

    scraped = ScrapedProduct(
        source_url="https://shop.example.com/x",
        domain="shop.example.com",
        title="Hoodie",
        description="Cozy hoodie.",
        images=["https://shop.example.com/h.jpg"],
        price=Decimal("60.00"),
        currency="USD",
        options=[{"name": "Size", "values": ["S", "M", "L"]}],
        extraction_method="json-ld",
        confidence=0.9,
    )
    with patch("src.seller_console.collectors.dispatcher.collect", side_effect=Exception("no dispatcher")), \
         patch("src.collectors.universal_scraper.UniversalScraper.fetch", return_value=scraped), \
         patch("src.seller_console.ai.translator.AITranslator.translate_product",
               return_value={"title_ko": "후드티", "description_ko": "포근한 후드티.", "provider": "stub"}):
        resp = _post(client, "https://shop.example.com/x")

    data = json.loads(resp.data)
    draft = data["draft"]
    assert draft["options"] == [{"name": "Size", "values": ["S", "M", "L"]}]
    assert draft["images"] == ["https://shop.example.com/h.jpg"]
    assert draft["source"].startswith("universal_")


def test_no_mock_on_total_failure(client):
    """dispatcher·범용 스크래퍼 모두 빈 결과면 목업 없이 manual_entry 안내."""
    from src.collectors.universal_scraper import ScrapedProduct

    empty = ScrapedProduct(
        source_url="https://blocked.example.com/y",
        domain="blocked.example.com",
        title="",
        description="",
        confidence=0.0,
    )
    with patch("src.seller_console.collectors.dispatcher.collect", side_effect=Exception("blocked")), \
         patch("src.collectors.universal_scraper.UniversalScraper.fetch", return_value=empty):
        resp = _post(client, "https://blocked.example.com/y")

    data = json.loads(resp.data)
    assert data["ok"] is False
    assert data.get("manual_entry") is True
    assert "$50" not in (data.get("error") or "")
    assert "Mock" not in (data.get("error") or "")
