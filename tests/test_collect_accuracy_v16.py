"""tests/test_collect_accuracy_v16.py — v16 P0 수집 정확도: 필러 제거·리뷰·가격0 정직 + FAB 메시징 가드."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- 유닛: 필러 가드 + 리뷰 추출 ----
def test_filler_description_detection():
    from src.collectors.universal_scraper import is_filler_description
    assert is_filler_description("Temu에서 쇼핑하여 절약을 시작하세요")
    assert is_filler_description("Smarter Shopping, Better Living!")
    assert is_filler_description("Start saving today")
    # 실제 상품 설명은 필러 아님(오탐 금지)
    assert not is_filler_description("100% 면 크루넥 티셔츠. 세탁기 사용 가능, 5가지 색상.")
    assert not is_filler_description("")


def test_parse_html_drops_filler_og_description():
    from src.collectors.universal_scraper import UniversalScraper
    html = ('<html><head>'
            '<meta property="og:title" content="Cotton Tee">'
            '<meta property="og:description" content="Temu에서 쇼핑하여 절약을 시작하세요">'
            '</head><body></body></html>')
    s = UniversalScraper().parse_html(html, "https://www.temu.com/p/1")
    assert (s.description or "") == ""        # 필러는 설명으로 저장 안 함


def test_extract_reviews_jsonld_only_real():
    from src.collectors.universal_scraper import extract_reviews
    ld = {"@type": "Product", "review": [
        {"reviewBody": "Great quality", "reviewRating": {"ratingValue": 5}, "author": {"name": "Kim"}}]}
    html = '<html><head><script type="application/ld+json">' + json.dumps(ld) + '</script></head></html>'
    revs = extract_reviews(html)
    assert len(revs) == 1 and revs[0]["rating"] == 5.0 and revs[0]["body"] == "Great quality"
    assert extract_reviews("<html></html>") == []     # 없으면 빈 리스트(가짜 금지)


# ---- 엔드포인트: 필러 제거 + 가격0 정직 ----
@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _post(client, body):
    captured = {}

    def _fake_append(**kwargs):
        captured.update(kwargs)
        return "hist1"

    with patch("src.api.extension_api._require_token") as mock_auth:
        mock_auth.return_value = {"user_id": "u1", "scopes": ["collect.write"]}
        with patch("src.api.extension_api._upsert_catalog", return_value="cat1"), \
             patch("src.api.extension_api._notify_telegram"), \
             patch("src.seller_console.collect_history_store.append", _fake_append), \
             patch("src.seller_console.collect_history_store.get", return_value={"id": "hist1"}):
            resp = client.post("/api/v1/collect/extension", data=json.dumps(body),
                               content_type="application/json",
                               headers={"Authorization": "Bearer tok_test"})
    return resp, captured


def test_endpoint_drops_filler_and_flags_price(client):
    resp, captured = _post(client, {
        "url": "https://www.temu.com/p/1",
        "title": "Cotton Tee",
        "description": "Temu에서 쇼핑하여 절약을 시작하세요",   # 필러
        "price": "0", "currency": "USD", "translate": False,
    })
    assert resp.status_code == 200
    extra = captured.get("extra") or {}
    assert (extra.get("description") or "") == ""              # 필러 저장 안 함
    assert extra.get("price_status") == "needs_check"          # 가격0 → 정직 표기


def test_fab_messaging_guard_present():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "kgpSendMessage" in cs and "kgpExtAlive" in cs       # 컨텍스트 가드
    assert "chrome.runtime.id" in cs
    # 직접 sendMessage 호출은 가드 헬퍼로 일원화(onMessage 리스너 제외)
    assert cs.count("chrome.runtime.sendMessage") == 1          # 헬퍼 내부 1회만


def test_no_percenty_in_extension():
    ext = Path("extensions/chrome-collector")
    for p in list(ext.glob("*.js")) + list(ext.glob("*.html")) + [ext / "README.md", ext / "build.sh"]:
        if p.exists():
            assert "퍼센티" not in p.read_text(encoding="utf-8"), f"{p.name}에 '퍼센티' 잔존"


# ---- P0-3 관리자 패널: 비관리자 숨김 + 403 (회귀 가드) ----
def test_admin_panel_hidden_and_blocked(client):
    # 비관리자 세션은 /admin/* 403, 사이드바에 '관리자 패널' 링크 미노출
    with client.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "u@x.com"; s["user_role"] = "seller"
    assert client.get("/admin/diagnostics").status_code == 403
    assert client.get("/admin/users").status_code == 403
    import os as _os
    _os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "관리자 패널" not in html        # 비관리자에겐 링크 숨김


def test_admin_link_template_gated():
    base = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    # 관리자 패널 링크는 admin 역할 가드 안에 있어야 함
    assert "_user_role == 'admin'" in base
    idx = base.find("관리자 패널")
    assert idx > 0 and "admin" in base[max(0, idx - 200):idx]
