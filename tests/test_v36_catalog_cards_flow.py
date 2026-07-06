"""tests/test_v36_catalog_cards_flow.py — v36 PART B: catalog 표→카드 + 모바일 액션 흐름 라우트 점검."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

CATALOG = Path("src/seller_console/templates/catalog.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_catalog_table_cards():
    # table-cards는 본문, data-label/cardcell-*는 행 파셜(단일소스)로 이동.
    assert "table-cards" in CATALOG
    ROWS = Path("src/seller_console/templates/catalog_rows.html").read_text(encoding="utf-8")
    for lbl in ('data-label="SKU"', 'data-label="가격"', 'data-label="상태"', 'data-label="마지막 동기화"'):
        assert lbl in ROWS, f"{lbl} 누락"
    assert "cardcell-title" in ROWS and "cardcell-actions" in ROWS


def test_mobile_action_flow_routes_ok(client):
    # 폰에서 쓰는 핵심 액션 화면이 모바일에서도 정상 응답(수집→편집 진입→주문→CS)
    # (manual-collect 등 별칭은 302→최종 200 — follow_redirects로 확인)
    for path in ("/seller/manual-collect", "/seller/collect/history",
                 "/seller/catalog", "/seller/orders", "/seller/cs/inbox"):
        assert client.get(path, follow_redirects=True).status_code == 200, f"{path} 비정상"
