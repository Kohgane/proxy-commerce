"""오너 11-25 00:58 실기기 「무조건 등록하는 길밖에 없다 · 어떤 순간이든 뺄 수 있게」 — 계약.

① 빼기: a 결과 카드 「이 마켓 빼기」 · b 등록 버튼 둘(통과만 / 보류도) · c 보내는 중 대기 마켓 「취소」·이미 나간 마켓 「이 마켓에서 내리기」(판매중지, 확인 한 번)
   · d 「이 사진 빼기」(등록에서만 · 원본 불변 · 되돌림)
② 사진이 전부 500px 미만이면 전 마켓 보류 · 대표 자동 고르기는 사람 없는 제품 컷 먼저
③ 반쪽 수집(원본 주소 없음·옵션 있는데 SKU 0·원가 없음) → 「수집이 덜 됐어요」
④ 판매수수료율 모르는 마켓 → 유저 화면은 「이 마켓은 아직 준비 중」(체크 해제·비활성) · env 이름은 관리자만
⑤ 쿠팡명: 브랜드(라틴 앞머리)·핵심 스펙(40L) 유지 · 끝 조각(「프리」) 안 남김
⑥ 잡 진행 알약이 내용을 가리지 않게 본문 아래 여백
⑦ 관리자 읽기 진단(스스 상태별 수·키-스토어 대조) — 관리자만
마켓 전송·판매중지는 오너 탭으로만(확인 없으면 거절).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

M5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
CPX = Path("src/seller_console/templates/_coupang_exposure.html").read_text(encoding="utf-8")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app as _app
    _app.config["TESTING"] = True
    return _app


@pytest.fixture
def client(app):
    return app.test_client()


def _item(**over):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "tomtoc 여행 백팩", "images": ["https://img.example/a.jpg", "https://img.example/b.jpg", "https://img.example/c.jpg"]}
    ex.update(over.pop("extra", {}))
    kw = dict(source="extension", url="https://item.taobao.com/item.htm?id=744111222333", title="tomtoc 여행 백팩", price="129.28",
              currency="USD", image="https://img.example/a.jpg", seller_id="default", extra=ex)
    kw.update(over)
    return S.append(**kw)


def _extra(iid):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_id="default")["extra_json"])


# ── ①a·b — 마켓 빼기 · 등록 버튼 둘 ───────────────────────────────────────────

def test_every_result_row_can_be_taken_out_and_put_back():
    assert 'data-role="m5-off-market"' in M5 and "이 마켓 빼기" in M5
    assert 'data-role="m5-readd-market"' in M5 and "다시 넣기" in M5
    # 뺀 마켓은 통과·보류 어느 쪽에도 안 들어간다(등록 대상에서 빠진다)
    assert "okMarkets = pvOrder.filter(function (m) { return !pvOff[m] && pvRows[m] && pvRows[m].ok; });" in M5
    assert "var held = pvOrder.filter(function (m) { return !pvOff[m] && pvRows[m] && overridable(pvRows[m]); });" in M5


def test_two_register_buttons_main_sends_only_passed():
    assert 'id="m5GoHeld"' in M5
    assert "'통과한 ' + n + '곳만 등록'" in M5 and "'보류 ' + held.length + '곳도 그래도 등록'" in M5
    # 주 버튼은 보류를 싣지 않는다 — 보조 버튼을 눌렀을 때만(withHeld)
    assert "var held = withHeld ? (goBtn.dataset.held || '').split(',').filter(Boolean) : [];" in M5
    assert "withHeld = true; register(false);" in M5


# ── ①c — 보내는 중 취소 · 이 마켓에서 내리기 ────────────────────────────────────

def test_send_is_per_market_and_cancellable():
    assert "markets: [m]" in M5                                  # 한 마켓씩
    assert 'data-role="m5-send-cancel"' in M5 and "if (sendCancel[m])" in M5
    assert "cancelled: true" in M5 and "보내지 않았어요." in M5


def test_take_down_button_asks_once_inline_no_native_confirm():
    assert 'data-role="m5-takedown"' in M5 and "이 마켓에서 내리기" in M5
    assert 'data-role="m5-takedown-yes"' in M5 and 'data-role="m5-takedown-no"' in M5
    assert "'/take-down', {market: m, confirm: true}" in M5
    assert "confirm(" not in M5.replace("confirm: true", "").replace("confirmWarn", "").replace("confirmDup", "") \
        .replace("_confirm", "").replace("m5-confirm", "").replace("m5-dup-confirm", "").replace("m5-warn-confirm", "")


def test_take_down_route_needs_confirm_and_a_record(client, monkeypatch):
    iid = _item()
    assert client.post(f"/seller/collect/{iid}/take-down", json={"market": "smartstore"}).status_code == 400
    assert client.post(f"/seller/collect/{iid}/take-down", json={"market": "smartstore", "confirm": True}).status_code == 404


def test_take_down_route_records_verified_result(client, monkeypatch):
    iid = _item(extra={"uploaded": [{"market": "smartstore:shegoga", "channel_product_no": "13894618263", "product_id": "1"}]})
    seen = []
    import src.services.market_takedown as T
    monkeypatch.setattr(T, "take_down", lambda rec: seen.append(rec) or {"ok": True, "status": "SUSPENSION"})
    r = client.post(f"/seller/collect/{iid}/take-down", json={"market": "smartstore:shegoga", "confirm": True})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert seen and seen[0]["channel_product_no"] == "13894618263"
    td = _extra(iid)["takedowns"]
    assert td[-1]["market"] == "smartstore:shegoga" and td[-1]["ok"] is True


def test_take_down_other_market_is_honest():
    from src.services.market_takedown import take_down
    out = take_down({"market": "woocommerce", "product_id": "9"})
    assert out["ok"] is False and "판매자센터" in out["error"]


class _CP:
    def __init__(self, still_on=False):
        self.still_on, self.stopped = still_on, []

    def get_product(self, sid):
        return {"items": [{"vendorItemId": 11}, {"vendorItemId": 12}]}

    def stop_sale(self, vid):
        self.stopped.append(vid)
        return {"ok": True}

    def on_sale(self, vid):
        return self.still_on


def test_take_down_coupang_stops_every_option_and_verifies(monkeypatch):
    import src.services.coupang_relist as R
    from src.services.market_takedown import take_down
    up = _CP()
    monkeypatch.setattr(R, "_uploader", lambda acc: up)
    monkeypatch.setattr(R, "_vids", lambda live: [11, 12])
    out = take_down({"market": "coupang:gogane", "product_id": "13892554342"})
    assert out["ok"] is True and out["stopped"] == 2 and up.stopped == [11, 12]
    up2 = _CP(still_on=True)
    monkeypatch.setattr(R, "_uploader", lambda acc: up2)
    out2 = take_down({"market": "coupang:gogane", "product_id": "13892554342"})
    assert out2["ok"] is False and "판매중으로 읽힘" in out2["error"]       # 다시 읽어 판매중이면 「내렸어요」가 아니다


def test_take_down_smartstore_suspends_and_rereads(monkeypatch):
    import src.uploaders.naver_uploader as N
    from src.services.market_takedown import take_down
    calls = []
    state = {"st": "SALE"}

    def fake(self, method, path, data=None, **kw):
        calls.append((method, path, data))
        if method == "PUT":
            state["st"] = "SUSPENSION"
            return {}
        return {"originProductNo": 777, "originProduct": {"statusType": state["st"]}}
    monkeypatch.setattr(N.NaverSmartStoreUploader, "__init__", lambda self, account=None: None)
    monkeypatch.setattr(N.NaverSmartStoreUploader, "_api_request", fake)
    out = take_down({"market": "smartstore:shegoga", "channel_product_no": "13894618263"})
    assert out["ok"] is True and out["status"] == "SUSPENSION"
    assert ("PUT", "/v1/products/origin-products/777/change-status", {"statusType": "SUSPENSION"}) in calls

    def stays(self, method, path, data=None, **kw):
        return {} if method == "PUT" else {"originProductNo": 777, "originProduct": {"statusType": "SALE"}}
    monkeypatch.setattr(N.NaverSmartStoreUploader, "_api_request", stays)
    out2 = take_down({"market": "smartstore:shegoga", "channel_product_no": "13894618263"})
    assert out2["ok"] is False and "SALE" in out2["error"]                  # 가짜 성공 금지


# ── ①d — 이 사진 빼기 ─────────────────────────────────────────────────────────

def test_photo_exclude_only_affects_registration(client):
    from src.services.image_translate_store import effective_images
    iid = _item()
    r = client.post(f"/seller/collect/{iid}/image-exclude", json={"idx": 1, "on": True})
    assert r.status_code == 200
    ex = _extra(iid)
    assert ex["images"] == ["https://img.example/a.jpg", "https://img.example/b.jpg", "https://img.example/c.jpg"]   # 원본 불변
    assert "https://img.example/b.jpg" not in effective_images(ex)
    # 되돌림
    client.post(f"/seller/collect/{iid}/image-exclude", json={"idx": 1, "on": False})
    assert "https://img.example/b.jpg" in effective_images(_extra(iid))


def test_last_photo_cannot_be_excluded(client):
    iid = _item(extra={"images": ["https://img.example/a.jpg", "https://img.example/b.jpg"]})
    assert client.post(f"/seller/collect/{iid}/image-exclude", json={"idx": 0}).status_code == 200
    r = client.post(f"/seller/collect/{iid}/image-exclude", json={"idx": 1})
    assert r.status_code == 400 and "마지막 한 장" in r.get_json()["error"]


def test_exposure_tiles_have_exclude_and_put_back():
    assert 'data-role="cpx-exclude"' in CPX and "이 사진 빼기" in CPX
    assert 'data-role="cpx-include"' in CPX


# ── ② — 사진 전부 작음 · 대표는 사람 없는 컷 ──────────────────────────────────

def test_all_small_photos_hold_every_market():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": "t", "images": ["https://img.example/a.jpg"], "price": "89", "_imgs_all_small": {"max": 350, "n": 14}}
    for m in ("coupang", "smartstore", "elevenst", "shopify"):
        h = [x for x in UploadDispatcher.readiness_holds(pd, m) if x["fix"] == "small_images"]
        assert h and "350px" in h[0]["line"] and "14장" in h[0]["line"]


def test_best_rep_prefers_product_only_shot():
    from src.services.coupang_image_check import best_rep
    cands = [{"idx": 0, "ok": True, "w": 800, "h": 800, "long_side": 800, "person": True},
             {"idx": 1, "ok": True, "w": 700, "h": 700, "long_side": 700, "person": False}]
    assert best_rep(cands) == 1


# ── ③ — 반쪽 수집 ────────────────────────────────────────────────────────────

def test_incomplete_reasons(app):
    from src.seller_console.views import _incomplete_reasons
    with app.test_request_context():
        short = {"url": "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc", "extra_json": "{}"}
        assert [r["code"] for r in _incomplete_reasons(short, {}, True)] == ["no_source_url"]
        known = {"url": "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc", "extra_json": json.dumps({"item_id_taobao": "744111222333"})}
        assert _incomplete_reasons(known, {}, True) == []
        other = {"url": "https://www.yoshidakaban.com/product/123.html", "extra_json": "{}"}
        assert _incomplete_reasons(other, {}, True) == []              # SKU 규칙이 없는 소싱처도 멀쩡한 원본 주소다
        opts = {"options": [{"name": "색상", "values": ["블랙", "그레이"]}], "skus": []}
        codes = [r["code"] for r in _incomplete_reasons(other, opts, False)]
        assert codes == ["no_skus", "no_price"]


def test_incomplete_screen_has_refetch_and_address():
    assert "m5-incomplete" in M5 and "다시 가져오기" in M5 and "주소 넣기" in M5


# ── ④ — 수수료 모르는 마켓 ─────────────────────────────────────────────────────

def test_unknown_commission_market_is_not_ready_for_users(app, monkeypatch):
    from src.seller_console.views import _mark_not_ready
    monkeypatch.delenv("MARKET_COMMISSION_PCT_WOOCOMMERCE", raising=False)
    with app.test_request_context():
        ms = [{"code": "woocommerce", "checked": True}, {"code": "coupang", "checked": True}, {"code": "coupang:gogane", "checked": True}]
        _mark_not_ready(ms, {})
        assert ms[0]["checked"] is False and ms[0]["not_ready"] == "이 마켓은 아직 준비 중"
        assert "not_ready" not in ms[1] and ms[1]["checked"] is True
        assert "not_ready" not in ms[2] and ms[2]["checked"] is True          # 계정 붙은 코드도 마켓(쿠팡)으로 판정
        ms2 = [{"code": "woocommerce", "checked": True}]
        _mark_not_ready(ms2, {"sell_price_krw": 59000})                  # 셀러가 판매가를 적었으면 그 값이 이긴다
        assert ms2[0]["checked"] is True


def test_unknown_commission_hold_has_no_env_name():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": "t", "images": ["https://img.example/a.jpg"], "price": "89",
          "_commission_probe": {"woocommerce": "woocommerce 판매수수료율이 없습니다 — MARKET_COMMISSION_PCT_WOOCOMMERCE"}}
    [h] = [x for x in UploadDispatcher.readiness_holds(pd, "woocommerce") if x["fix"] == "not_ready"]
    assert "MARKET_COMMISSION" not in h["line"] and "아직 준비 중" in h["line"]
    assert "MARKET_COMMISSION" in h["admin_why"]                         # 관리자에겐 무엇을 설정할지
    assert not [x for x in UploadDispatcher.readiness_holds(pd, "coupang") if x["fix"] == "not_ready"]


# ── ⑤ — 쿠팡명 ──────────────────────────────────────────────────────────────

def test_coupang_name_keeps_brand_and_spec_drops_fragment():
    from src.uploaders.coupang_title import build_name
    p = {"title_ko": "tomtoc 여행 백팩 대용량 휴대 가방 비행 기내 승인 프리 40L 노트북 수납",
         "title": "tomtoc travel backpack 40L flight approved carry on"}
    name = build_name(p)["name"]
    assert "tomtoc" in name and "40L" in name
    assert not name.rstrip().endswith("프리")


# ── ⑥ — 잡 진행 알약 여백 ─────────────────────────────────────────────────────

def test_jobline_pill_reserves_bottom_space():
    css = Path("src/static/m_shell.css").read_text(encoding="utf-8")
    js = Path("src/seller_console/static/m_shell.js").read_text(encoding="utf-8")
    assert "body[data-mshell].kgp-jobline-on { padding-bottom:" in css
    assert "document.body.classList.toggle('kgp-jobline-on', !!on)" in js


# ── ⑦ — 관리자 읽기 진단 ──────────────────────────────────────────────────────

def test_diag_routes_are_admin_only(client):
    assert client.get("/seller/admin/diag/stores?nos=13894618263").status_code == 403
    assert client.get("/seller/admin/diag/item/13894618263").status_code == 403


def test_store_audit_counts_and_mismatch(monkeypatch):
    import src.seller_console.smartstore_routing as R
    import src.uploaders.naver_uploader as N
    from src.services import admin_diag
    monkeypatch.setattr(R, "STORES", ("shegoga",))
    monkeypatch.setattr(R, "store_label", lambda st: "셰고가")
    monkeypatch.setattr(R, "identify_common_key", lambda force=False: {"state": "ok"})

    def init(self, account=None):
        self.client_id, self.client_secret = "id", "sec"
    monkeypatch.setattr(N.NaverSmartStoreUploader, "__init__", init)
    monkeypatch.setattr(N.NaverSmartStoreUploader, "_get_access_token", lambda self: "tok")
    monkeypatch.setattr(N.NaverSmartStoreUploader, "count_products", lambda self, sts: {"SALE": 90, "WAIT": 5, "OUTOFSTOCK": 2}.get(sts[0], 0) if len(sts) == 1 else 97)

    def api(self, method, path, data=None, **kw):
        if path == "/v1/seller/channels":
            return [{"name": "고코스모스", "channelNo": 1}]
        return {"originProduct": {"name": "tomtoc", "statusType": "SALE", "images": {"representativeImage": {"url": "x"}}}}
    monkeypatch.setattr(N.NaverSmartStoreUploader, "_api_request", api)
    out = admin_diag.store_audit(["13894618263"])
    [row] = out["stores"]
    assert row["counts"]["SALE"] == 90 and row["limit_count"] == 97 and set(row["counts"]) == set(admin_diag.STATUSES)
    assert out["mismatch"] and "셰고가" in out["mismatch"][0]               # 셰고가 키가 고코스모스를 가리키면 P0
    assert out["products"]["13894618263"]["shegoga"]["found"] is True
