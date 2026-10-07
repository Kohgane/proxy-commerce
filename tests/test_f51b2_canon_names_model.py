"""F51-b-2 · F51-b-3 · F48-d (오너 통합 브리프 2026-09-27).

  F51-b-2 수행방패 정본 10줄(용어집 옵션 값 섹션) → 10 SKU 전부 「용어집」, itemName = 정본, 사전검증 미번역 사유 0.
  F51-b-3 옵션 **이름**도 오너 수정 → 용어집(商品规格→규격 …) → 번역기 → 보류. 메타에 없으면 보류 + 메타 속성명 목록.
          회귀: 1064346880857 双位纸巾架 — 「규격」 축으로 통과하거나 목록 붙은 보류.
  F48-d  쿠팡 필수 옵션 블록 자동 로드 · 적용모델은 제목 모델 토큰으로 선채움(「제목에서 추출 — 확인」).
"""
from __future__ import annotations

import pytest

from src.uploaders import coupang_options as O
from tests.test_f49t2_tmall_ice_sku import res_of
from tests.test_f51_coupang_multi_sku import META, SHIP, _product, _skus

pytestmark = pytest.mark.coupang_precheck

CANON = ["화이트", "블랙", "핑크", "블루", "레드",
         "블랙 선정리형", "화이트 선정리형", "블루 선정리형", "핑크 선정리형", "레드 선정리형"]
META_MODEL = {"attributes": META["attributes"] + [
    {"attributeTypeName": "적용모델", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED",
     "groupNumber": "NONE"}]}
F_1064 = "tests/fixtures/realpages/tmall_1064346880857_ice_min.html"


# ── F51-b-2 정본 10줄 ─────────────────────────────────────────────────────────

def test_shield_ten_skus_use_the_canon_with_glossary_badges():
    plan = O.plan_for(META["attributes"], _product(_skus()))
    assert plan["multi"] and plan["holds"] == [] and len(plan["items"]) == 10
    assert sorted(i["label"] for i in plan["items"]) == sorted(CANON)
    for it in plan["items"]:
        assert not it["confirm"]
        assert [r["how"] for r in it["resolved"]] == ["glossary"]            # 전부 「용어집」


def test_item_names_are_the_canon():
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader(access_key="a", secret_key="b", vendor_id="v")
    p = _product(_skus())
    plan = O.plan_for(META["attributes"], p)
    names = sorted(up._sku_item({}, it, p)["itemName"] for it in plan["items"])
    assert names == sorted(CANON)


@pytest.fixture
def wired_real(monkeypatch):
    """F51 `wired`와 같은 실경로 — 단 용어집 **목 없음**(실제 정본 10줄로 돈다)."""
    for k, v in SHIP.items():
        monkeypatch.setenv(k, v)
    from src.uploaders.coupang_uploader import CoupangUploader
    from src.seller_console.upload_dispatcher import UploadDispatcher
    meta = {"attributes": META_MODEL["attributes"], "noticeCategories": [], "requiredDocumentNames": []}

    def _api(self, method, path, data=None):
        if "categorization/predict" in path:
            return {"data": {"predictedCategoryId": "63955"}}
        if "category-related-metas" in path:
            return {"data": meta}
        if "shipping-place/outbound" in path:
            return {"data": [{"outboundShippingPlaceCode": "25099966", "addressType": "OVERSEA"}]}
        return {"code": "SUCCESS", "data": None}

    monkeypatch.setattr(CoupangUploader, "_api_request", _api)
    monkeypatch.setattr(UploadDispatcher, "_landed_krw",
                        staticmethod(lambda pd, m="": (float(pd["price_original"]) * 250, "")))
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_api_state",
                        lambda: {"missing": [], "account": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_shipping_state",
                        lambda acct: {"missing": [], "source": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.resolve_upload_account", lambda: "")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: __import__("contextlib").nullcontext())


def test_prevalidate_has_no_untranslated_or_required_option_reason(wired_real):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-f51b2-pre"; s["user_role"] = "admin"   # Z6: 서버 env 키(오너 자격)는 공유 사용자만
    r = c.post("/seller/collect/prevalidate", json={"product": _product(_skus(price_fn=None)),
                                                   "markets": ["coupang"]}).get_json()["results"][0]
    assert r["ok"] is True, r
    text = str(r)
    assert "SKU별 등록 10개" in r["hint"]
    assert "옮기지 못했습니다" not in text and "미해석" not in text and "필수 옵션" not in text


# ── F51-b-3 옵션 이름 ────────────────────────────────────────────────────────

def test_name_resolution_order():
    r = O.resolve_option_name
    assert r("颜色分类", ["색상"])["how"] == "glossary"
    assert r("商品规格", ["규격", "수량"])["meta"] == "규격"
    assert r("尺码", ["사이즈"])["meta"] == "사이즈" and r("款式", ["종류"])["meta"] == "종류"
    assert r("型号", ["모델"], name_ko="모델")["how"] == "translator"
    assert r("商品规格", ["색상"], override="색상")["how"] == "override"
    held = r("商品规格", ["색상", "수량"])
    assert held["meta"] == "" and held["candidate"] == "규격" and "메타 속성 중에서 골라" in held["why"]


def _tissue(meta_names_has_gyu: bool):
    res = res_of(F_1064)
    vals = {v["vid"]: v for v in res["skuBase"]["props"][0]["values"]}
    info = res["skuCore"]["sku2info"]
    skus = []
    for s in res["skuBase"]["skus"]:
        v = vals[s["propPath"].split(":")[1]]
        cost = int(info[s["skuId"]]["price"]["priceMoney"]) / 100
        skus.append({"spec": [v["name"]], "sku_id": s["skuId"], "price": f"{cost:.2f}", "currency": "CNY",
                     "stock": info[s["skuId"]]["quantity"], "image": v.get("image") or "",
                     "sell_price_krw": int(cost * 200)})
    names = [v["name"] for v in res["skuBase"]["props"][0]["values"]]
    ko = {names[0]: "2단 휴지걸이(롤·물티슈·각티슈)", names[1]: "휴지걸이 서랍형(생리대 수납)", names[2]: "품질 보증"}
    p = {"title": res["item"]["title"], "price": 175.5, "currency": "CNY", "sku": "1064346880857",
         "options": [{"name": "商品规格", "values": names, "values_ko": [ko[n] for n in names]}], "skus": skus}
    meta = [{"attributeTypeName": ("규격" if meta_names_has_gyu else "색상"), "required": "MANDATORY",
             "dataType": "STRING", "exposed": "EXPOSED", "groupNumber": "NONE"},
            {"attributeTypeName": "수량", "required": "MANDATORY", "dataType": "NUMBER", "basicUnit": "개",
             "usableUnits": ["개"], "exposed": "EXPOSED", "groupNumber": "NONE"}]
    return p, meta


def test_tissue_holder_passes_on_the_gyu_axis():
    p, meta = _tissue(True)
    plan = O.plan_for(meta, p)
    assert plan["multi"] and plan["holds"] == [], plan["holds"]
    assert {a["attributeTypeName"] for it in plan["items"] for a in it["attributes"]} >= {"규격"}
    # 3번째 SKU(售后品质保障丨购买无忧)는 U4(오너 2026-10-02)부터 재고와 무관하게 「옵션 아님 — 제외」
    assert len(plan["items"]) == 2 and any("옵션 아님 — 제외" in n and "售后" in n for n in plan["notes"])
    assert all(it["confirm"] for it in plan["items"])                                # 번역기 값 — 확인


def test_tissue_holder_without_gyu_is_held_with_the_meta_list_then_owner_pick_passes():
    p, meta = _tissue(False)
    plan = O.plan_for(meta, p)
    assert any(h.startswith("옵션 「商品规格」(→규격)") for h in plan["holds"])
    assert plan["name_picks"] == [{"orig": "商品规格", "candidate": "규격", "choices": ["색상", "수량"]}]
    p["option_name_overrides"] = {"商品规格": "색상"}
    assert O.plan_for(meta, p)["holds"] == []


def test_name_pick_route_stores_override(monkeypatch):
    import json
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "u-f51b3-name"
    iid = S.append(url="https://detail.tmall.com/item.htm?id=1064346880857", title="t", price="175.5",
                   currency="CNY", source="extension", seller_id=seller, extra={"options": []})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    r = c.post(f"/seller/collect/preview/{iid}/option-name", json={"orig": "商品规格", "name": "색상"}).get_json()
    assert r["ok"] and r["overrides"] == {"商品规格": "색상"}
    ex = json.loads(S.get(iid, seller_id=seller)["extra_json"])
    assert ex["option_name_overrides"] == {"商品规格": "색상"}


def test_name_overrides_reach_the_uploader():
    from src.channel_sync._channel_bridge import to_collected
    from src.uploaders.coupang_uploader import CoupangUploader
    pd = {**_product(_skus()), "option_names_ko": {"商品规格": "규격"}, "option_name_overrides": {"a": "b"}}
    prepared = CoupangUploader(access_key="a", secret_key="b", vendor_id="v").prepare_product(to_collected(pd))
    assert prepared["_names_ko"] == {"商品规格": "규격"} and prepared["option_name_overrides"] == {"a": "b"}


# ── F48-d 적용모델 선채움 · 자동 로드 ─────────────────────────────────────────

def test_model_tokens_from_the_title():
    t = _product(_skus())["title"]
    assert O.model_tokens(t) == ["applewatch7/9", "S8", "Ultra2"]
    assert O.model_tokens("SPORTLINK iwatch Airpods") == []                       # 숫자 없는 영단어는 아님


def test_apply_model_is_prefilled_with_a_badge_source_and_sent():
    p = _product(_skus())
    form = O.option_form(META_MODEL["attributes"], p)
    f = next(x for x in form["fields"] if x["name"] == "적용모델")
    assert f["value"] == "applewatch7/9, S8, Ultra2" and f["source"] == "제목에서 추출"
    assert not any("필수 옵션" in h for h in form["holds"]), form["holds"]
    sent = O.plan_for(META_MODEL["attributes"], p)["items"][0]["attributes"]
    assert {"attributeTypeName": "적용모델", "attributeValueName": "applewatch7/9, S8, Ultra2"} in \
        [{k: a[k] for k in ("attributeTypeName", "attributeValueName")} for a in sent]


def test_no_model_token_means_still_held():
    p = {**_product(_skus()), "title": "随行盾 手表架"}
    plan = O.plan_for(META_MODEL["attributes"], p)
    assert any("필수 옵션: 적용모델" in h for h in plan["holds"])                     # 빈 값 전송 금지 그대로


def test_option_block_auto_loads_and_renders_badges():
    html = open("src/seller_console/templates/collect_preview.html", encoding="utf-8").read()
    i = html.index("F48-d — 쿠팡 필수 옵션은 **자동으로** 불러온다")
    auto = html[i:i + 700]
    assert "DOMContentLoaded" in auto and "kgpLoadCoupangOptions();" in auto and "editCategory" in auto
    assert '<i class="bi bi-arrow-repeat"></i> 다시 불러오기</button>' in html
    assert '> 쿠팡 기준 불러오기</button>' not in html
    assert 'data-role="cp-error"' in html and "원문 보기</summary>" in html and "kgpCpFail(body" in html
    assert 'data-role="cp-model">제목에서 추출 — 확인' in html
    assert 'data-role="cp-name-pick"' in html and "data-cp-name" in html
    assert 'data-role="cp-glossary"' in html
    j = html.index("갱신됐어요 · ")
    # Y1(2026-10-04): 재수집 뒤엔 페이지를 통째로 다시 그린다(location.reload) — DOMContentLoaded 자동 불러오기
    #   (위 `auto` 단언)가 쿠팡 옵션을 다시 부른다. 예전 제자리 호출은 헤더·배너를 옛 값으로 남겼다.
    assert "location.reload()" in html[j:j + 600]


def test_model_prefill_survives_the_50_char_title_cut():
    """실경로(브리지 → prepare_product)에선 쿠팡 제목이 50자로 잘린다 — 모델 토큰은 **원제목**에서 뽑아야 한다
    (캡처에서 발견: 잘린 제목으로 뽑아 `Ultra2`가 빠졌다)."""
    from src.channel_sync._channel_bridge import to_collected
    from src.channel_sync.coupang_uploader import prepared_input
    from src.uploaders.coupang_uploader import CoupangUploader
    prepared = CoupangUploader(access_key="a", secret_key="b", vendor_id="v").prepare_product(
        to_collected(prepared_input(_product(_skus()))))
    assert "Ultra2" not in prepared["title"] and "Ultra2" in prepared["title_original"]
    f = next(x for x in O.option_form(META_MODEL["attributes"], prepared)["fields"] if x["name"] == "적용모델")
    assert f["value"] == "applewatch7/9, S8, Ultra2"


# ── 환율 표기 정직성(같은 유형 결함 — 이번 캡처에서 발견) ─────────────────────────

def test_fx_env_fallback_is_not_called_live(monkeypatch):
    """FXProvider는 API가 다 실패하면 `env` 폴백(고정값)을 fetched_at=지금으로 준다. 옛 코드는 그걸
    드로어엔 「실시간」, 옵션 블록엔 「실시간 환율 · 방금」이라 적었다(before 캡처: CNY 190 「실시간 환율」)."""
    from decimal import Decimal
    from src.seller_console import data_aggregator as DA
    import src.fx.provider as FP
    monkeypatch.setattr(FP.FXProvider, "get_rates", lambda self: {
        "USDKRW": Decimal("1350"), "JPYKRW": Decimal("9"), "EURKRW": Decimal("1470"), "CNYKRW": Decimal("190"),
        "fetched_at": "2026-09-27T11:00:00+00:00", "provider": "env"})
    monkeypatch.setattr(DA, "_FX_DISABLE_NETWORK", False, raising=False)
    DA._FX_CACHE.clear()
    d = DA._compute_fx_rates()
    assert d["is_mock"] is True and d["source"] == "env" and d["updated_at"] == ""
    monkeypatch.delenv("FX_USE_LIVE", raising=False)
    monkeypatch.setattr(DA, "get_fx_rates", lambda: {**d, "is_mock": False})       # 옛 표기를 흉내 내도
    from src.price import sell_fx_rates
    assert sell_fx_rates()[1]["CNY"]["source"] != "live"                            # env는 실시간이 아니다
    DA._FX_CACHE.clear()


def test_fx_real_api_is_live(monkeypatch):
    from src.seller_console import data_aggregator as DA
    from src.price import sell_fx_rates
    monkeypatch.delenv("FX_USE_LIVE", raising=False)
    monkeypatch.setattr(DA, "get_fx_rates", lambda: {"USD": 1390.0, "JPY": 9.3, "EUR": 1500.0, "CNY": 195.5,
                                                     "is_mock": False, "source": "frankfurter",
                                                     "updated_at": "2026-09-27T03:00:00+00:00"})
    info = sell_fx_rates()[1]["CNY"]
    assert info["source"] == "live" and info["label"] == "실시간 환율" and info["rate"] == 195.5
