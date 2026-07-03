"""tests/test_v44_1_upload_status.py — v44-1: 업로드 성공 표식(마켓별 뱃지·목록 등록됨).

서버가 확인한 성공 마켓만 항목에 영속 저장 → 목록 '등록됨' 뱃지. 실패는 저장 안 함(가짜 성공 0).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
HISTORY = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(views, "_seller_id", lambda: "u1")
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


class _FakeResult:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


def test_upload_persists_only_success_markets(client, monkeypatch):
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    iid = ch.append(source="extension", url="https://temu.com/g-1.html", title="소파", seller_id="u1")

    import src.seller_console.views as views
    result = {
        "product_url": "", "total": 3, "succeeded": 2, "queued": 0, "failed": 1,
        "results": [
            {"market": "coupang", "market_label": "쿠팡", "success": True, "external_url": "https://coupang/p/1", "message": "ok"},
            {"market": "smartstore", "market_label": "스마트스토어", "success": True, "external_url": "https://ss/p/2", "message": "ok"},
            {"market": "elevenst", "market_label": "11번가", "success": False, "message": "키 없음", "error_code": "token_missing"},
        ],
    }

    class _Disp:
        def dispatch(self, product, markets):
            return _FakeResult(result)
    monkeypatch.setattr(views, "_get_upload_dispatcher", lambda: _Disp())
    import src.seller_console.market_credentials as mc
    monkeypatch.setattr(mc, "seller_market_env", lambda *a, **k: __import__("contextlib").nullcontext())

    r = client.post("/seller/collect/upload", json={
        "product": {"title": "소파"}, "markets": ["coupang", "smartstore", "elevenst"], "item_id": iid})
    assert r.status_code == 200 and r.get_json()["ok"] is True

    row = ch.get(iid, seller_ids={"u1"})
    up = json.loads(row.get("extra_json") or "{}").get("uploaded")
    got = sorted(u["market"] for u in up)
    assert got == ["coupang", "smartstore"]        # 성공 2개만
    assert "elevenst" not in got                   # 실패는 저장 0(가짜 성공 금지)
    assert any(u.get("external_url") for u in up)   # 상품 바로가기 URL 보관


def test_history_view_exposes_uploaded_markets(client, monkeypatch):
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    ch.append(source="extension", url="https://temu.com/g-2.html", title="책상", seller_id="u1",
              extra={"uploaded": [{"market": "coupang", "market_label": "쿠팡", "external_url": "https://c/1"}]})
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "등록됨" in html and "쿠팡" in html


def test_templates_have_badges_retry_and_item_id():
    # 결과 모달: 마켓별 뱃지 + 실패 재시도 + item_id 전송.
    assert "등록됨" in PREVIEW and "retryFailedUpload" in PREVIEW
    assert "item_id: _ITEM_ID" in PREVIEW
    # 목록: 등록됨 뱃지.
    assert "uploaded_markets" in HISTORY and "등록됨" in HISTORY
