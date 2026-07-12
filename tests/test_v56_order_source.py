"""tests/test_v56_order_source.py — v56 STEP2: 주문 → 소싱처 원클릭.

주문 항목 → 카탈로그(sku) → 수집 원본(src_url) 역참조. 끊긴 경우 '원본 미연결'+수동 연결. [소싱처에서 주문]
버튼(새 탭)·주문 정보 복사(옵션·수량·수취인)·'소싱 주문 완료' 토글(notes 마커 영속). 데스크톱·모바일 공용.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

ORDERS_TPL = Path("src/seller_console/templates/orders.html").read_text(encoding="utf-8")
ORDERS_JS = Path("src/seller_console/static/orders.js").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


class _FakeCL:
    def lookup_by_sku(self, sku):
        return {"sku": sku, "title_ko": "가방", "src_url": "https://taobao.com/item/999"} if sku == "BAG-1" else None


def test_source_info_reverse_lookup():
    from src.seller_console.views import _order_source_info
    order = {"order_id": "O1", "marketplace": "coupang", "buyer_name_masked": "홍*동", "notes": "",
             "items": [{"sku": "BAG-1", "title": "가방", "qty": 2, "options": {"색상": "블랙"}}]}
    with patch("src.orders.catalog_lookup.CatalogLookup", _FakeCL):
        si = _order_source_info(order)
    assert si["linked"] is True and si["source_url"] == "https://taobao.com/item/999"
    assert "가방" in si["copy_text"] and "색상:블랙" in si["copy_text"] and "x2" in si["copy_text"]
    assert "수취인: 홍*동" in si["copy_text"]      # 마스킹된 수취인만
    assert si["sourced"] is False


def test_source_info_unlinked_and_sourced_flag():
    from src.seller_console.views import _order_source_info
    order = {"order_id": "O2", "marketplace": "x", "notes": "[소싱완료] 메모",
             "items": [{"sku": "", "title": "수동상품", "qty": 1, "options": {}}]}
    with patch("src.orders.catalog_lookup.CatalogLookup", _FakeCL):
        si = _order_source_info(order)
    assert si["linked"] is False                  # sku 미매칭 → 원본 미연결
    assert si["sourced"] is True                   # notes 마커 → 소싱완료


def test_orders_template_buttons():
    assert "소싱처에서 주문" in ORDERS_TPL and "원본 미연결" in ORDERS_TPL and "수동 연결" in ORDERS_TPL
    assert "주문 정보 복사" in ORDERS_TPL and "소싱 주문 완료" in ORDERS_TPL
    assert "kgpCopyOrder" in ORDERS_TPL and "kgpToggleSourced" in ORDERS_TPL
    assert "cardcell-actions" in ORDERS_TPL         # 모바일 카드에서도 동일 버튼(v36 .table-cards)


def test_orders_js_copy_and_toggle():
    assert "function kgpCopyOrder" in ORDERS_JS and "clipboard" in ORDERS_JS and "execCommand" in ORDERS_JS
    assert "function kgpToggleSourced" in ORDERS_JS and "/sourced" in ORDERS_JS


def test_sourced_endpoint_toggles_notes():
    from src.order_webhook import app
    from types import SimpleNamespace

    class _Order:
        def __init__(self, notes):
            self.order_id = "O1"; self.marketplace = "coupang"
            self.status = SimpleNamespace(value="paid"); self.notes = notes
    calls = {}

    class _Backend:
        def update_status(self, oid, mp, status, note, ts):
            calls["note"] = note; calls["status"] = status; return True

    class _Svc:
        def list_orders(self, **k): return [_Order("")]
    with patch("src.seller_console.views._get_order_sync_service", return_value=_Svc()), \
         patch("src.seller_console.orders.sheets_adapter._order_backend", return_value=_Backend()):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
            r = c.post("/seller/orders/coupang/O1/sourced")
            d = r.get_json()
    assert d["ok"] and d["sourced"] is True         # 마커 추가
    assert "[소싱완료]" in calls["note"] and calls["status"] == "paid"   # notes 영속·상태 불변


def test_orders_page_renders():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        assert c.get("/seller/orders").status_code == 200   # 빈 주문이어도 200
