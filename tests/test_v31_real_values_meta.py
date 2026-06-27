"""tests/test_v31_real_values_meta.py — v31 P0: 상세·가격 실값 + 원본 메타/플레이스홀더 숨김."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clean():
    from src.seller_console import collect_history_store as store
    store._in_memory[:] = []
    yield
    store._in_memory[:] = []


def _collect(seller_id="u1"):
    from src.seller_console import collect_history_store as store
    return store.append(source="extension", url="https://temu.com/p/1", title="t",
                        seller_id=seller_id, extra={"brand": "테스트", "images": []})


def test_raw_meta_panel_hidden_for_non_admin(client):
    item_id = _collect("u1")
    with client.session_transaction() as s:
        s["user_id"] = "u1"   # 일반 유저(관리자 아님)
    html = client.get(f"/seller/collect/preview/{item_id}").get_data(as_text=True)
    assert "수집된 원본 메타" not in html, "일반 유저에게 개발용 원본 메타 JSON 노출"


def test_raw_meta_panel_shown_for_admin(client):
    item_id = _collect("u1")
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_role"] = "admin"
    html = client.get(f"/seller/collect/preview/{item_id}").get_data(as_text=True)
    assert "수집된 원본 메타" in html


def test_price_prefill_does_not_use_derived_price_original():
    # 빈 USD가 KRW로 둔갑하던 원인 = price_original(파생값) 우선 프리필 → 제외
    assert "_firstNonEmpty(_EXTRA.price, _ITEM.price)" in PREVIEW
    assert "price_original은 파생값이라 프리필에서 제외" in PREVIEW
    # needs_check/빈값이면 빈칸 + 가격 확인 필요(임의 환산 금지)
    assert "document.getElementById('editPrice').value = '';" in PREVIEW
    assert "priceNeedsCheck" in PREVIEW


def test_description_placeholder_is_hint_not_filler():
    # 마케팅성 안내문이 실제 설명처럼 보이지 않게 — 짧은 힌트 + '비워두면 저장되지 않아요'
    assert "전환율이 올라갑니다" not in PREVIEW
    assert "비워두면 저장되지 않아요" in PREVIEW
