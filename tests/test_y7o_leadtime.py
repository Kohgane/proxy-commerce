"""Y7-O(오너 2026-10-12 12:28 KST 그분 폰, 타오바오 ICE) — 옵션 값 번역 검사 오탐 + 발송 소요 분리.

증거: 옵션 값 「泡泡粉（2-3周发货）」「黑色（2-3周发货）」 → 쿠팡 고가네·우주대행·셰고가·고코스모스·11번가 전부 보류
「번역기 값이 원문의 영문·숫자(2-3)를 잃었습니다」(Papago 99,852 남음 — 한도 아님). 번역기는 「2~3주」로 옮겼다.
운영 DB 저장값(01f38481, Pedestal Viva TV 스탠드, 10-12 13:24 KST 수집): 값 사이는 괄호가 아니라 **제어문자 0x04 두 개** —
「泡泡粉\x04\x042-3周发货」 · 색 10개 · SKU 10개. 폰의 □가 이것이다. 아래 VALS는 그 저장값 그대로.
대조(변화 0): 플리츠 세트 `ae9cee70` 저장 옵션.
"""
from __future__ import annotations

import json

import pytest

VALS = ["泡泡粉\x04\x042-3周发货", "黑色\x04\x042-3周发货"]                      # 운영 저장값 그대로
OPTS = [{"name": "颜色分类", "values": list(VALS), "values_ko": ["거품 파우더는 2~3주 후 발송", "검은색은 2~3주 내에 발송"]}]
SKUS = [{"spec": [VALS[0]], "price": "720.0", "stock": 10, "sku_id": "1"},
        {"spec": [VALS[1]], "price": "980.0", "stock": 10, "sku_id": "2"}]
PL_OPTS = [{"name": "颜色分类", "values": ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"],
            "name_ko": "색상", "values_ko": ["블랙 상의", "블랙 스커트", "블루 상의", "블루 스커트", "모스 그린 상의", "모스 그린 스커트",
                                           "로열 블루 상의", "로열 블루 스커트"]},
           {"name": "尺码", "values": ["均码"], "name_ko": "사이즈", "values_ko": ["프리사이즈"]}]


def _ex():
    return {"title": "x", "options": json.loads(json.dumps(OPTS)), "skus": json.loads(json.dumps(SKUS))}


# ── 1. 숫자 보존 검사 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ko", ["버블 핑크(2~3주 배송)", "버블 핑크 (2-3주)", "버블 핑크(2–3주)", "버블 핑크 2 to 3주",
                                "버블 핑크(2∼3주)", "버블 핑크（２〜３주）"])
def test_1_range_separators_are_equivalent(ko):
    from src.uploaders.coupang_options import lost_tokens, resolve_option_value
    for src in (VALS[0], "泡泡粉（2-3周发货）"):                                     # 운영 저장값(0x04) · 화면 표기(전각 괄호)
        assert lost_tokens(src, ko) == []
        r = resolve_option_value(src, values_ko=ko)
        assert r["value"] and "잃었습니다" not in (r.get("why") or "")


@pytest.mark.parametrize("v", ["泡泡粉\x04\x042-3周发货", "泡泡粉（2-3周发货）", "泡泡粉(2-3周发货)", "泡泡粉 2-3周发货"])
def test_2_parse_forms(v):
    from src.collectors.option_leadtime import parse
    p = parse(v)
    assert (p["core"], p["raw"], p["min_days"], p["max_days"]) == ("泡泡粉", "2-3周发货", 14, 21)


def test_1_real_losses_still_hold():
    from src.uploaders.coupang_options import lost_tokens
    assert lost_tokens("PD20W快充", "고속 충전") == ["PD20W"]                     # 영문 토큰 — 원문 표기 그대로
    assert lost_tokens("2-3周", "3주") == ["2"]                                    # 숫자를 잃음
    assert lost_tokens("1.8米", "1.8m") == [] and lost_tokens("3-2", "2-3") == ["2"]   # 순서도 본다


# ── 2. 발송 소요 분리 ─────────────────────────────────────────────────────────────────────────

def test_2_split_values_skus_and_lead_time():
    from src.collectors import option_leadtime as L
    ex = _ex()
    ex["option_value_overrides"] = {VALS[0]: "핑크"}
    rec = L.apply(ex)
    assert rec["state"] == "split"
    o = ex["options"][0]
    assert o["values"] == ["泡泡粉", "黑色"] and o["values_ko"] == ["", ""]              # 핵심만 다시 옮긴다
    assert o["lead_time"]["泡泡粉"] == {"raw": "2-3周发货", "kind": "lead", "min_days": 14, "max_days": 21}
    assert [k["spec"] for k in ex["skus"]] == [["泡泡粉"], ["黑色"]]
    assert [(k["price"], k["stock"], k["sku_id"]) for k in ex["skus"]] == [("720.0", 10, "1"), ("980.0", 10, "2")]
    assert ex["options_src"][0]["values"] == VALS and ex["skus_src"][0]["spec"] == [VALS[0]]   # 원문 보관
    assert ex["option_value_overrides"] == {"泡泡粉": "핑크"}
    assert L.apply(ex) is None                                                    # 두 번 하지 않는다
    tok = json.loads(open("src/uploaders/option_leadtime.json", encoding="utf-8").read())
    assert tok["units"]["周"] == 7 and "预售" in tok["presale_words"] and tok["max_days"] == {"coupang": 20, "smartstore": 14}


def test_2_collision_axis_is_left_alone():
    from src.collectors import option_leadtime as L
    ex = {"options": [{"name": "颜色", "values": ["黑色（现货）", "黑色（2-3周发货）"]}],
          "skus": [{"spec": ["黑色（现货）"], "price": 1, "stock": 1}, {"spec": ["黑色（2-3周发货）"], "price": 1, "stock": 1}]}
    assert L.apply(ex) is None and ex["options"][0]["values"] == ["黑色（现货）", "黑色（2-3周发货）"]


def test_2_rule_pass_splits_first_then_translates_core():
    from src.services import option_translate_auto as A
    ex = _ex()
    st = A.rule_pass(ex)
    assert st["changed"] and ex["options"][0]["values"] == ["泡泡粉", "黑色"]
    assert VALS[0] not in st["pending"] and "泡泡粉" in st["pending"]                # 번역기엔 핵심 값만


def test_2_pleats_unchanged():
    from src.collectors import option_leadtime as L
    ex = {"options": json.loads(json.dumps(PL_OPTS)), "skus": [{"spec": ["黑色上衣", "均码"], "price": 168, "stock": 3}]}
    before = json.dumps(ex, ensure_ascii=False, sort_keys=True)
    assert L.apply(ex) is None and json.dumps(ex, ensure_ascii=False, sort_keys=True) == before
    assert L.summary(ex) is None and L.hold(ex, "coupang") is None and L.caution(ex) == ""


# ── 3. 주의 칩 · 보류 · 마켓 칸 ───────────────────────────────────────────────────────────────

def test_3_hold_caution_and_caps():
    from src.collectors import option_leadtime as L
    ex = _ex()
    L.apply(ex)
    assert L.caution(ex) == "선주문 — 발송 2~3주"
    hc = L.hold(ex, "coupang:woojoo")
    assert hc["fix"] == "lead_time" and "상한 20일" in hc["line"] and "2-3周发货" in hc["line"]
    assert "상한 14일" in L.hold(ex, "smartstore:gocosmos")["line"]
    assert L.hold(ex, "elevenst")["fix"] == "lead_time"                            # 자동 체인은 마켓 무관 보류
    assert L.days_for(ex, "coupang") == 20 and L.days_for(ex, "smartstore:chezgoga") == 14
    assert L.hold({**ex, "lead_time_override": {"at": "x"}}, "coupang") is None      # 「선주문 그래도 등록」


def test_3_market_fields_after_override():
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    assert N.expected_delivery(14) == {"customProductAfterOrderYn": True, "expectedDeliveryPeriodType": "FOURTEEN"}
    assert N.expected_delivery(0) == {} and N.expected_delivery(1)["expectedDeliveryPeriodType"] == "TWO"
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.collectors import option_leadtime as L
    ex = _ex()
    L.apply(ex)
    pd = {"title": "버블 핑크 선풍기", "options": ex["options"], "skus": ex["skus"], "lead_time_override": {"at": "x"}}
    assert UploadDispatcher._payload_for_market(pd, "coupang")[0]["lead_time_days"] == 20
    assert UploadDispatcher._payload_for_market(pd, "smartstore")[0]["lead_time_days"] == 14
    from src.channel_sync._channel_bridge import to_collected
    assert to_collected({"lead_time_days": 20})["lead_time_days"] == 20
    assert to_collected({})["lead_time_days"] == 0


def test_3_coupang_outbound_days(monkeypatch):
    """쿠팡 출고소요일 — 선주문(「그래도 등록」 뒤) 20일 · 평소 정본 7일. 등록과 같은 변환(to_collected → prepare_product)."""
    from tests.test_canary8_sku_price import _uploader
    from src.channel_sync._channel_bridge import to_collected
    up = _uploader(monkeypatch)
    base = {"title_ko": "버블 핑크 선풍기", "sell_price_krw": 30000, "images": ["https://img.alicdn.com/a.jpg"]}
    for days, want in ((20, 20), (0, 7)):
        prepared = up.prepare_product(to_collected(dict(base, lead_time_days=days)))
        assert prepared["lead_time_days"] == days
        items = up._build_product_payload(prepared)["items"]
        assert items and all(it["outboundShippingTimeDay"] == want for it in items)


# ── 4·5. 표시 반각 · WC 기본 해제 ─────────────────────────────────────────────────────────────

def test_4_card_text_is_halfwidth_but_storage_is_not():
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import PrevalidationResult
    r = PrevalidationResult(market="coupang", ok=False, hold=True, message="옵션 값 「泡泡粉（2-3周发货）」",
                            details=["원문 「黑色\x04\x042-3周发货」"])
    r.cautions = ["선주문 — 「（预售）」"]
    d = V._pv_dict(r)
    assert d["message"] == "옵션 값 「泡泡粉(2-3周发货)」" and d["details"] == ["원문 「黑色 · 2-3周发货」"]   # 0x04(폰 □) → 「 · 」
    assert d["cautions"] == ["선주문 — 「(预售)」"]


def test_5_shared_bundle_does_not_auto_check_wc(monkeypatch):
    from src.seller_console import market_pick as MP
    monkeypatch.delenv("MARKET_NO_AUTO_CHECK", raising=False)
    monkeypatch.setattr(MP, "get_last", lambda sc: [])
    monkeypatch.setattr(MP, "get_default", lambda sc: ["coupang:woojoo", "smartstore:gocosmos", "elevenst", "woocommerce"])
    rows = [{"code": c, "connected": True} for c in ("coupang:woojoo", "smartstore:gocosmos", "elevenst", "woocommerce")]
    out = MP.apply_checks(rows, "shared", shared=True)
    assert out["codes"] == ["coupang:woojoo", "smartstore:gocosmos", "elevenst"]
    assert [r["code"] for r in rows if r["checked"]] == ["coupang:woojoo", "smartstore:gocosmos", "elevenst"]
    assert any(r["code"] == "woocommerce" for r in rows)                           # 줄은 그대로 — 손으로 고를 수 있다
    rows2 = [{"code": "woocommerce", "connected": True}]
    monkeypatch.setattr(MP, "get_default", lambda sc: ["woocommerce"])
    assert MP.apply_checks(rows2, "seller:x", shared=False)["codes"] == ["woocommerce"]   # 자기 키 셀러는 그대로


# ── 사전검증 끝까지(저장값 → 카드) ────────────────────────────────────────────────────────────

def test_end_to_end_prevalidate_splits_persists_and_holds(monkeypatch):
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import UploadDispatcher, PrevalidationResult
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_pv_auto_detail", lambda pd, data, results, force=False: (None, pd))
    seen = {}

    def fake_market(self, pd, market):
        h = UploadDispatcher.readiness_holds(pd, market)
        seen[market] = [x["fix"] for x in h]
        lt = [x for x in h if x["fix"] == "lead_time"]
        return PrevalidationResult(market=market, ok=not lt, hold=bool(lt), message=(lt[0]["short"] if lt else "통과"),
                                   details=[lt[0]["line"]] if lt else [], fixes=["lead_time"] if lt else [])
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market", fake_market)
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: UploadDispatcher())
    ex = {"title": "泡泡粉风扇", "title_ko": "버블 핑크 선풍기", "price": "39.9", "currency": "CNY",
          "images": ["https://img.alicdn.com/a.jpg"], "options": json.loads(json.dumps(OPTS)), "skus": json.loads(json.dumps(SKUS))}
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=1", seller_id="y7o", title="x", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y7o"
    from tests._pv_helper import prevalidate
    d = prevalidate(c, {"product": {"title": "버블 핑크 선풍기", "price": 39.9, "options": OPTS, "skus": SKUS},
                        "item_id": iid, "markets": ["elevenst"]})
    r = d["results"][0]
    assert r["hold"] and r["fixes"] == ["lead_time"] and "선주문 — 발송 2~3주" in r["cautions"]
    saved = json.loads(S.get(iid, seller_ids={"y7o"})["extra_json"])
    assert saved["options"][0]["values"] == ["泡泡粉", "黑色"]
    assert saved["options"][0]["lead_time"]["黑色"]["max_days"] == 21
    # 「선주문 그래도 등록」 → 보류 풀림
    assert c.post(f"/seller/collect/{iid}/lead-time-override").get_json()["ok"]
    d2 = prevalidate(c, {"product": {"title": "버블 핑크 선풍기", "price": 39.9}, "item_id": iid, "markets": ["elevenst"]})
    assert d2["results"][0]["ok"] and "선주문 — 발송 2~3주" in d2["results"][0]["cautions"]


def test_3_naver_delivery_fields_end_to_end():
    """네이버 — 등록과 같은 변환(to_collected → prepare_product → 몸통): 선주문 14일이면 주문 확인 후 제작 + FOURTEEN, 평소엔 칸 없음."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    from src.channel_sync._channel_bridge import to_collected
    up = N(account=None)
    for days, want in ((14, (True, "FOURTEEN")), (0, (None, None))):
        p = up.prepare_product(to_collected({"title_ko": "x", "sell_price_krw": 30000, "images": ["https://a/1.jpg"],
                                             "lead_time_days": days}))
        di = up._build_product_payload(p)["originProduct"]["deliveryInfo"]
        assert (di.get("customProductAfterOrderYn"), di.get("expectedDeliveryPeriodType")) == want
