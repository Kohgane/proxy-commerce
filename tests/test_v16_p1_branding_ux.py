"""tests/test_v16_p1_branding_ux.py — v16 P1: OG 공유 브랜딩·proxy-commerce 제거·FAB on/off·소싱처 메뉴·잔여문구."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_og_share_card_branding(client):
    html = client.get("/").get_data(as_text=True)
    for needle in ('property="og:description"', 'property="og:image"', 'icon-512.png',
                   'name="twitter:card"', 'property="og:site_name"'):
        assert needle in html, f"공유 카드 메타 누락: {needle}"
    assert "수집부터 마켓 등록" in html        # 브랜드+한 줄 소개


def test_brand_default_names_not_proxy_commerce():
    import importlib
    em = importlib.import_module("src.global_commerce.trade.export_manager")
    src = Path("src/orders/international_router.py").read_text(encoding="utf-8")
    assert "'Proxy Commerce'" not in Path("src/notifications/email_sender.py").read_text(encoding="utf-8")
    assert "KOHgogane" in src or "SENDER_NAME" in src
    # 봇 도움말/알림 기본 표기
    assert "코고가네 봇 도움말" in Path("src/bot/commands.py").read_text(encoding="utf-8")


def test_fab_on_off_toggle():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "KGP_FAB_ENABLED" in cs and "kgp_fab_enabled" in cs
    pj = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
    assert "kgp_fab_enabled" in pj and "fabToggle" in pj
    ph = Path("extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
    assert 'id="fabToggle"' in ph


def test_my_sources_in_sidebar(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/sourcing/my-sources" in html
    assert "소싱처 등록(My Sources)" in html
    assert client.get("/seller/sourcing/my-sources").status_code == 200


def test_dev_jargon_removed(client):
    assert "GenericOgCollector" not in client.get("/seller/sourcing").get_data(as_text=True)


def test_bookmarklet_explainer(client):
    html = client.get("/seller/bookmarklet").get_data(as_text=True)
    assert "북마클릿이 뭔가요?" in html and "언제 쓰나요?" in html


def test_token_page_jargon_behind_tooltips():
    tpl = Path("src/seller_console/templates/personal_tokens.html").read_text(encoding="utf-8")
    # 본문은 쉬운 말 + 날것 표기는 '?' 툴팁 뒤로
    assert "‘내 계정 것’임을 자동 확인" in tpl
    assert tpl.count("pc-help") >= 3
    assert "collect.write = 상품 수집 저장" in tpl      # 스코프 뜻은 툴팁 안
    assert "_scope_ko" in tpl                           # 권한 배지 한글화


def test_token_list_is_per_user():
    # 본인 전용 — list_tokens/revoke_token이 user_id로 격리
    import inspect
    from src.auth import personal_tokens as pt
    assert "user_id" in inspect.signature(pt.list_tokens).parameters
    assert "user_id" in inspect.signature(pt.revoke_token).parameters
