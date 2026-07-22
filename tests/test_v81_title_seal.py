"""tests/test_v81_title_seal.py — v81 STEP5: 제목 새니타이저 서버 봉인.

증상: 'PORTER STROLL 2WAY BAG | YOSHIDA & Co.' 접미가 저장됨. 코어 폴백(북마클릿 og-meta)은 클라이언트
_sanitizeTitle을 안 타고, 클라 새니타이저도 법인 접미('& Co.')는 $ 앵커를 막혀 못 지웠다. 수리: 서버
단일 지점(collect_sanitize.sanitize_payload)이 sanitize_title로 브랜드+법인 접미까지 제거 → 전 경로 봉인.

판정: | YOSHIDA & Co. 접미 재발 0.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch
from pathlib import Path

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── 단위: sanitize_title(브랜드+법인 접미) ──
def test_sanitize_title_strips_brand_and_corp_suffix():
    from src.collectors.collect_sanitize import sanitize_title
    cases = [
        ("PORTER STROLL 2WAY BAG | YOSHIDA & Co.", "https://www.yoshidakaban.com/x", "PORTER STROLL 2WAY BAG"),
        ("PORTER TANKER | YOSHIDA & Co., LTD.", "https://www.yoshidakaban.com/p", "PORTER TANKER"),
        ("ある製品 ｜ 楽天市場", "https://item.rakuten.co.jp/s/1", "ある製品"),
        ("Amazon.com: Cool Gadget", "https://www.amazon.com/dp/x", "Cool Gadget"),
        ("【楽天市場】名品バッグ", "https://item.rakuten.co.jp/s/1", "名品バッグ"),
    ]
    for raw, url, want in cases:
        assert sanitize_title(raw, url) == want, (raw, sanitize_title(raw, url))
    # 재발 0: 접미가 남지 않는다.
    assert "YOSHIDA & Co." not in sanitize_title("X | YOSHIDA & Co.", "https://www.yoshidakaban.com/x")


def test_sanitize_title_no_overreach_and_never_empty():
    from src.collectors.collect_sanitize import sanitize_title
    # 브랜드 없는 정상 제목은 불변.
    assert sanitize_title("普通の商品タイトル", "https://example.com/p") == "普通の商品タイトル"
    assert sanitize_title("Blue Cotton Shirt - Size M", "https://shop.io/p") == "Blue Cotton Shirt - Size M"
    # 전부 브랜드/접미라 과도 제거되면 원문 보존(빈값 금지).
    assert sanitize_title("| YOSHIDA & Co.", "https://www.yoshidakaban.com/x").strip() != ""
    # 멱등(두 번 돌려도 동일).
    once = sanitize_title("PORTER | YOSHIDA & Co.", "https://www.yoshidakaban.com/x")
    assert sanitize_title(once, "https://www.yoshidakaban.com/x") == once


def test_sanitize_payload_seals_title():
    from src.collectors.collect_sanitize import sanitize_payload
    p = {"title": "PORTER STROLL 2WAY BAG | YOSHIDA & Co.", "url": "https://www.yoshidakaban.com/x",
         "price": "", "currency": ""}
    sanitize_payload(p)
    assert p["title"] == "PORTER STROLL 2WAY BAG"


def test_source_contract_payload_calls_title():
    src = Path("src/collectors/collect_sanitize.py").read_text(encoding="utf-8")
    assert "def sanitize_title(" in src
    assert 'payload["title"] = sanitize_title(' in src   # 단일 지점 봉인


# ── E2E: 코어 폴백(mode=core) 수집 → 저장 제목 접미 0 ──
@pytest.fixture
def client():
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-v81"
    return flask_app.test_client()


def test_core_fallback_title_sealed_e2e(client):
    captured = {}

    def _cap_upsert(*a, **k):
        # product_data는 위치 인자 — title 필드 확인용으로 캡처.
        try:
            captured["pd"] = a[0] if a else k.get("product_data")
        except Exception:
            pass
        return "hist-xyz"

    with patch("src.api.extension_api._require_token") as mock_auth:
        mock_auth.return_value = {"user_id": "u1", "scopes": ["collect.write"]}
        with patch("src.api.extension_api._upsert_catalog", side_effect=_cap_upsert):
            with patch("src.api.extension_api._notify_telegram"):
                resp = client.post(
                    "/api/v1/collect/extension",
                    data=json.dumps({
                        "url": "https://www.yoshidakaban.com/product/12345.html",
                        "title": "PORTER STROLL 2WAY BAG | YOSHIDA & Co.",
                        "mode": "core",
                        "translate": False,
                    }),
                    content_type="application/json",
                    headers={"Authorization": "Bearer tok_test"},
                )
    assert resp.status_code in (200, 201, 502), resp.get_data(as_text=True)[:200]
    pd = captured.get("pd") or {}
    stored_title = str(pd.get("title") or pd.get("title_ko") or "")
    assert "YOSHIDA & Co." not in stored_title, ("코어 폴백 저장 제목에 브랜드 접미 재발!", stored_title)
    assert "PORTER STROLL 2WAY BAG" in stored_title, stored_title
