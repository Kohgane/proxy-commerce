"""tests/test_default_markets_v15.py — v15 P1 디폴트 마켓 확장(대형 크로스보더) 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
OPT = Path("extensions/chrome-collector/options.js").read_text(encoding="utf-8")

NEW = ["iherb", "dhgate", "qoo10", "mercari", "rakuten"]


def test_content_script_and_options_sources_in_sync():
    # 새 디폴트 소싱처가 content_script 게이팅과 options 토글 양쪽에 모두 존재
    for sid in NEW:
        assert sid in CS, f"content_script KGP_DEFAULT_SOURCES에 {sid} 없음"
        assert sid in OPT, f"options DEFAULT_SOURCES에 {sid} 없음"


def test_niche_brands_still_user_add_only():
    # 브랜드·니치 도메인은 디폴트 게이팅에 없음(유저 추가 전용) — 도메인 기준으로 정확히 확인
    for niche_dom in ("yoshidakaban.com", "vvic.com", "zozo.jp", "shein.com"):
        assert niche_dom not in CS


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_oneclick_row_has_new_markets_with_icons(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    for dom in ("iherb.com", "dhgate.com", "qoo10.com", "mercari.com", "rakuten.co.jp"):
        assert "domain=" + dom in html, f"원클릭 행에 {dom} 파비콘 없음"
