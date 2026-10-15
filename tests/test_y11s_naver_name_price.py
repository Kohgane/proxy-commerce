"""Y11-S(오너 2026-10-16 07:46 캡처) — 네이버 상품명 중괄호 · 원문 줄 「확인 필요」 · 팝업 판매가 · 쿠팡 갱신 큐 틱.

운영 실측(읽기 전용, VRSUK 4ebaf1b8):
  - 네이버 상품명 「[해외직구] VRSUK{비즈니스 시리즈} 심플 리클라이너 …」 — Y11-D 괄호 규칙은 쿠팡명에만 있었다.
  - 편집 화면 원문 줄은 `title_en`(「VRSUK{商务系列}简约伊姆斯躺椅油蜡皮Eames…」)을 `mask_marks`에 통과시켜
    伊姆斯·Eames 자리에 「확인 필요」를 끼워 넣었다(Y6-C A3).
  - 등록 기록 4건 모두 `price: {}` — `UploadResult.price`(M8-8)를 채우고도 `DispatchResult.to_dict()`가 빼먹었다.
    그래서 팝업이 지금 마진(기본 25%)으로 다시 계산해 「3,013,210원」 — 실제 전송은 4,784,940원(옵션가 맞춤).
"""
import json

import pytest


@pytest.fixture
def state(monkeypatch):
    import src.db.image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: json.loads(json.dumps(box.get(k) or {})))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, json.loads(json.dumps(v))))
    return box


# ── 1. 중괄호 규칙 — 전 마켓 공통 제목 · 네이버/11번가 상품명 ────────────────────────────────────────

@pytest.mark.parametrize("raw, want", [
    ("VRSUK{비즈니스 시리즈} 심플 리클라이너 오일 왁스 가죽", "VRSUK 비즈니스 시리즈 심플 리클라이너 오일 왁스 가죽"),
    ("VRSUK{商务系列}简约躺椅", "VRSUK 简约躺椅"),                      # 한자만 든 묶음은 통째로(원문 표시용 아님 — 나가는 제목)
    ("수행 방패{SPORTLINK} 세트", "수행 방패 (SPORTLINK) 세트"),
    ("가방 { } 크로스", "가방 크로스"),
    ("[해외직구] 그대로 (S) 사이즈", "[해외직구] 그대로 (S) 사이즈"),     # 대괄호·둥근 괄호는 손대지 않는다
    ("짝 없는 } 괄호", "짝 없는 괄호"),
])
def test_unbrace_title(raw, want):
    from src.collectors.ko_polish import unbrace_title
    assert unbrace_title(raw) == want


def test_polish_ko_applies_unbrace():
    from src.collectors.ko_polish import polish_ko
    assert "{" not in polish_ko("VRSUK{비즈니스 시리즈} 심플 리클라이너") and "비즈니스 시리즈" in polish_ko("VRSUK{비즈니스 시리즈} 심플")


def test_outbound_title_unbraced_for_every_market():
    from src.seller_console.upload_dispatcher import apply_outbound_text
    pd = apply_outbound_text({"title_ko": "VRSUK{비즈니스 시리즈} 심플 리클라이너", "title": "VRSUK{비즈니스 시리즈} 심플",
                              "description": ""})
    assert pd["title_ko"] == "VRSUK 비즈니스 시리즈 심플 리클라이너" and "{" not in pd["title"]


def test_naver_and_elevenst_prepare_product_names():
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    from src.uploaders.elevenst_uploader import ElevenStUploader
    col = {"title_ko": "VRSUK{비즈니스 시리즈} 심플 리클라이너", "sell_price_krw": 1000}
    nv = NaverSmartStoreUploader.__new__(NaverSmartStoreUploader).prepare_product(col)
    assert nv["title"] == "[해외직구] VRSUK 비즈니스 시리즈 심플 리클라이너"
    up = ElevenStUploader.__new__(ElevenStUploader)
    up.CATEGORY_MAP, up.default_category = {}, "1"
    assert ElevenStUploader.prepare_product(up, col)["title"] == "[해외직구] VRSUK 비즈니스 시리즈 심플 리클라이너"


# ── 1b. 이미 올라간 네이버 상품 — 이름만 수정(GET → name만 → PUT) ─────────────────────────────────────

class _NaverUp:
    def __init__(self, name, status="SALE", put_res=None):
        self.cur = {"originProduct": {"name": name, "statusType": status, "salePrice": 4784940, "detailContent": "<p>x</p>"},
                    "smartstoreChannelProduct": {"channelProductNo": 13813465384}, "other": 1}
        self.put = put_res if put_res is not None else {}
        self.sent = []

    def _api_request(self, method, path, data=None):
        if method == "GET":
            return json.loads(json.dumps(self.cur))
        self.sent.append(data)
        return self.put


def _bind(fake):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    for name in ("_modify_origin", "update_name", "update_detail_content"):
        setattr(fake, name, getattr(N, name).__get__(fake))
    return fake


def test_update_name_changes_only_the_name():
    up = _bind(_NaverUp("[해외직구] VRSUK{비즈니스 시리즈} 심플 리클라이너"))
    from src.collectors.ko_polish import unbrace_title
    res = up.update_name("13752236154", unbrace_title)
    assert res["success"] and res["after_name"] == "[해외직구] VRSUK 비즈니스 시리즈 심플 리클라이너"
    body = up.sent[0]
    assert body["originProduct"]["name"] == res["after_name"]
    assert body["originProduct"]["salePrice"] == 4784940 and body["originProduct"]["detailContent"] == "<p>x</p>"
    assert "other" not in body and body["smartstoreChannelProduct"] == {"channelProductNo": 13813465384}


def test_update_name_without_braces_sends_nothing():
    up = _bind(_NaverUp("[해외직구] 깨끗한 이름"))
    res = up.update_name("1", lambda n: __import__("src.collectors.ko_polish", fromlist=["x"]).unbrace_title(n))
    assert res["success"] and res["unchanged"] and up.sent == []


def test_update_name_refused_status_and_rejection_raw():
    up = _bind(_NaverUp("A{B}", status="WAIT"))
    assert not up.update_name("1", lambda n: "A B")["success"] and up.sent == []
    up = _bind(_NaverUp("A{B}", put_res={"error": "HTTP 400", "http_status": 500, "body": '{"code":"X"}'}))
    r = up.update_name("1", lambda n: "A B")
    assert not r["success"] and r["raw"] == '{"code":"X"}'


def test_update_detail_content_still_works():
    up = _bind(_NaverUp("n"))
    r = up.update_detail_content("1", "<p>new</p>")
    assert r["success"] and up.sent[0]["originProduct"]["detailContent"] == "<p>new</p>" and up.sent[0]["originProduct"]["name"] == "n"


def test_fix_name_records_result_on_upload_record():
    from src.services import naver_name_fix as nnf
    ex = {"uploaded": [{"market": "smartstore:chezgoga", "product_id": "13752236154", "channel_product_no": "13813465384"}]}
    saved = {}
    fake = _bind(_NaverUp("[해외직구] VRSUK{비즈니스 시리즈} 심플"))
    out = nnf.fix_name({"id": "it", "extra_json": json.dumps(ex)}, "smartstore:chezgoga", save=saved.update,
                       make_up=lambda a: fake)
    assert out["ok"] and out["after"] == "[해외직구] VRSUK 비즈니스 시리즈 심플"
    rec = saved["uploaded"][0]["name_fix"]
    assert rec["before"].endswith("{비즈니스 시리즈} 심플") and nnf.line({"name_fix": rec}).startswith("상품명 고침:")
    assert nnf.fix_name({"id": "it", "extra_json": "{}"}, "smartstore:chezgoga")["ok"] is False


def test_status_popup_kicks_name_fix_once(monkeypatch):
    """팝업이 지금 네이버 이름에서 중괄호를 보면 이름 고침을 한 번 시작한다(기록이 있으면 다시 안 함)."""
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    import src.seller_console.listing_status as MS
    import src.seller_console.views as V
    MS.reset_cache()
    ex = {"uploaded": [{"market": "smartstore:chezgoga", "product_id": "13752236154", "channel_product_no": "13813465384"}]}
    iid = S.append(source="extension", url="https://x/2", seller_id="y11s-nf", title="t", price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    monkeypatch.setattr(MS, "_naver", lambda rec: {"sid": "13813465384", "state": "approved", "label": "판매중",
                                                   "live_name": "[해외직구] VRSUK{비즈니스 시리즈} 심플", "error": ""})
    kicked = []
    monkeypatch.setattr(V, "_kick_naver_name_fix", lambda item_id, market: kicked.append(market))
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y11s-nf", user_email="y11s-nf@example.com", user_role="seller")
    d = c.get(f"/seller/collect/{iid}/market-status?phase=status").get_json()
    row = d["rows"][0]
    assert kicked == ["smartstore:chezgoga"] and "고쳐 보내는 중" in row["name_fix_line"] and row["live_name"].endswith("심플")
    MS.reset_cache()


# ── 2. 원문 줄 — 원문 그대로 · 걸린 상표는 배지 ─────────────────────────────────────────────────────

def test_gated_names_order_and_dedupe():
    from src.collectors.ko_polish import gated_names
    t = "VRSUK{商务系列}简约伊姆斯躺椅油蜡皮Eames办公旋转升降现货单椅"
    names = gated_names(t)
    assert names[:2] == ["伊姆斯", "Eames"]
    assert gated_names("깨끗한 원문") == []


def test_editor_shows_original_verbatim_with_mark_badge():
    from src.seller_console import collect_history_store as S
    from src.order_webhook import app
    src = "VRSUK{商务系列}简约伊姆斯躺椅油蜡皮Eames办公旋转升降现货单椅"
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=9", seller_id="y11s-orig", title="VRSUK 리클라이너",
                   price="6995", currency="CNY", extra={"title": src, "title_en": src, "title_ko": "VRSUK 리클라이너",
                                                        "price": "6995", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11s-orig"
    h = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    line = [ln for ln in h.splitlines() if "const _ORIG_TITLE_SHOWN" in ln][0]
    assert json.loads(line.split("=", 1)[1].strip().rstrip(";")) == src and "확인 필요" not in line
    assert "상표 확인 필요: 伊姆斯 · Eames" in h


# ── 3. 팝업 판매가 = 실제 전송값 ───────────────────────────────────────────────────────────────────

def test_price_serialized_into_dispatch_result():
    from src.seller_console.upload_dispatcher import DispatchResult, UploadResult
    r = UploadResult(market="smartstore:chezgoga", success=True, message="ok",
                     price={"sell_krw": 4118850, "margin_pct": 40, "line": "… → 10원 올림 4,118,850원"},
                     sent={"sale_price": 4784940, "price_how": "option"})
    d = DispatchResult(product_url="u", results=[r]).to_dict()["results"][0]
    assert d["price"]["sell_krw"] == 4118850 and d["sent"]["sale_price"] == 4784940


@pytest.mark.parametrize("rec, want", [
    ({"sent": {"sale_price": 4784940, "price_how": "option"}, "price": {"sell_krw": 4118850, "margin_pct": 40}},
     "보낸 판매가 4,784,940원(옵션가 맞춤) · 계산값 4,118,850원(마진 40%)에서 바뀜"),
    ({"sent": {"sale_price": 3592100, "price_how": "calc"}, "price": {"sell_krw": 3592100, "line": "원가 … → 10원 올림 3,592,100원"}},
     "보낸 판매가 3,592,100원(계산값) · 원가 … → 10원 올림 3,592,100원"),
    ({"sent": {}, "price": {}}, "등록 당시 값 기록 없음"),
    ({}, "등록 당시 값 기록 없음"),
])
def test_registered_price_line(rec, want):
    from src.seller_console.listing_status import _price_line
    assert _price_line(rec) == want


def test_naver_upload_returns_sent_price_and_name(monkeypatch):
    """계산값이 0원 옵션 규칙으로 거부되고 옵션가 맞춤으로 다시 보내 통과하면, 그 값·그 규칙·그 이름을 돌려준다(등록 기록 → 팝업)."""
    from src.uploaders import naver_detail, naver_options, naver_categories
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    monkeypatch.setattr(naver_detail, "judge", lambda html, up, sku: {"ok": True, "html": "<p>x</p>", "dropped": [], "cached": 0})

    def fake_plan(product, stock_default=999, base_override=0, base_override_how=""):
        if base_override:
            return {"mode": "combo", "sale_price": base_override, "base_how": base_override_how}
        return {"mode": "combo", "sale_price": 4118850, "base_how": "calc", "base_alt": 4784940, "base_alt_how": "option"}
    monkeypatch.setattr(naver_options, "plan", fake_plan)
    monkeypatch.setattr(naver_options, "record_probe", lambda *a, **k: None)
    monkeypatch.setattr(naver_options, "price_related_400", lambda body: True)
    monkeypatch.setattr(naver_categories, "pick", lambda p: ("50003682", "manual"))
    monkeypatch.setattr(naver_categories, "hold", lambda p, account="": None)
    up = N.__new__(N)
    up.image_upload_enabled = False
    up.account = "chezgoga"
    up.STOCK_QUANTITY = 999
    monkeypatch.setattr(up, "find_template_leaks", lambda payload: [], raising=False)
    name = "[해외직구] VRSUK 비즈니스 시리즈"
    monkeypatch.setattr(up, "_build_product_payload",
                        lambda product: {"originProduct": {"name": name, "salePrice": int(product["_option_plan"]["sale_price"])}},
                        raising=False)
    calls = []

    def api(method, path, data=None):
        calls.append(data["originProduct"]["salePrice"])
        if len(calls) == 1:
            return {"error": "400", "http_status": 400, "body": "NoZeroStock"}
        return {"originProductNo": 13752236154, "smartstoreChannelProductNo": 13813465384}
    monkeypatch.setattr(up, "_api_request", api, raising=False)
    monkeypatch.setattr(up, "product_url", lambda ch: f"https://smartstore.naver.com/x/products/{ch}", raising=False)
    out = up.upload_product({"sku": "748639898871", "title": "t", "item_id": "it"})
    assert out.get("success"), out
    assert calls == [4118850, 4784940]
    assert out["sent"] == {"sale_price": 4784940, "price_how": "option", "name": name}


# ── 4. 쿠팡 상세 갱신 큐 — 번역 드레인 틱이 깨운다 ────────────────────────────────────────────────────

def test_tick_kicks_coupang_drain_only_when_queue_nonempty(monkeypatch, state):
    import src.pricing.cron as C
    import src.services.coupang_detail_refresh as R
    from src.utils import bg_job
    started = []
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (started.append(name), (True, {}))[1])
    monkeypatch.setattr("src.seller_console.translate_worker.drain_once", lambda **k: {"processed": 0, "remaining": 0})
    monkeypatch.setattr(C, "_run_pilot_finish_tick", lambda **k: {"gated": True})
    monkeypatch.setattr("src.services.image_translate_auto.kick", lambda: None)
    from src.services import workers
    monkeypatch.setattr(workers, "lease", lambda *a, **k: True)
    monkeypatch.setattr(workers, "release", lambda *a, **k: None)
    monkeypatch.setattr(workers, "record_run", lambda *a, **k: None)
    from src.order_webhook import app
    C._tick_lock.acquire(blocking=False)
    r1 = C._run_full_tick(app, limit=1, pilot_chunk=1, tick_budget=30)
    assert "coupang_detail_kick" not in r1 and started == []
    state[R.QUEUE_KEY] = {"rows": [{"item_id": "it", "market": "coupang:gogane", "sid": "1", "reason": "번역 대기"}]}
    C._tick_lock.acquire(blocking=False)
    r2 = C._run_full_tick(app, limit=1, pilot_chunk=1, tick_budget=30)
    assert r2.get("coupang_detail_kick") is True and started == ["coupang-detail-refresh"]


def test_record_last_trims_rows(state):
    import src.services.coupang_detail_refresh as R
    R.record_last({"picked": 2, "sent": 1, "ok": 0, "left": 2,
                   "rows": [{"market": "coupang:gogane", "sent": True, "ok": False, "body": "x" * 5000,
                             "detail_image": {"state": "rejected"}, "secret": "nope"}]})
    v = state[R.LAST_KEY]
    assert v["picked"] == 2 and len(v["rows"][0]["body"]) == 1500 and "secret" not in v["rows"][0]
    assert v["rows"][0]["detail_image"]["state"] == "rejected"


def test_editor_title_field_unbraced_but_original_kept():
    from src.seller_console import collect_history_store as S
    from src.order_webhook import app
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=10", seller_id="y11s-ed", title="t",
                   price="1", currency="CNY", extra={"title": "VRSUK{商务系列}简约躺椅", "title_ko": "VRSUK{비즈니스 시리즈} 심플",
                                                      "price": "1", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11s-ed"
    h = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    ex = json.loads([ln for ln in h.splitlines() if "const _EXTRA =" in ln][0].split("=", 1)[1].strip().rstrip(";"))
    assert ex["title_ko"] == "VRSUK 비즈니스 시리즈 심플" and ex["title"] == "VRSUK{商务系列}简约躺椅"
    stored = json.loads(S.get(iid)["extra_json"])
    assert stored["title_ko"] == "VRSUK{비즈니스 시리즈} 심플"                     # 저장값은 셀러가 저장할 때만
