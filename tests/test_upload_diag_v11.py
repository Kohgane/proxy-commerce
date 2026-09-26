"""tests/test_upload_diag_v11.py — v11 P0/P1 업로드 정직 진단 + 깔끔 유저 뷰 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_token_missing_message_distinguishes_app_vs_env(monkeypatch):
    """키 미입력 시: 'env 미설정'이 아니라 '마켓 연동에 내 키 입력' 안내 + env 구분."""
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
        monkeypatch.delenv(k, raising=False)
    from src.seller_console.upload_dispatcher import UploadDispatcher
    res = UploadDispatcher().prevalidate(
        {"title": "x", "price": 1000, "images": []}, ["coupang"]
    )
    r = res[0]
    assert r.error_code == "token_missing"
    assert "마켓 연동" in (r.hint or "") or "markets/connect" in (r.hint or "")
    # M1-1(2026-09-26): 예전엔 「서버 환경변수(MARKET_CRED_ENC_KEY …)와 다릅니다」를 붙였다 — 셀러에겐
    #   모르는 이름만 늘었다. 이제 env 이름 0 + 고칠 화면 주소를 따로 준다.
    assert "MARKET_CRED_ENC_KEY" not in (r.hint or "") and "COUPANG_" not in (r.hint or "")
    assert r.action_url == "/seller/markets/connect/coupang"
    assert "환경변수 미설정" not in r.message      # 개발자틱 메시지 폐기


def test_price_zero_blocked_honestly(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP", "x.myshopify.com")
    monkeypatch.setenv("SHOPIFY_AUTO_TOKEN", "tok")
    from src.seller_console.upload_dispatcher import UploadDispatcher
    res = UploadDispatcher().prevalidate(
        {"title": "상품", "price": 0, "images": []}, ["shopify"]
    )
    r = res[0]
    assert r.error_code == "missing_field"
    assert "판매가" in r.message
    assert "원화" in (r.hint or "")


def test_collect_preview_clean_gallery_and_advanced_raw_urls():
    html = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "imageGallery" in html
    assert "function renderGallery" in html
    assert "고급: 이미지 URL" in html          # raw URL 편집은 '고급'으로 숨김
    assert "optionRows" in html                # 옵션 표시 유지


def test_markets_connect_clarifies_app_key_vs_env():
    html = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")
    assert "내 마켓 키" in html
    assert "MARKET_CRED_ENC_KEY" in html       # env 인프라 키와 구분 설명
