"""Z7(2026-10-07) — 주문은 **누구의 것인가**: 공개 가입자가 오너 마켓 주문을 보거나 바꾸지 못한다.

L1(#837) 이후 누구나 가입한다. 주문 행(`orders`)은 오너 서버의 마켓 자격(전역 환경변수)으로 동기화된
**오너 마켓 주문**이고 `user_id`가 비어 있다(오너 풀). 예전 `/seller/orders` 계열은 스코프가 없어서
갓 가입한 남이 오너 주문 목록·구매자(마스킹)·매출 KPI를 보고, 운송장·상태까지 바꿀 수 있었다
(운송장은 **오너 쿠팡 계정으로** 마켓에 전송된다).

규칙:
- 공유 사용자(관리자 · `FAMILY_EMAILS`) = 오너 풀(`user_id` 빈 행) + 자기 행.
- 그 밖의 로그인 사용자 = 자기 `user_id`(또는 이메일)가 실린 행만. 오너 풀 0건 → 빈 상태(가짜 수치 0).
- 로그인 신원이 없는 요청(크론·인증 꺼진 개발) = 종전 그대로(서버 자신).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

import pytest

OWNER_ROW = "OWN-1"
STRANGER_ROW = "MINE-1"
OTHER_ROW = "OTHER-1"


def _row(order_id, user_id, status="paid", marketplace="coupang"):
    today = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "order_id": order_id, "marketplace": marketplace, "status": status,
        "placed_at": today, "paid_at": today,
        "buyer_name_masked": f"김*{order_id[-1]}", "buyer_phone_masked": "010-****-1234",
        "buyer_address_masked": "서울 **", "total_krw": "39000", "shipping_fee_krw": "0",
        "items_json": '[{"sku":"S1","title":"테스트 상품","qty":1,"unit_price_krw":"39000","options":{}}]',
        "courier": "", "tracking_no": "", "shipped_at": "", "landed_cost_krw": "",
        "margin_krw": "", "margin_pct": "", "last_synced_at": today, "notes": "",
        "user_id": user_id,
    }


@pytest.fixture()
def orders_mem(monkeypatch):
    from src.seller_console.orders import sheets_adapter as oa
    monkeypatch.setattr(oa, "_pg_orders", lambda: None)
    oa._MEM.rows[:] = []
    oa._MEM.upsert_rows([
        _row(OWNER_ROW, ""),                 # 오너 마켓 동기화분(오너 풀)
        _row(STRANGER_ROW, "stranger-1"),    # 가입자 본인 행
        _row(OTHER_ROW, "other-9"),          # 다른 가입자 행
    ])
    yield oa._MEM
    oa._MEM.rows[:] = []


@pytest.fixture()
def market_calls(monkeypatch):
    """오너 자격으로 마켓을 두드리는 호출을 잡는다 — 남의 요청에서 0이어야 한다."""
    calls = []
    from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter

    def _track(self, order_id, **kw):
        calls.append(("tracking", order_id))
        return {"ok": True}

    def _fetch(self, since=None):
        calls.append(("fetch", "coupang"))
        return []

    monkeypatch.setattr(CoupangAdapter, "update_tracking", _track, raising=False)
    monkeypatch.setattr(CoupangAdapter, "fetch_orders_unified", _fetch, raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    return calls


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com")
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")


def _client(user_id, email, role="seller"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = user_id
        s["user_email"] = email
        s["user_role"] = role
    return c


@pytest.fixture()
def stranger(env):
    return _client("stranger-1", "stranger@example.com")


def _status_of(mem, order_id):
    return next(r for r in mem.rows if r["order_id"] == order_id)["status"]


def _tracking_of(mem, order_id):
    return next(r for r in mem.rows if r["order_id"] == order_id)["tracking_no"]


# ── 읽기: 남에게 오너 주문이 안 보인다 ─────────────────────────────────────────

def test_stranger_orders_page_hides_owner_orders(orders_mem, stranger):
    body = stranger.get("/seller/orders").get_data(as_text=True)
    assert OWNER_ROW not in body, "가입자 화면에 오너 마켓 주문이 보인다"
    assert OTHER_ROW not in body, "다른 가입자 주문이 보인다"
    assert STRANGER_ROW in body, "본인 행까지 숨겼다(과잉 차단)"


def test_stranger_orders_page_kpi_counts_only_own(orders_mem, stranger):
    from src.seller_console.orders import sheets_adapter as oa
    orders_mem.rows[:] = [_row(OWNER_ROW, ""), _row("OWN-2", ""), _row("OWN-3", "")]
    body = stranger.get("/seller/orders").get_data(as_text=True)
    assert "아직 주문이 없습니다" in body, "오너 풀 0건인데 빈 상태가 아니다"
    # KPI 4칸 전부 0 — 오너 매출 흐름(발송대기 3)이 새면 안 된다
    import re
    vals = re.findall(r'class="od-stat-v">(\d+)<', body)
    assert vals and all(v == "0" for v in vals), f"가입자 KPI에 오너 수치가 샌다: {vals}"
    assert len(oa._MEM.rows) == 3


def test_stranger_order_detail_404(orders_mem, stranger):
    r = stranger.get(f"/seller/orders/coupang/{OWNER_ROW}")
    assert r.status_code == 404
    assert stranger.get(f"/seller/orders/coupang/{STRANGER_ROW}").status_code == 200


def test_stranger_csv_export_only_own(orders_mem, stranger):
    text = stranger.get("/seller/orders/export.csv").get_data(as_text=True)
    ids = [row[0] for row in csv.reader(io.StringIO(text))][1:]
    assert ids == [STRANGER_ROW], f"CSV에 남의 주문이 섞였다: {ids}"


def test_stranger_mobile_home_hides_owner_orders(orders_mem, stranger):
    r = stranger.get("/seller/m")
    body = r.get_data(as_text=True)
    # 예전엔 주문이 1건만 있어도 500(템플릿 `.get`이 UnifiedOrder에서 터짐) — 그 500이 누수를 가렸다.
    assert r.status_code == 200, "모바일 홈이 주문이 있으면 500"
    assert OWNER_ROW not in body and OTHER_ROW not in body
    assert STRANGER_ROW in body and "테스트 상품" in body


def test_stranger_mobile_empty_state_does_not_promise_sync(orders_mem, stranger):
    orders_mem.rows[:] = [_row(OWNER_ROW, "")]
    body = stranger.get("/seller/m").get_data(as_text=True)
    assert "마켓을 연동하면 주문이 모여요" not in body, "동기화가 없는 계정에 「연동하면 모여요」 약속"
    assert "준비 중" in body


def test_shared_mobile_home_renders_owner_orders(orders_mem, env):
    r = _client("mom-1", "mom@example.com").get("/seller/m")
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and OWNER_ROW in body
    assert "결제완료" in body and ">paid<" not in body, "상태 영문 코드가 그대로 보인다"


def test_stranger_settlement_counts_only_own(orders_mem, stranger, monkeypatch):
    seen = []
    from src.seller_console import net_profit
    real = net_profit.net_profit_summary

    def _spy(orders):
        seen.append([o["order_id"] for o in orders])
        return real(orders)

    monkeypatch.setattr(net_profit, "net_profit_summary", _spy)
    assert stranger.get("/seller/settlement").status_code == 200
    assert seen == [[STRANGER_ROW]], f"정산에 남의 주문이 들어갔다: {seen}"


def test_stranger_orders_auto_hides_owner_orders(orders_mem, stranger):
    body = stranger.get("/seller/orders/auto").get_data(as_text=True)
    assert OWNER_ROW not in body and OTHER_ROW not in body
    res = stranger.post("/seller/orders/auto/process").get_json()
    touched = {r.get("order_id") for r in res.get("results", [])}
    assert OWNER_ROW not in touched and OTHER_ROW not in touched


def test_stranger_dashboard_order_kpi_widget(orders_mem, env):
    from src.order_webhook import app
    from src.seller_console.widgets import build_orders_kpi_widget
    orders_mem.rows[:] = [_row(OWNER_ROW, ""), _row("OWN-2", "")]
    with app.test_request_context():
        from flask import session
        session.update({"user_id": "stranger-1", "user_email": "stranger@example.com", "user_role": "seller"})
        data = build_orders_kpi_widget()["data"]
    assert data["pending_ship"] == 0 and data["today_new"] == 0, f"대시보드 주문 KPI에 오너 수치: {data}"


def test_stranger_analytics_shows_empty_state_not_owner_sales(env, monkeypatch):
    """BI(매출·채널·TOP SKU)는 오너 풀 전체로 계산된다 — 남에겐 엔진도 안 돌고, 「0원」도 안 쓴다."""
    called = []
    from src.analytics import bi_engine

    def _build(self, force_refresh=False):
        called.append(1)
        return {"sales_summary": {"today_krw": 777777, "week_krw": 1, "month_krw": 1, "channel_share": {}},
                "top_products": [], "inventory_alerts": {"low_stock": [], "over_stock": []},
                "ad_roi": {"channels": [], "roas_threshold": 1.5},
                "quality": {"unanswered_24h": 0, "delayed_shipping": 0, "refund_rate": 0.0}}

    monkeypatch.setattr(bi_engine.BIEngine, "build_dashboard", _build)
    r = _client("stranger-1", "stranger@example.com").get("/seller/analytics")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert called == [], "가입자 요청이 오너 BI를 계산했다"
    assert "777777" not in body and "아직 이 계정의 판매 데이터가 없습니다" in body
    assert "오늘 매출" not in body, "모르는 매출을 0원으로 그렸다"
    shared = _client("mom-1", "mom@example.com").get("/seller/analytics").get_data(as_text=True)
    assert "777777" in shared and called == [1]


# ── 쓰기: 남이 오너 주문을 못 바꾼다(마켓 전송 0) ──────────────────────────────

def test_stranger_cannot_change_owner_status(orders_mem, stranger):
    r = stranger.post(f"/seller/orders/coupang/{OWNER_ROW}/status", json={"next_status": "preparing"})
    assert r.status_code == 404
    assert _status_of(orders_mem, OWNER_ROW) == "paid"


def test_stranger_cannot_set_owner_tracking(orders_mem, stranger, market_calls):
    r = stranger.post(f"/seller/orders/coupang/{OWNER_ROW}/tracking",
                      json={"courier": "CJGLS", "tracking_no": "123456789012"})
    assert r.status_code == 404
    assert not r.get_json()["ok"]
    assert _tracking_of(orders_mem, OWNER_ROW) == ""
    assert market_calls == [], f"오너 쿠팡 계정으로 운송장이 나갔다: {market_calls}"


def test_stranger_bulk_tracking_skips_owner(orders_mem, stranger, market_calls):
    r = stranger.post("/seller/orders/bulk/tracking", json={"items": [
        {"order_id": OWNER_ROW, "marketplace": "coupang", "courier": "CJGLS", "tracking_no": "123456789012"}]})
    res = r.get_json()
    assert res["success_count"] == 0 and res["results"][0]["ok"] is False
    assert _tracking_of(orders_mem, OWNER_ROW) == ""
    assert market_calls == []


def test_stranger_bulk_status_skips_owner(orders_mem, stranger):
    res = stranger.post("/seller/orders/bulk/status", json={
        "next_status": "preparing", "items": [{"order_id": OWNER_ROW, "marketplace": "coupang"}]}).get_json()
    assert res["success_count"] == 0
    assert _status_of(orders_mem, OWNER_ROW) == "paid"


def test_stranger_cannot_toggle_owner_sourced(orders_mem, stranger):
    assert stranger.post(f"/seller/orders/coupang/{OWNER_ROW}/sourced").status_code == 404
    assert "[소싱완료]" not in next(r for r in orders_mem.rows if r["order_id"] == OWNER_ROW)["notes"]


def test_stranger_cannot_trigger_owner_sync(orders_mem, stranger, market_calls):
    r = stranger.post("/seller/orders/sync")
    assert r.status_code == 403
    assert market_calls == [], "가입자 요청이 오너 자격으로 마켓 주문을 끌어왔다"


def test_stranger_page_has_no_dead_sync_button(orders_mem, stranger):
    body = stranger.get("/seller/orders").get_data(as_text=True)
    assert 'id="ordersSyncButton"' not in body, "누르면 403만 나는 동기화 버튼이 남아 있다"


def test_stranger_can_still_work_own_order(orders_mem, stranger):
    r = stranger.post(f"/seller/orders/coupang/{STRANGER_ROW}/status", json={"next_status": "preparing"})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert _status_of(orders_mem, STRANGER_ROW) == "preparing"


# ── 공유 사용자·서버 자신은 종전 그대로 ────────────────────────────────────────

@pytest.mark.parametrize("uid,email,role", [
    ("owner-1", "owner@example.com", "seller"),    # ADMIN_EMAILS
    ("owner-2", "x@example.com", "admin"),         # user_role admin
    ("mom-1", "Mom@Example.com", "seller"),        # FAMILY_EMAILS(대소문자 무관)
])
def test_shared_users_see_owner_pool(orders_mem, env, uid, email, role):
    c = _client(uid, email, role)
    body = c.get("/seller/orders").get_data(as_text=True)
    assert OWNER_ROW in body
    assert OTHER_ROW not in body and STRANGER_ROW not in body, "공유 사용자에게 가입자 개인 주문이 보인다"
    assert 'id="ordersSyncButton"' in body
    r = c.post(f"/seller/orders/coupang/{OWNER_ROW}/status", json={"next_status": "preparing"})
    assert r.status_code == 200 and _status_of(orders_mem, OWNER_ROW) == "preparing"


def test_shared_user_tracking_for_unsynced_order_still_reaches_market(orders_mem, env, market_calls):
    """우리 기록에 아직 없는 주문의 송장(동기화 전 일괄 등록)은 공유 사용자에게 종전 그대로 마켓까지 간다."""
    c = _client("mom-1", "mom@example.com")
    c.post("/seller/orders/coupang/NOT-SYNCED-1/tracking", json={"courier": "CJGLS", "tracking_no": "123456789012"})
    assert ("tracking", "NOT-SYNCED-1") in market_calls


def test_shared_user_cannot_touch_other_sellers_row(orders_mem, env, market_calls):
    c = _client("mom-1", "mom@example.com")
    r = c.post(f"/seller/orders/coupang/{OTHER_ROW}/tracking", json={"courier": "CJGLS", "tracking_no": "123456789012"})
    assert r.status_code == 404 and market_calls == []
    assert _tracking_of(orders_mem, OTHER_ROW) == ""


def test_stranger_tracking_for_unsynced_order_never_reaches_owner_market(orders_mem, stranger, market_calls):
    r = stranger.post("/seller/orders/coupang/NOT-SYNCED-1/tracking",
                      json={"courier": "CJGLS", "tracking_no": "123456789012"})
    assert r.status_code == 404 and market_calls == []


def test_shared_user_sync_reaches_markets(orders_mem, env, market_calls):
    c = _client("mom-1", "mom@example.com")
    assert c.post("/seller/orders/sync").status_code == 200
    assert ("fetch", "coupang") in market_calls


def test_no_login_identity_is_server_itself(orders_mem):
    """크론·인증 꺼진 개발(세션 신원 없음) = 오너 서버 자신 — 종전처럼 전부."""
    from src.order_webhook import app
    with app.test_request_context():
        from src.seller_console.orders.sync_service import OrderSyncService
        ids = {o.order_id for o in OrderSyncService().list_orders(limit=50)}
    assert {OWNER_ROW, STRANGER_ROW, OTHER_ROW} <= ids


def test_owner_sync_does_not_steal_seller_row_ownership(orders_mem):
    """오너 동기화가 같은 키 행을 덮어써도 `user_id`(소유)는 바뀌지 않는다."""
    orders_mem.upsert_rows([dict(_row(STRANGER_ROW, ""), status="shipped")])
    row = next(r for r in orders_mem.rows if r["order_id"] == STRANGER_ROW)
    assert row["user_id"] == "stranger-1" and row["status"] == "shipped"


def test_pg_backend_reads_user_id_and_keeps_owner_on_upsert(monkeypatch):
    """PG 백엔드가 **실제로 보내는 SQL**을 가짜 커서로 잡아 본다(소스 문자열 핀 아님 — 메타 계약)."""
    import contextlib
    from src.db import orders_pg

    sent = []

    class _Cur:
        def execute(self, sql, params=None):
            sent.append((sql, params))

        def fetchall(self):
            return [tuple(["stranger-1"] + ["x"] * (len(orders_pg._INSERT_COLS) - 1))]

    @contextlib.contextmanager
    def _cm():
        yield _Cur()
    monkeypatch.setattr(orders_pg.pg, "tx", _cm)
    monkeypatch.setattr(orders_pg.pg, "query", _cm)

    rows = orders_pg.all_row_dicts()
    assert rows[0]["user_id"] == "stranger-1", "PG 읽기가 user_id를 안 실어 스코프 판정이 불가"
    select_sql = sent[-1][0]
    assert select_sql.split("FROM")[0].count("user_id") == 1

    assert orders_pg.upsert_rows([dict(_row(STRANGER_ROW, "stranger-1"))]) == 1
    sql, vals = sent[-1]
    insert_cols, update_set = sql.split("DO UPDATE SET")
    assert "user_id" in insert_cols and vals[0] == "stranger-1"            # 넣을 때만 주인을 쓴다
    assert "user_id" not in update_set, "동기화 upsert가 소유자를 덮어쓴다"
