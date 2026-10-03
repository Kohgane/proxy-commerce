"""W(통합, 오너 2026-10-03) — 계정 키 매핑 · 네이버 주문 폴러 · 워커 단일 실행.

W0 쿠팡: 고가네 = 기본 계정(무접두 COUPANG_* 키 + COUPANG_GOGANE_* 배송지) · 우주대행 = COUPANG_WOOJOO_*만
   네이버: 스토어 자기 키 → 없으면 공용 키(실측 주인) · 둘 다 있는데 값이 다르면 경고 · 진단 「계정 키 출처」
W1 주문 캐너리: 최근 N일 결제완료 목록(구매자 정보 없음) — 스마트스토어센터 숫자와 대조
W2 워커: 배포에선 WORKERS_ENABLED=1 서비스만 · DB 리스로 서비스 간 한 곳 · 서비스별 실행 기록 · 진단 「워커 실행 서비스」
"""
from __future__ import annotations

import pytest

_BASE = {"COUPANG_ACCESS_KEY": "base-ak", "COUPANG_SECRET_KEY": "base-sk", "COUPANG_VENDOR_ID": "A01381223"}
_GOGANE_SHIP = {"COUPANG_GOGANE_RETURN_CENTER_CODE": "G-RC", "COUPANG_GOGANE_OUTBOUND_SHIPPING_PLACE_CODE": "G-OB",
                "COUPANG_GOGANE_VENDOR_USER_ID": "gogane-wing"}
_WOOJOO = {"COUPANG_WOOJOO_ACCESS_KEY": "w-ak", "COUPANG_WOOJOO_SECRET_KEY": "w-sk", "COUPANG_WOOJOO_VENDOR_ID": "A01504840",
           "COUPANG_WOOJOO_RETURN_CENTER_CODE": "W-RC", "COUPANG_WOOJOO_OUTBOUND_SHIPPING_PLACE_CODE": "W-OB",
           "COUPANG_WOOJOO_VENDOR_USER_ID": "woojoo-wing"}


@pytest.fixture
def coupang_env(monkeypatch):
    import os
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    for k, v in {**_BASE, **_GOGANE_SHIP, **_WOOJOO}.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def _up_for(account):
    from src.seller_console.market_cred_view import coupang_account
    from src.channel_sync.coupang_uploader import make_uploader
    with coupang_account(account):
        return make_uploader()


# ── W0 쿠팡 ────────────────────────────────────────────────────────────────────

def test_gogane_uses_base_keys_and_gogane_shipping(coupang_env):
    up, acct = _up_for("gogane")
    assert acct == "gogane"
    assert (up.access_key, up.secret_key, up.vendor_id) == ("base-ak", "base-sk", "A01381223")
    assert (up.return_center_code, up.outbound_place_code, up.vendor_user_id) == ("G-RC", "G-OB", "gogane-wing")


def test_woojoo_uses_only_woojoo_keys_and_shipping(coupang_env):
    up, acct = _up_for("woojoo")
    assert acct == "woojoo"
    assert (up.access_key, up.secret_key, up.vendor_id) == ("w-ak", "w-sk", "A01504840")
    assert (up.return_center_code, up.outbound_place_code, up.vendor_user_id) == ("W-RC", "W-OB", "woojoo-wing")
    for k in ("COUPANG_WOOJOO_ACCESS_KEY", "COUPANG_WOOJOO_SECRET_KEY"):
        coupang_env.delenv(k)
    up2, _ = _up_for("woojoo")
    assert up2.access_key == "" and up2.secret_key == ""                 # 무접두(고가네) 키를 빌리지 않는다


def test_both_accounts_pass_the_credential_part_of_prevalidate(coupang_env):
    from src.seller_console.market_cred_view import coupang_api_state, coupang_shipping_state
    for acct in ("gogane", "woojoo"):
        assert coupang_api_state(acct)["missing"] == []
        assert not [e for e, _ in coupang_shipping_state(acct)["missing"]
                    if e.endswith(("RETURN_CENTER_CODE", "OUTBOUND_SHIPPING_PLACE_CODE", "VENDOR_USER_ID"))]


def test_key_source_says_where_each_account_reads_from(coupang_env):
    from src.pipeline.coupang_replicate import coupang_key_source
    g, w = coupang_key_source("gogane"), coupang_key_source("woojoo")
    assert g["key_source"] == "기본(무접두)" and g["ready"] and g["ship_source"] == "COUPANG_GOGANE_*" and g["note"] is None
    assert w["key_source"] == "계정 접두" and w["ready"] and w["ship_source"] == "COUPANG_WOOJOO_*"
    coupang_env.setenv("COUPANG_VENDOR_ID", "A09999999")
    assert "고가네(기본 계정)로 쓰는 중" in coupang_key_source("gogane")["note"]


# ── W0 네이버 ──────────────────────────────────────────────────────────────────

def test_naver_key_report_and_mismatch_warning(monkeypatch):
    from src.seller_console import smartstore_routing as SR
    for k in ("NAVER_CHEZGOGA_CLIENT_ID", "NAVER_CHEZGOGA_CLIENT_SECRET", "NAVER_GOCOSMOS_CLIENT_ID", "NAVER_GOCOSMOS_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "common-id")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "common-sec")
    monkeypatch.setattr(SR, "promoted_store", lambda: "chezgoga")
    rep = {r["store"]: r for r in SR.naver_key_report()}
    assert rep["chezgoga"]["common_promoted"] and "공용 NAVER_COMMERCE_* 사용" in rep["chezgoga"]["note"]
    assert rep["gocosmos"]["note"] == "키 없음" and rep["gocosmos"]["own_env"] == "NAVER_GOCOSMOS_CLIENT_ID/_SECRET"
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_ID", "other-id")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_SECRET", "other-sec")
    monkeypatch.setenv("NAVER_GOCOSMOS_CLIENT_ID", "g")
    monkeypatch.setenv("NAVER_GOCOSMOS_CLIENT_SECRET", "g")
    rep = {r["store"]: r for r in SR.naver_key_report()}
    assert rep["chezgoga"]["mismatch"] and "값이 다름" in rep["chezgoga"]["note"]
    assert rep["gocosmos"]["own"] and rep["gocosmos"]["note"] == "자기 키 사용"          # 고코스모스 키 도착
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_ID", "common-id")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_SECRET", "common-sec")
    assert not {r["store"]: r for r in SR.naver_key_report()}["chezgoga"]["mismatch"]


# ── W2 워커 ────────────────────────────────────────────────────────────────────

def test_workers_gate(monkeypatch):
    from src.services import workers as W
    monkeypatch.delenv("WORKERS_ENABLED", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert W.workers_enabled() is True                                    # 로컬·테스트 = 예전처럼
    monkeypatch.setenv("RENDER", "true")
    assert W.workers_enabled() is False and "배포라 꺼짐" in W.gate_text()  # 배포 + 미설정 = 접수만
    monkeypatch.setenv("WORKERS_ENABLED", "1")
    assert W.workers_enabled() is True
    monkeypatch.setenv("WORKERS_ENABLED", "0")
    monkeypatch.delenv("RENDER")
    assert W.workers_enabled() is False


def test_disabled_service_only_enqueues(monkeypatch):
    from src.services import option_translate_auto as O
    from src.services import image_translate_auto as I
    started = []
    monkeypatch.delenv("OPTION_TRANSLATE_AUTO_OFF", raising=False)
    monkeypatch.delenv("OPTION_TRANSLATE_AUTO_SYNC", raising=False)
    monkeypatch.delenv("IMAGE_TRANSLATE_AUTO_SYNC", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("WORKERS_ENABLED", "0")
    monkeypatch.setattr("threading.Thread.start", lambda self: started.append(self.name))
    O.kick(); I.kick()
    assert started == []


def test_lease_is_exclusive_across_services(monkeypatch):
    from src.services import workers as W
    monkeypatch.setattr(W, "_pg_on", lambda: False)
    W._MEM.clear()
    monkeypatch.setattr(W, "_holder", lambda: "kohganeproxxxxy-singapore:1")
    assert W.lease("optko-auto", ttl=60)
    monkeypatch.setattr(W, "_holder", lambda: "proxy-commerce:7")
    assert not W.lease("optko-auto", ttl=60)                              # 다른 서비스는 못 잡는다
    monkeypatch.setattr(W, "_holder", lambda: "kohganeproxxxxy-singapore:1")
    W.release("optko-auto")
    monkeypatch.setattr(W, "_holder", lambda: "proxy-commerce:7")
    assert W.lease("optko-auto", ttl=60)                                   # 놓으면 이어받는다
    W._MEM.clear()


def test_runs_are_recorded_per_service(monkeypatch):
    from src.services import workers as W
    from src.db import image_translate_queue_pg as Q
    Q.state_set("workers:runs", {})
    monkeypatch.setenv("RENDER_SERVICE_NAME", "kohganeproxxxxy-singapore")
    W.record_run("optko-auto", 3)
    W.record_run("optko-auto", 2)
    monkeypatch.setenv("RENDER_SERVICE_NAME", "proxy-commerce")
    W.record_run("optko-auto", 1)
    runs = Q.state_get("workers:runs")
    assert runs["kohganeproxxxxy-singapore"]["optko-auto"]["runs_today"] == 2
    assert runs["kohganeproxxxxy-singapore"]["optko-auto"]["items_today"] == 5
    assert runs["proxy-commerce"]["optko-auto"]["items_today"] == 1
    snap = {w["name"]: w for w in W.snapshot()["workers"]}
    assert set(snap["optko-auto"]["runs"]) == {"kohganeproxxxxy-singapore", "proxy-commerce"}
    Q.state_set("workers:runs", {})


def test_naver_order_worker_is_off_unless_asked(monkeypatch):
    from src.order_alerts import naver_worker as NW
    monkeypatch.delenv("NAVER_ORDER_POLL", raising=False)
    assert NW.start_if_enabled().startswith("꺼짐 — NAVER_ORDER_POLL 미설정")
    monkeypatch.setenv("NAVER_ORDER_POLL", "1")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("WORKERS_ENABLED", "0")
    assert NW.start_if_enabled().startswith("꺼짐 — 이 서비스는 워커 아님")


# ── 진단 화면 ──────────────────────────────────────────────────────────────────

def _admin_client():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner-w"; s["user_role"] = "admin"; s["email"] = "owner@example.com"
    return c


def test_diagnostics_shows_account_keys_and_workers(coupang_env, monkeypatch):
    monkeypatch.setenv("SMARTSTORE_LIVE_PROBE", "0")
    h = _admin_client().get("/admin/diagnostics").get_data(as_text=True)
    assert 'data-role="account-keys"' in h and 'data-role="workers-status"' in h
    assert "쿠팡 — 고가네" in h and "기본(무접두)" in h and "COUPANG_GOGANE_*" in h
    assert "쿠팡 — 우주대행" in h and "COUPANG_WOOJOO_*" in h
    assert "base-ak" not in h and "w-sk" not in h                           # 값은 절대 안 싣는다
    assert "옵션·상품명 번역 큐" in h and "/admin/diagnostics/naver-orders?store=chezgoga" in h


def test_naver_order_canary_lists_without_buyer_pii(monkeypatch):
    from src.order_alerts import naver_order_poller as P
    rows = P.NaverOrderPoller._normalize_orders([{
        "productOrder": {"productOrderId": "2026100312345", "productName": "기계식 키보드", "quantity": 1,
                         "totalPaymentAmount": 129000, "productOrderStatus": "PAYED"},
        "order": {"orderId": "2026100300001", "ordererName": "홍길동", "ordererTel": "010-1234-5678",
                  "paymentDate": "2026-10-03T10:00:00.000+09:00"}}], store="chezgoga")
    seen = {}
    monkeypatch.setattr(P.NaverOrderPoller, "fetch_window", lambda self, a, b: seen.update(store=self.store, days=(b - a).days) or rows)
    h = _admin_client().get("/admin/diagnostics/naver-orders?store=chezgoga&days=7").get_data(as_text=True)
    assert seen == {"store": "chezgoga", "days": 7}
    assert "1건" in h and "129,000원" in h and "2026100312345" in h and "기계식 키보드" in h
    assert "홍길동" not in h and "010-1234-5678" not in h                    # 구매자 정보 미표시
    monkeypatch.setattr(P.NaverOrderPoller, "fetch_window",
                        lambda self, a, b: (_ for _ in ()).throw(P.NaverOrderError('HTTP 403: {"code":"GW.IP_NOT_ALLOWED"}')))
    h = _admin_client().get("/admin/diagnostics/naver-orders?store=gocosmos").get_data(as_text=True)
    assert 'data-role="naver-orders-err"' in h and "GW.IP_NOT_ALLOWED" in h


def test_naver_order_window_splits_into_24h_and_pages(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from src.order_alerts.naver_order_poller import NaverOrderPoller
    calls = []

    def api(self, method, path, data=None):
        calls.append((method, path))
        if "last-changed-statuses" in path:
            if "moreSequence" not in path and len([c for c in calls if "last-changed" in c[1]]) == 1:
                return {"data": {"lastChangeStatuses": [{"productOrderId": "A1"}], "more": {"moreSequence": "S2"}}}
            return {"data": {"lastChangeStatuses": [{"productOrderId": "A2"}]}}
        return {"data": [{"productOrder": {"productOrderId": "A1"}}, {"productOrder": {"productOrderId": "A2"}}]}
    monkeypatch.setattr(NaverOrderPoller, "_api", api)
    p = NaverOrderPoller(client_id="x", client_secret="y")
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    ids = p.changed_product_order_ids(now - timedelta(days=3), now)
    windows = [c for c in calls if "last-changed" in c[1] and "moreSequence" not in c[1]]
    assert len(windows) == 3                                               # 24시간 창 셋
    assert any("moreSequence=S2" in c[1] for c in calls)                   # 다음 장
    assert ids[:2] == ["A1", "A2"]
