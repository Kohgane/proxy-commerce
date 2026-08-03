"""tests/test_v87_s3_products_screen.py — v87 STEP3 #1: 상품 수집 화면 마감 손질.

■ 무엇이 문제였나 (검수 발견 2건)
1. **죽은 소스.** 이 화면은 Sheets `collected_products` 워크시트를 읽었는데, 거기에 쓰는 코드는
   `src/collectors/cli.py`가 부르는 CollectionManager **하나뿐**이다(웹 경로 호출 0). 수집 상품의
   실제 저장소는 #417/#429 이후 PG `collect_history`다. 즉 **상품이 쌓여 있어도 이 화면만 0건**이었다.
   주문 화면이 죽은 Sheets 소스를 읽던 #562와 같은 결함 — 그래서 같은 방식(PG 우선 + 폴백)으로 고친다.
2. **가짜 성공.** `/dashboard/collect/start`는 로그만 남기고 `{"status":"started"}` 202와
   '수집 작업이 시작되었습니다'를 돌려줬다. 큐도 잡도 없다. 없는 일을 시작했다고 말하지 않는다.

■ 킬리스트(개발자스러움 제거)
- 존재하지 않는 필드를 세던 KPI 'Amazon N · Taobao M'(항상 0·0) → 소싱처 수 · 번역 완료 수.
- 하드코딩 선택지 '전체 마켓/Amazon/Taobao' → 실제 수집된 소싱처 도메인.
- 채울 수 없는 컬럼(SKU·마켓 — 등록 전 상품엔 없다) → 소싱처·수집가·수집시각.

■ 화면 수 동결
신규 라우트 0.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SRC = Path("src/dashboard/web_ui.py").read_text(encoding="utf-8")

_PG_ROWS = [
    {"id": "1", "collected_at": "2026-08-01T10:00:00+00:00", "source": "extension",
     "domain": "rakuten.co.jp", "url": "https://item.rakuten.co.jp/shop/abc/",
     "title": "折りたたみカップホルダー", "image_url": "", "price": "2480", "currency": "JPY",
     "status": "ok", "preview_url": "",
     "extra_json": json.dumps({"title_ko": "접이식 컵홀더"}, ensure_ascii=False), "seller_id": "u1"},
    {"id": "2", "collected_at": "2026-08-02T11:00:00+00:00", "source": "bookmarklet",
     "domain": "amazon.com", "url": "https://amazon.com/dp/X",
     "title": "Phone Grip", "image_url": "", "price": "", "currency": "",
     "status": "ok", "preview_url": "", "extra_json": "{}", "seller_id": "u1"},
]


@pytest.fixture()
def client():
    import os
    os.environ["DASHBOARD_UI_ENABLED"] = "1"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "a@b.c"; s["user_role"] = "admin"
    return c


@pytest.fixture()
def pg_products(monkeypatch):
    """PG collect_history가 살아 있는 상태를 만든다."""
    from src.db import collect_history_pg
    from src.dashboard import web_ui
    monkeypatch.setattr(collect_history_pg, "list_items", lambda **kw: [dict(r) for r in _PG_ROWS])
    monkeypatch.setattr(web_ui, "_load_collected_products", lambda: web_ui._pg_collected_rows())
    return _PG_ROWS


# ── 죽은 소스 ─────────────────────────────────────────────────────────────────

def test_source_is_pg_first_with_honest_fallback():
    seg = SRC.split("def _load_collected_products")[1].split("\ndef ")[0]
    assert "pg_enabled()" in seg, "PG 위임이 없다 — 죽은 Sheets 소스로 되돌아갔다"
    assert "_pg_collected_rows()" in seg
    assert "logger.warning" in seg, "PG 조회 실패를 빈 목록으로 위장한다"


def test_pg_rows_mapped_to_screen_vocabulary(monkeypatch):
    from src.db import collect_history_pg
    from src.dashboard import web_ui
    monkeypatch.setattr(collect_history_pg, "list_items", lambda **kw: [dict(r) for r in _PG_ROWS])
    rows = web_ui._pg_collected_rows()
    assert len(rows) == 2
    a = rows[0]
    assert a["domain"] == "rakuten.co.jp" and a["price_original"] == "2480" and a["currency"] == "JPY"
    # 번역본은 extra_json 안에 있다 — 못 펴면 화면이 전부 '원문'으로 보인다.
    assert a["title_ko"] == "접이식 컵홀더"
    # extra_json이 비어도 떨어지지 않는다.
    assert rows[1]["title_ko"] == "" and rows[1]["domain"] == "amazon.com"


def test_existing_products_never_render_zero(client, pg_products):
    """★ 이 화면의 핵심 계약 — 수집된 상품이 있는데 목록이 0건이면 red."""
    body = client.get("/dashboard/products").get_data(as_text=True)
    assert "접이식 컵홀더" in body, "PG에 있는 상품이 화면에 안 나온다"
    assert "rakuten.co.jp" in body
    assert "총 2개" in body


# ── 가짜 성공 ─────────────────────────────────────────────────────────────────

def test_collect_start_no_longer_claims_it_started(client):
    r = client.post("/dashboard/collect/start?format=json")
    assert r.status_code == 501, "없는 작업을 시작했다고 202로 답한다"
    data = r.get_json()
    assert data["status"] == "not_implemented"
    assert "시작되었습니다" not in data["message"]
    assert data["collect_url"] == "/seller/collect"


def test_collect_start_html_sends_user_to_the_real_entry_point(client):
    r = client.post("/dashboard/collect/start")
    assert r.status_code in (301, 302)
    assert "/seller/collect" in r.headers.get("Location", "")


def test_no_fake_started_copy_reaches_the_user(client, pg_products):
    """소스 주석이 아니라 **사용자에게 나가는 것**을 본다(주석에는 무엇을 없앴는지 남겨 둔다)."""
    assert "시작되었습니다" not in client.post("/dashboard/collect/start?format=json").get_data(as_text=True)
    assert "시작되었습니다" not in client.get("/dashboard/products").get_data(as_text=True)


def test_products_screen_button_is_not_a_dead_trigger():
    """버튼이 아무 일도 안 하는 POST를 쏘지 않는다 — 실제 수집 진입점으로 보낸다."""
    seg = SRC.split('def products()')[1].split("\n@web_ui_bp")[0]
    assert 'action="/dashboard/collect/start"' not in seg
    assert 'href="/seller/collect"' in seg


# ── 킬리스트: 채울 수 없는 열·하드코딩 선택지·존재하지 않는 필드 ──────────────

def test_table_drops_columns_that_can_never_be_filled(client, pg_products):
    body = client.get("/dashboard/products").get_data(as_text=True)
    head = body.split("<thead>")[1].split("</thead>")[0]
    # 등록 전 수집 상품에는 SKU도 판매 마켓도 없다 — 있는 척하는 빈 열은 드로어 PCC와 같은 죽은 필드다.
    assert "SKU" not in head
    assert "소싱처" in head and "수집가" in head and "수집시각" in head


def test_filter_options_come_from_real_data_not_hardcoded(client, pg_products):
    body = client.get("/dashboard/products").get_data(as_text=True)
    assert 'value="rakuten.co.jp"' in body and 'value="amazon.com"' in body
    assert "전체 소싱처" in body
    # 하드코딩 선택지는 고를 때마다 0건이었다.
    assert ">Taobao<" not in body


def test_filter_options_survive_being_filtered(client, pg_products):
    """한 소싱처를 고르고 나서도 다른 소싱처로 옮길 수 있어야 한다."""
    body = client.get("/dashboard/products?domain=amazon.com").get_data(as_text=True)
    assert 'value="rakuten.co.jp"' in body, "필터 적용 후 선택지가 사라져 되돌아갈 수 없다"
    assert "총 1개" in body


def test_price_without_currency_is_honest(client, pg_products):
    """가격이 없으면 0원으로 지어내지 않는다."""
    body = client.get("/dashboard/products").get_data(as_text=True)
    assert "2480 JPY" in body
    assert "가격 확인 필요" in body


def test_dashboard_kpi_stops_counting_a_field_that_does_not_exist(client, pg_products, monkeypatch):
    from src.dashboard import web_ui
    monkeypatch.setattr(web_ui, "_load_orders", lambda: [])
    body = client.get("/dashboard/").get_data(as_text=True)
    assert "Amazon" not in body and "Taobao" not in body, "존재하지 않는 필드를 세어 항상 0을 보여준다"
    assert re.search(r"소싱처\s*2곳", body), body[body.find("수집 상품"):][:300]
    assert "번역 완료 1" in body
