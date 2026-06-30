"""tests/test_v40_c_detail_builder.py — v40-C: 마켓별 상세페이지 편집·꾸미기.

블록 에디터(텍스트/이미지/강조박스/구분선) + 마켓 프리셋(공통+마켓 오버라이드) + 미리보기 + 규칙 경고.
저장: extra.detail_blocks(공통 + 마켓별). 마켓 규칙 위반(과대광고)은 등록 전 경고.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


def test_block_editor_ui_present():
    assert "상세페이지 꾸미기" in TPL
    for token in ("dpAddBlock", "dpBlocks", "dpPreview", "dpSelectMarket", "detailPageBuilder"):
        assert token in TPL, f"블록 에디터 토큰 누락: {token}"
    # 4종 블록
    for t in ("'text'", "'image'", "'highlight'", "'divider'"):
        assert f"dpAddBlock({t})" in TPL


def test_market_presets_and_rule_warning():
    for m in ("coupang", "smartstore", "shopify", "woocommerce", "common"):
        assert f'data-market="{m}"' in TPL
    # 마켓별 안내 + 과대광고 경고 후보
    assert "DP_MARKET_NOTES" in TPL and "DP_BANNED" in TPL
    assert "dpCheckRules" in TPL and "과대광고" in TPL


def test_common_plus_market_override_model():
    # 공통(common) 기본 + 마켓 오버라이드(없으면 공통 사용)
    assert "dpActiveBlocks" in TPL and "_dpEnsureOverride" in TPL
    assert "detail_blocks: dpData" in TPL          # 저장 페이로드에 포함


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_save_persists_detail_blocks(client, monkeypatch):
    import src.seller_console.views as views
    import src.seller_console.collect_history_store as ch
    saved = {}
    monkeypatch.setattr(views, "_get_owned_item", lambda iid: {"id": iid, "title": "T", "extra_json": "{}", "seller_id": "u1"})

    def fake_update(item_id, *args, **kw):
        ej = kw.get("extra_json")
        saved["extra"] = json.loads(ej) if ej else (kw.get("extra") or {})
        return True
    monkeypatch.setattr(ch, "update", fake_update, raising=False)

    with client.session_transaction() as s:
        s["user_id"] = "u1"
    payload = {
        "title": "테스트", "detail_blocks": {
            "common": [{"type": "text", "content": "공통 상세"}, {"type": "divider", "content": ""}],
            "coupang": [{"type": "highlight", "content": "쿠팡 전용 강조"}, {"type": "bad", "content": "무시"}],
        }
    }
    r = client.post("/seller/collect/preview/x1/save", json=payload)
    assert r.status_code == 200
    db = saved.get("extra", {}).get("detail_blocks")
    assert db is not None
    assert db["common"][0] == {"type": "text", "content": "공통 상세"}
    assert db["coupang"][0]["type"] == "highlight"
    # 알 수 없는 블록 타입은 제거(정직 — 임의 저장 0)
    assert all(b["type"] in ("text", "image", "highlight", "divider") for b in db["coupang"])
