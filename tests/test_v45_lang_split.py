"""tests/test_v45_lang_split.py — 한/영 분리 저장 + 언어 토글 단일언어 표시 + 원문 뱃지(6).

제목을 title_ko/title_en 분리 저장, UI 언어 토글(kgp_lang)에 맞는 언어만 표시하고,
그 언어 번역이 없으면 원문 폴백 + '원문' 뱃지(섞어 보여주기 금지).
"""
from __future__ import annotations

import os
import json

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    import src.seller_console.collect_history_store as ch
    ch._in_memory[:] = []
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
        yield c, ch
    ch._in_memory[:] = []


def _seed(ch, title, title_ko, title_en):
    ch.append(source="extension", url="https://x.com/g-" + title_en.replace(" ", ""),
              title=title, seller_id="u1",
              extra={"title": title_en, "title_en": title_en, "title_ko": title_ko})


def test_ko_shows_translated_no_badge(client):
    c, ch = client
    _seed(ch, "접이식 책상", "접이식 책상", "Folding Desk")   # 번역됨
    c.set_cookie("kgp_lang", "ko")
    html = c.get("/seller/collect/history").get_data(as_text=True)
    assert "접이식 책상" in html
    assert "Folding Desk" not in html          # 다른 언어 안 섞임
    assert "원문</span>" not in html           # 번역됐으니 원문 뱃지 없음


def test_ko_untranslated_shows_original_with_badge(client):
    c, ch = client
    _seed(ch, "Folding Desk", "Folding Desk", "Folding Desk")   # 미번역(ko==en)
    c.set_cookie("kgp_lang", "ko")
    html = c.get("/seller/collect/history").get_data(as_text=True)
    assert "Folding Desk" in html
    assert "원문" in html                       # 원문 뱃지


def test_en_shows_original_no_mix(client):
    c, ch = client
    _seed(ch, "접이식 책상", "접이식 책상", "Folding Desk")
    c.set_cookie("kgp_lang", "en")
    html = c.get("/seller/collect/history").get_data(as_text=True)
    assert "Folding Desk" in html
    assert "접이식 책상" not in html            # en 토글 → 한국어 안 섞임


def test_storage_separate_fields():
    # 확장 저장이 title_en(원문)/title_ko(번역)/description(원문)/description_ko를 분리 저장
    from pathlib import Path
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert '"title_en": title' in api and '"title_ko": title_ko' in api
    assert '"description_ko"' in api
