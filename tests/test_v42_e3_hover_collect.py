"""tests/test_v42_e3_hover_collect.py — v42 E-3: 목록 호버 즉시 수집 버튼.

목록 카드 hover 시 썸네일 중앙 '수집' 버튼 → 클릭 즉시 수집 → '수집됨 ✓'.
이미 수집된 건 처음부터 '수집됨 ✓'(중복 방지 연동, /exists). 터치=우상단 상시.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")


# ── 확장 소스 계약 ──
def test_hover_quick_button_exists():
    assert "kgp-card-quick" in CS
    assert "function kgpQuickCollect" in CS
    assert "수집됨 ✓" in CS
    # 데스크톱 hover 노출 + 터치 상시(우상단)
    assert "mouseenter" in CS and "mouseleave" in CS
    assert "KGP_TOUCH" in CS


def test_quick_collect_marks_collected_on_success_or_duplicate():
    # 성공(success>0) 또는 중복(duplicate>0)이면 '수집됨 ✓'로 마킹.
    i = CS.index("function kgpQuickCollect")
    j = CS.index("\n}\n", i)
    body = CS[i:j]
    assert "resp.success" in body and "resp.duplicate" in body
    assert "kgpMarkQuickCollected" in body


def test_background_has_exists_handler():
    assert 'action: "bulkProgress"' in BG or "collectExists" in BG
    assert "collectExists" in BG and "/api/v1/collect/exists" in BG


# ── 서버: /exists (이미 수집된 URL) ──
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_exists_reports_collected_urls(client):
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    # 하나 수집.
    ch.append(source="extension", url="https://www.temu.com/kr/g-100000000000001.html",
              title="A", seller_id="u1")
    r = client.post("/api/v1/collect/exists", json={"urls": [
        "https://www.temu.com/kr/g-100000000000001.html?_oak=track",   # 같은 상품(트래킹 쿼리)
        "https://www.temu.com/kr/g-999999999999999.html",             # 미수집
    ]})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert d["collected"] == ["https://www.temu.com/kr/g-100000000000001.html?_oak=track"]


def test_exists_requires_auth(client, monkeypatch):
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: None)
    r = client.post("/api/v1/collect/exists", json={"urls": ["https://x/y"]})
    assert r.status_code == 401
