"""M6(오너 2026-10-08) — 「검토 상태 보기」 팝업.

실측(오너 폰 16:26 KST): 쿠팡 우주대행 16407690349 등록 성공 → 「검토 상태 보기」가 아무것도 안 보여 줌.
이제 팝업이 마켓에 그때 묻는다(60초 캐시): 쿠팡 statusName·반려 사유·Wing 딥링크(오너 실주소 형식),
스마트스토어 statusType·판매자센터, 11번가 등은 「상태 조회 미연동」 그대로. 마지막 상태는 수집 행에 남는다.
"""
from __future__ import annotations

import json
import os

import pytest

from src.seller_console import listing_status as MS

WING = "https://wing.coupang.com/tenants/seller-web/vendor-inventory/modify?vendorInventoryId=16407690349"


@pytest.fixture(autouse=True)
def _reset():
    MS.reset_cache()
    yield
    MS.reset_cache()


def _extra():
    return {"uploaded": [
        {"market": "smartstore:chezgoga", "market_label": "스마트스토어 — 셰고가", "product_id": "12345", "account": "chezgoga",
         "at": "2026-10-08T07:30:00+00:00"},
        {"market": "coupang:woojoo", "market_label": "쿠팡 — 우주대행", "product_id": "16407690349", "account": "woojoo",
         "at": "2026-10-08T07:26:18+00:00"},
        {"market": "coupang", "market_label": "쿠팡", "external_url": "https://www.coupang.com/vp/products/16401838524",
         "at": "2026-10-02T09:54:59+00:00", "review": {"state": "approved", "label": "승인"}},
        {"market": "elevenst", "market_label": "11번가", "product_id": "9001", "at": "2026-10-08T08:00:00+00:00"},
    ]}


def test_records_order_backfill_and_tone():
    recs = MS.records(_extra())
    assert [r["market"] for r in recs] == ["coupang:woojoo", "coupang", "smartstore:chezgoga", "elevenst"]
    legacy = recs[1]
    assert legacy["product_id"] == "16401838524"                         # 예전 기록은 주소에서 번호를 읽는다(소급)
    assert legacy["tone"] == "ok" and legacy["state_label"] == "승인"
    assert recs[0]["chip"] == "쿠팡·우주대행" and recs[0]["tone"] == "wait"


class _FakeCoupang:
    calls = 0

    def review_status(self, sid):
        _FakeCoupang.calls += 1
        return {"sid": sid, "state": "rejected", "label": "반려", "status_raw": "승인반려",
                "comment": "대표 이미지에 텍스트가 있습니다", "link": "", "wing_url": WING, "error": ""}


@pytest.fixture
def coupang(monkeypatch):
    from src.seller_console import views as V
    _FakeCoupang.calls = 0
    monkeypatch.setattr(V, "_coupang_up_for", lambda account: _FakeCoupang())
    return _FakeCoupang


def test_coupang_status_reason_wing_link_and_60s_cache(coupang):
    rec = MS.records(_extra())[0]
    row = MS.query(rec, now=1000.0)
    assert row["state"] == "rejected" and row["status_raw"] == "승인반려"
    assert row["comment"] == "대표 이미지에 텍스트가 있습니다"
    assert row["manage_url"] == WING and row["manage_label"] == "Wing에서 열기"
    assert row["tone"] == "bad" and row["cached"] is False
    assert MS.query(rec, now=1030.0)["cached"] is True and coupang.calls == 1      # 60초 안엔 다시 안 묻는다
    MS.query(rec, now=1061.0)
    assert coupang.calls == 2


def test_coupang_wing_url_uses_owner_pattern():
    from src.uploaders.coupang_uploader import CoupangUploader
    assert CoupangUploader.wing_modify_url("16407690349") == WING


def test_naver_status_and_seller_center(monkeypatch):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    monkeypatch.setattr(SS, "_api_request", lambda self, m, p, data=None: {
        "originProduct": {"statusType": "UNADMISSION"}, "smartstoreChannelProduct": {"channelProductNo": 777}})
    row = MS.query(MS.records(_extra())[2])
    assert (row["state"], row["label"], row["status_raw"]) == ("pending", "승인대기", "UNADMISSION")
    assert row["manage_url"] == "https://sell.smartstore.naver.com/" and row["link"] == ""
    MS.reset_cache()
    monkeypatch.setattr(SS, "_api_request", lambda self, m, p, data=None: {"originProduct": {"statusType": "SALE"},
                                                                          "smartstoreChannelProduct": {"channelProductNo": 777}})
    # Y7-J: 구매자 주소 = 스토어 주소(셰고가 chezgoga) + 채널 상품번호
    assert MS.query(MS.records(_extra())[2])["link"] == "https://smartstore.naver.com/chezgoga/products/777"
    MS.reset_cache()
    monkeypatch.setattr(SS, "_api_request", lambda self, m, p, data=None: {"error": "네이버 거부 — http_status=404 body={...}"})
    row = MS.query(MS.records(_extra())[2])
    assert row["state"] == "unknown" and "http_status=404" in row["error"] and row["tone"] == "fail"


def test_unsupported_markets_say_so():
    row = MS.query(MS.records(_extra())[3])
    assert row["state"] == "unsupported" and "상태 조회 미연동" in row["label"]
    assert row["manage_url"] == "https://soffice.11st.co.kr/"


@pytest.fixture
def item():
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=6", seller_id="m6-own",
                    title="플리츠 미니멀 여성 여름 세트", price="168", currency="CNY",
                    extra=dict(_extra(), title_ko="플리츠 미니멀 여성 여름 세트"))


def _client(uid="m6-own", role="seller"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role=role)
    return c


def test_route_one_market_persists_last_state(item, coupang):
    d = _client().get(f"/seller/collect/{item}/market-status?market=coupang:woojoo").get_json()
    assert d["ok"] and [r["market"] for r in d["rows"]] == ["coupang:woojoo"]
    from src.seller_console import collect_history_store as S
    ex = json.loads(S.get(item, seller_ids={"m6-own"})["extra_json"])
    woo = [u for u in ex["uploaded"] if u["market"] == "coupang:woojoo"][0]
    assert woo["review"]["state"] == "rejected" and woo["review"]["comment"] == "대표 이미지에 텍스트가 있습니다"


def test_failed_lookup_keeps_last_known_state(item, monkeypatch):
    from src.seller_console import views as V

    class Boom:
        def review_status(self, sid):
            raise RuntimeError("HTTP 401 Invalid signature")
    monkeypatch.setattr(V, "_coupang_up_for", lambda account: Boom())
    d = _client().get(f"/seller/collect/{item}/market-status?market=coupang").get_json()
    assert "HTTP 401 Invalid signature" in d["rows"][0]["error"]                 # 원문 그대로
    from src.seller_console import collect_history_store as S
    ex = json.loads(S.get(item, seller_ids={"m6-own"})["extra_json"])
    assert [u for u in ex["uploaded"] if u["market"] == "coupang"][0]["review"]["state"] == "approved"


def test_route_is_owner_scoped(item):
    assert _client("stranger").get(f"/seller/collect/{item}/market-status").status_code == 404


def test_list_badge_opens_popup(item):
    h = _client().get("/seller/collect/history").get_data(as_text=True)
    # M7: 목록은 마켓별 칩 — 칩이 팝업을 연다(data-market-status)
    assert 'data-role="mk-chip"' in h and 'data-market-status="coupang:woojoo"' in h and f'data-item="{item}"' in h
    assert 'id="kgpMarketStatus"' in h


@pytest.mark.skipif(not os.path.exists("/opt/pw-browsers/chromium") and not os.environ.get("KGP_REQUIRE_BROWSER"),
                    reason="브라우저 없음")
def test_popup_390px_shows_state_reason_and_wing(item, coupang):
    """실브라우저 390px: 목록 「쿠팡·우주대행」 칩 → 팝업에 우주대행 「반려」·사유·「Wing에서 열기」(오너 주소 형식)."""
    pytest.importorskip("playwright.sync_api")
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright
    c = _client()
    page = c.get("/seller/collect/history").get_data(as_text=True)
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page(viewport={"width": 390, "height": 900})

        def handle(route):
            u = route.request.url
            if (urlparse(u).hostname or "") != "kgp.test":
                return route.fulfill(status=200, body=b"")
            path = u.split("kgp.test", 1)[-1]
            if path == "/seller/collect/history":
                return route.fulfill(status=200, content_type="text/html", body=page)
            r = c.open(path, method=route.request.method)
            return route.fulfill(status=r.status_code, content_type=r.content_type or "text/plain", body=r.get_data())
        pg.route("**/*", handle)
        pg.goto("http://kgp.test/seller/collect/history")
        pg.click(f'[data-role="mk-chip"][data-item="{item}"][data-market-status="coupang:woojoo"]')
        # M8: 팝업은 2단 — DB 줄이 먼저(「상태 확인 중…」), 마켓 상태가 오면 그 줄이 바뀐다. 상태가 채워진 줄을 잰다.
        pg.wait_for_selector('[data-role=mst-row][data-market="coupang:woojoo"]:not([data-pending])', timeout=15000)
        woo = pg.inner_text('[data-role=mst-row][data-market="coupang:woojoo"]')
        href = pg.get_attribute('[data-role=mst-row][data-market="coupang:woojoo"] [data-role=mst-manage]', "href")
        b.close()
    assert "반려" in woo and "대표 이미지에 텍스트가 있습니다" in woo and "Wing에서 열기" in woo
    assert href == WING
