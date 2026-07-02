"""tests/test_v42_1_6_filler.py — v42 1-6: 상세설명 가짜 템플릿(필러) 박멸 + AI 초안.

증거: 'Temu에서 이 올인홈 …을 확인하세요. 가구 제품도 좋아할 수 있습니다.' — 자동 필러.
수리: 필러 삭제(실추출 1순위, 없으면 AI 초안 뱃지). 오탐(실제 상세) 0.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.universal_scraper import is_filler_description as F  # noqa: E402


def test_temu_template_is_filler():
    assert F("Temu에서 이 올인홈 접이식 책상을 확인하세요. 가구 제품도 좋아할 수 있습니다.")
    assert F("Temu에서 이 상품을 확인하세요.")
    assert F("가구 제품도 좋아할 수 있습니다.")


def test_real_description_not_filler():
    """실제 상세('확인하세요'·'제품' 포함)는 필러로 오탐하지 않는다."""
    assert not F("이 제품은 원목 소재로 제작된 튼튼한 3단 책상입니다. 조립이 간편합니다.")
    assert not F("조립 방법을 확인하세요. 나사를 시계방향으로 돌리세요.")
    assert not F("사이즈를 확인하세요. 가슴둘레 90cm, 어깨 42cm.")
    assert not F("")


# ── 서버: 확장 수집 시 필러 설명은 저장 안 함(빈값) ──
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_collect_blanks_filler_description(client):
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    r = client.post("/api/v1/collect/extension", json={
        "url": "https://www.temu.com/kr/g-777000111222333.html", "title": "접이식 차량용 책상",
        "description": "Temu에서 이 올인홈 접이식 책상을 확인하세요. 가구 제품도 좋아할 수 있습니다.",
        "price": "61144", "currency": "KRW"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    import json
    row = ch.list_items(seller_ids={"u1"})[0]
    ex = json.loads(row.get("extra_json") or "{}")
    assert (ex.get("description") or "") == ""          # 필러는 저장 0
    assert (ex.get("description_ko") or "") == ""        # 번역본도 필러 아님


def test_edit_page_has_ai_draft_badge_and_button():
    html = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "aiDraftBadge" in html and "AI 초안" in html
    assert "AI 상세 초안 생성" in html
    assert "ai-description" in html
