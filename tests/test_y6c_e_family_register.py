"""Y6-C E(오너 2026-10-07 21:17 KST, 가족 폰 iPhone Safari) — 「등록 버튼이 안 눌려요」 + 카드 「계정 기본 (미설정)」.

원인(코드·운영 DB):
- 발주 경로 기본값은 **셀러별 키**(`ship_route:<seller>`)로만 읽었다 → 가족은 자기 키(빈 값)라 오너가 정해도 「미설정」.
  (운영 DB 실측: ship_route 키 0건 — 오너도 아직 안 정했다. 요율은 env라 오너·가족 같은 값.)
- 등록 버튼은 사전검증 결과가 올 때까지 `disabled` — 눌러도 아무 일도, 아무 말도 없었다.
  운영 DB `prevalidate_job:*` 0건(전체 기간) — 그 시간 사전검증 작업이 한 번도 시작되지 않았다.
수리: 공유 마켓 사용자(관리자·`FAMILY_EMAILS`)는 발주 경로를 공유 한 벌로 읽고 쓴다 · 검증 전 등록 버튼은
「사전검증부터」 모드(눌리면 사전검증) · 막힌 이유는 버튼 밑 한 줄. 검증 없이 바로 등록되는 길은 없다.
"""
from __future__ import annotations

import json
import os
import re

import pytest

FAM, OWNER, STRANGER = "fam@example.com", "owner@example.com", "stranger@example.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FAMILY_EMAILS", FAM)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    for k, v in {"WC_URL": "https://shop.example.com", "WC_KEY": "ck_test", "WC_SECRET": "cs_test"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("SHIPPING_RATE_KRW_PER_KG_CN", raising=False)
    monkeypatch.setenv("SHIPPING_RATE_KRW_PER_KG_CN_FORWARDER", "9000")
    monkeypatch.delenv("SHIPPING_RATE_KRW_PER_KG_CN_DIRECT", raising=False)
    from src.db import image_translate_queue_pg as st
    for k in ("ship_route:shared", "ship_route:fam-e", "ship_route:owner-e", "ship_route:str-e",
              "market_pick:default:shared", "market_pick:last:shared",
              "ship_settings:shared", "ship_settings:fam-e", "ship_settings:owner-e", "ship_settings:str-e"):
        st.state_set(k, {})
    from src.seller_console import shipping_ratio as SR
    monkeypatch.setattr(SR, "_fx", lambda c: 190.0 if c == "CNY" else None)
    yield


def _client(kind):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"fam": dict(user_id="fam-e", user_email=FAM, user_role="seller"),
                  "owner": dict(user_id="owner-e", user_email=OWNER, user_role="admin"),
                  "stranger": dict(user_id="str-e", user_email=STRANGER, user_role="seller")}[kind])
    return c


def _item(seller):
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=511822926875", seller_id=seller,
                    title="이식 현대 디자이너 소파 의자 회전식 1인용 의자", price="1225", currency="CNY",
                    extra={"title": "意式现代设计师沙发椅 旋转单人椅", "price": "1225", "currency": "CNY",
                           "images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"],
                           "detail_specs": [["尺寸", "50x40x30cm"], ["毛重", "8kg"]],  # Z6: 대형화물이 아닌 크기(이 테스트는 공유 설정을 본다)
                           "skus": [{"spec": ["灰色"], "price": 1225}], "options": [{"name": "颜色", "values": ["灰色"]}]})


def _card(kind, seller):
    iid = _item(seller)
    return iid, _client(kind).get(f"/seller/m/item/{iid}").get_data(as_text=True)


def _mode_on(h):
    import re as _re
    m = _re.search(r'class="m5-mode-btn is-on" data-mode="(\w+)"', h)
    return m.group(1) if m else ""


def test_family_card_shows_owner_ship_route_and_rate():
    """E3 · Z6(2026-10-08) 갱신: 발주 경로 드롭다운은 배송비 엔진의 「배송 설정」으로 바뀌었다 — 오너가 정한 공유 설정
    (기본 모드 항공·정밀검수)이 가족 카드의 배송비에 그대로 쓰인다."""
    r = _client("owner").post("/seller/settings/shipping", data={"provider": "percenty", "default_mode": "air",
                                                                 "addons": ["precise_inspect"], "lcl_threshold_cbm": "0.5"})
    assert r.status_code == 200 and "저장했어요" in r.get_data(as_text=True)
    from src.db import image_translate_queue_pg as st
    saved = st.state_get("ship_settings:shared")
    assert saved["default_mode"] == "air" and saved["addons"] == ["precise_inspect"]      # 오너 셀러 키가 아니라 공유 한 벌
    _iid, h = _card("fam", "fam-e")
    assert _mode_on(h) == "air"
    line = re.search(r'data-role="m5-ship-line">(.*?)<ul', h, re.S).group(1)
    assert "퍼센티 배대지 항공" in line and "부가서비스 3,000원" in line
    _iid, ho = _card("owner", "owner-e")
    assert _mode_on(ho) == "air"                                                           # 오너 자신도 같은 값


def test_family_save_writes_shared_and_stranger_is_isolated():
    _client("fam").post("/seller/settings/shipping", data={"provider": "percenty", "default_mode": "air", "lcl_threshold_cbm": "0.5"})
    from src.db import image_translate_queue_pg as st
    assert st.state_get("ship_settings:shared")["default_mode"] == "air"
    assert not (st.state_get("ship_settings:fam-e") or {}).get("default_mode")
    _iid, h = _card("stranger", "str-e")                                                    # 공개 가입자는 오너 값을 못 본다
    assert _mode_on(h) == "sea"
    _client("stranger").post("/seller/settings/shipping", data={"provider": "percenty", "default_mode": "sea", "lcl_threshold_cbm": "0.5"})
    assert st.state_get("ship_settings:shared")["default_mode"] == "air"                   # 남이 공유 값을 못 바꾼다
    assert st.state_get("ship_settings:str-e")["default_mode"] == "sea"


def test_legacy_own_key_still_read_when_shared_empty():
    from src.seller_console import shipping_ratio as SR
    SR.save_account_route("owner-e", "direct", shared=False)                    # 옛 저장(셀러 키)
    assert SR.account_route("owner-e", shared=True) == "direct"
    SR.save_account_route("owner-e", "forwarder", shared=True)
    assert SR.account_route("owner-e", shared=True) == "forwarder"


def test_family_card_market_rows_follow_owner_setting():
    """오너가 정한 「기본 등록 마켓」(공유 한 벌)이 가족 카드의 처음 체크 — 키는 오너 서버 값으로 연결됨."""
    _client("owner").post("/seller/settings", data={"codes": ["woocommerce"]})
    _iid, h = _card("fam", "fam-e")
    assert re.search(r'value="woocommerce" checked', h)
    wc = h.split('data-market="woocommerce"')[1][:600]
    assert 'data-role="m5-unconnected"' not in wc                               # 가족도 오너 키로 연결됨
    _iid, hs = _card("stranger", "str-e")
    assert 'value="woocommerce" checked' not in hs                               # 공개 가입자: 오너 설정·키 없음


def test_register_button_is_live_before_check_and_hint_says_why():
    _iid, h = _card("fam", "fam-e")
    btn = re.search(r'<button[^>]*data-role="m5-register"[^>]*>', h).group(0)
    assert 'data-mode="check"' in btn and "disabled" not in btn
    assert "누르면 사전검증부터 해요 — 통과한 마켓에만 등록돼요." in h


@pytest.mark.skipif(not os.path.exists("/opt/pw-browsers/chromium") and not os.environ.get("KGP_REQUIRE_BROWSER"),
                    reason="브라우저 없음")
def test_family_tap_register_runs_prevalidate_then_enables(monkeypatch):
    """실브라우저(390px): 가족 카드에서 「등록」을 먼저 누르면 → 사전검증 POST(등록 POST 0) → 통과 → 「등록 (1곳)」 켜짐."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    _client("owner").post("/seller/settings", data={"codes": ["woocommerce"]})
    iid, html = _card("fam", "fam-e")
    seen = []
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page(viewport={"width": 390, "height": 900})

        def handle(route):
            u, meth = route.request.url, route.request.method
            if u.endswith(f"/seller/m/item/{iid}"):
                route.fulfill(status=200, content_type="text/html", body=html)
                return
            seen.append((meth, u.split("kgp.test")[-1]))
            if meth == "POST" and u.endswith("/seller/collect/prevalidate"):
                body = json.loads(route.request.post_data or "{}")
                assert body.get("async") is True and body.get("markets") == ["woocommerce"]
                route.fulfill(status=202, content_type="application/json",
                              body=json.dumps({"ok": True, "job_id": "j1", "poll": "/seller/collect/prevalidate/job/j1"}))
            elif "/prevalidate/job/" in u:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"ok": True, "state": "done", "pending": [], "results": [
                        {"market": "woocommerce", "market_label": "WooCommerce", "ok": True, "hold": False, "fixes": []}]}))
            else:
                route.fulfill(status=200, content_type="application/json", body="{}")
        pg.route("**/*", handle)
        pg.goto(f"http://kgp.test/seller/m/item/{iid}")
        assert pg.evaluate("document.getElementById('m5Go').disabled") is False
        pg.click("#m5Go")
        for _ in range(60):
            if pg.inner_text("#m5Go").startswith("등록 ("):
                break
            pg.wait_for_timeout(100)
        text, disabled = pg.inner_text("#m5Go"), pg.evaluate("document.getElementById('m5Go').disabled")
        mode, hint = pg.evaluate("document.getElementById('m5Go').dataset.mode"), pg.inner_text("#m5GoHint")
        b.close()
    assert text == "등록 (1곳)" and disabled is False and mode == "go" and hint == ""
    assert ("POST", "/seller/collect/prevalidate") in seen
    assert not any(u.endswith("/seller/collect/upload") for _m, u in seen)          # 첫 탭은 검증만 — 등록 0회
