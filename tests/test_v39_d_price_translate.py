"""tests/test_v39_d_price_translate.py — v39 D: 가격 정직 표기 + 한국어 번역(온디맨드·정직)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_get_owned_item", lambda iid: {
        "id": iid, "title": "ヨシダ PORTER タンカー", "url": "https://yoshidakaban.com/p",
        "domain": "yoshidakaban.com", "price": "", "currency": "JPY", "image_url": "",
        "status": "ok", "source": "extension", "seller_id": "u1",
        "extra_json": json.dumps({"title": "ヨシダ PORTER タンカー", "title_en": "ヨシダ PORTER タンカー",
                                  "description": "", "price_status": "needs_check"}),
    })
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_edit_page_has_translate_button_and_orig_toggle():
    assert "translateToKo()" in PREVIEW
    assert 'id="btnTranslateKo"' in PREVIEW and "한국어로 번역" in PREVIEW
    assert "/seller/collect/bulk-translate" in PREVIEW    # 무료 카운터 연동 엔드포인트 재사용
    assert "restoreOrigTitle" in PREVIEW and "원문" in PREVIEW   # 원문 보존/되돌리기


def test_translate_is_honest_when_no_key():
    # stub/키 미설정이면 가짜 번역 0 → 정직 안내 분기
    assert "translated || 0) > 0" in PREVIEW
    assert "OPENAI_API_KEY" in PREVIEW or "원문을 유지" in PREVIEW


def test_price_needs_check_no_arbitrary_conversion():
    # 가격 빈값/needs_check면 임의 환산 금지 → '가격 확인 필요'
    assert "priceNeedsCheck" in PREVIEW and "가격 확인 필요" in PREVIEW
    assert "price_status === 'needs_check'" in PREVIEW


def test_preview_renders_with_needs_check(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/collect/preview/it9").get_data(as_text=True)
    assert html and "한국어로 번역" in html
