"""F51-b — 옵션 값 규칙 변경(오너 2026-09-27): 「색상은 용어집만」(F48-b) 폐기.

해석 순서(한 곳 — `coupang_options.resolve_option_value`):
  0) 오너가 이 상품에서 고친 값 → 1) 용어집 정확 일치 → 2) 용어집 조각 치환(白色→화이트, 带理线器→선정리형)
  → 3) 번역기 `values_ko`(브랜드·영문 토큰 보존) → 4) 그래도 비면 보류.
2)·3)은 옵션 블록에 「번역기 값 — 확인」 배지 + 고칠 칸. 고친 값은 용어집 **후보**로만(자동 반영 0).
SKU끼리 같아지면 원문 차이를 붙여 가르고(「블랙」 vs 「블랙 선정리형」), 그래도 같으면 보류.
SKU별 판매가에 쓴 환율(값·출처·갱신)을 옵션 블록 표에.

★ 수행방패 정본 10줄은 F51-b-2(오너 09-27)로 들어왔다 — 여기 `STAND_IN`은 「10줄이 들어오면」 메커니즘만 재는
  테스트 전용 대체값이고, 실제 정본 통과는 `test_f51b2_canon_names_model`이 잰다.
"""
from __future__ import annotations

import pytest

from src.uploaders import coupang_options as O
from tests.test_f51_coupang_multi_sku import FAKE_KO, META, _product, _skus

pytestmark = pytest.mark.coupang_precheck


def _with_ko(p, table=FAKE_KO):
    """번역기(translate_options)가 남기는 모양 그대로 — options[].values_ko."""
    for o in p["options"]:
        o["values_ko"] = [table.get(v, v) for v in o["values"]]
    return p


# ── 해석 순서 ──────────────────────────────────────────────────────────────────

def test_resolution_order():
    r = O.resolve_option_value
    assert r("黑色", values_ko="검정")["how"] == "glossary" and r("黑色")["value"] == "블랙"
    assert r("黑色", override="먹색")["value"] == "먹색"                                  # 0) 오너 수정이 먼저
    t = r("黑色带理线器")
    assert (t["value"], t["how"], t["confirm"]) == ("블랙 선정리형", "token", True)            # 2) 조각 치환
    tr = r("双位纸巾架【卷纸丨湿厕纸丨抽纸】", values_ko="2단 휴지걸이(롤·물티슈·각티슈)")
    assert tr["how"] == "translator" and tr["confirm"] is True                               # 3) 번역기
    # T1(2026-10-02): 「PD20W快充（白色款）」은 이제 정리 규칙만으로 풀린다(快充→고속충전) — 번역기 경로를 재려고
    #   규칙표에 없는 말(莫奈色)을 섞었다. 재는 것은 그대로: 번역기 값이 원문의 영문·숫자(PD20W)를 잃으면 보류.
    assert r("PD20W快充（白色款）")["value"].startswith("PD20W 고속충전")
    lost = r("PD20W莫奈色款", values_ko="모네 컬러")
    assert lost["value"] == "" and "PD20W" in lost["why"]                                     # 영문 토큰 보존
    # (T1 2026-09-30-H: 紫色 같은 기본 색은 이제 정리 규칙이 옮긴다 — 표에 없는 말로 보류를 잰다)
    assert r("莫奈色", values_ko="모네 컬러")["value"] == "모네 컬러"
    assert r("莫奈色")["value"] == "" and "직접 넣어" in r("莫奈色")["why"]                   # 4) 보류
    assert r("莫奈色", values_ko="莫奈色")["value"] == ""                                     # 원문 그대로 = 번역 안 됨
    assert (r("紫色")["value"], r("紫色")["how"]) == ("퍼플", "polish")                       # 정리 규칙(원격 표)


def test_owner_canon_lines_and_tokens_are_the_owner_list():
    """F51-b-2(오너 2026-09-27): 수행방패 정본 10줄 + 조각 치환 토큰 — 오너가 준 그대로."""
    from src.services.image_text_glossary import OPTION_VALUE_LINES, OPTION_VALUE_TOKENS
    assert len(OPTION_VALUE_LINES) == 10 and OPTION_VALUE_LINES["【三合一充电支架】带理线器（红色）"] == "레드 선정리형"
    owner_f51b = {"白色": "화이트", "黑色": "블랙", "粉色": "핑크", "蓝色": "블루", "红色": "레드",
                  "带理线器": "선정리형", "三合一": "3in1"}
    assert all(OPTION_VALUE_TOKENS[k] == v for k, v in owner_f51b.items())
    # Y6-C A3(오너 2026-10-07): 같은 표에 색명(외래어 표기 통일)·의류 낱말 추가 — 오너가 준 줄 그대로.
    y6c = {"宝蓝": "로열 블루", "藏蓝": "네이비", "苔藓绿": "모스 그린", "军绿": "카키 그린", "米白": "아이보리",
           "杏色": "베이지", "卡其": "카키", "酒红": "와인", "上衣": "상의", "半裙": "스커트", "连衣裙": "원피스",
           "套装": "세트", "均码": "프리사이즈"}
    assert all(OPTION_VALUE_TOKENS[k] == v for k, v in y6c.items())
    assert set(OPTION_VALUE_TOKENS) <= set(owner_f51b) | set(y6c) | {"半身裙"}


def test_without_the_lines_translator_values_pass_with_a_badge(monkeypatch):
    from src.services import image_text_glossary as G
    monkeypatch.setattr(G, "OPTION_VALUE_LINES", {})
    plan = O.plan_for(META["attributes"], _with_ko(_product(_skus())))
    assert plan["multi"] and plan["holds"] == [] and len(plan["items"]) == 10
    assert all(i["confirm"] for i in plan["items"])
    assert {i["label"] for i in plan["items"]} == set(FAKE_KO.values())


def test_without_any_korean_the_shield_is_still_held(monkeypatch):
    from src.services import image_text_glossary as G
    monkeypatch.setattr(G, "OPTION_VALUE_LINES", {})
    plan = O.plan_for(META["attributes"], _product(_skus()))
    assert any(h.startswith("옵션 값 10개를 한국어로 옮기지 못했습니다") for h in plan["holds"])


def test_owner_override_wins_and_is_not_a_badge():
    p = _with_ko(_product(_skus()))
    first = p["options"][0]["values"][0]
    p["option_value_overrides"] = {first: "오너 값"}
    plan = O.plan_for(META["attributes"], p)
    it = next(i for i in plan["items"] if i["spec"] == [first])
    assert it["label"] == "오너 값" and not it["confirm"]


# ── 같아지는 값 ────────────────────────────────────────────────────────────────

def _two(values, ko):
    p = _product(_skus())
    sk = p["skus"][:len(values)]
    for k, v in zip(sk, values):
        k["spec"] = [v]
    p["skus"] = sk
    p["options"] = [{"name": "颜色分类", "values": values, "values_ko": [ko[v] for v in values]}]
    return p


def test_equal_translations_get_the_original_difference_appended():
    p = _two(["款甲黑色", "款甲黑色带理线器"], {"款甲黑色": "블랙", "款甲黑色带理线器": "블랙"})
    plan = O.plan_for(META["attributes"], p)
    assert plan["holds"] == [], plan["holds"]
    assert sorted(i["label"] for i in plan["items"]) == ["블랙", "블랙 선정리형"]


def test_equal_translations_that_cannot_be_split_are_held():
    p = _two(["款甲黑色", "款乙黑色"], {"款甲黑色": "블랙", "款乙黑色": "블랙"})
    plan = O.plan_for(META["attributes"], p)
    assert any("옵션 값이 같아집니다" in h for h in plan["holds"])


# ── 1064346880857(双位纸巾架 등) ─────────────────────────────────────────────────

def test_tissue_holder_values_pass_through_the_translator_with_a_badge():
    ko = {"双位纸巾架【卷纸丨湿厕纸丨抽纸】": "2단 휴지걸이(롤·물티슈·각티슈)",
          "纸巾架-抽屉款【可收纳卫生巾】": "휴지걸이 서랍형(생리대 수납)"}
    for v, k in ko.items():
        r = O.resolve_option_value(v, values_ko=k)
        assert r["value"] == k and r["how"] == "translator" and r["confirm"]
    # U4(오너 2026-10-02): 「售后品质保障丨购买无忧」는 옵션이 아니라 보증 문구 — 번역기 값이 있어도 「옵션 아님 — 제외」.
    r = O.resolve_option_value("售后品质保障丨购买无忧", values_ko="품질 보증")
    assert r["value"] == "" and r["how"] == "non_option" and "옵션 아님" in r["why"]


# ── 오너 수정 → 후보(자동 반영 0) ────────────────────────────────────────────────

def test_fixing_a_value_stores_an_override_and_only_a_candidate(monkeypatch):
    import json
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.services import image_text_glossary as G
    seller = "u-f51b-fix"
    iid = S.append(url="https://detail.tmall.com/item.htm?id=617129397971", title="t", price="29.90",
                   currency="CNY", source="extension", seller_id=seller, extra={"options": []})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    r = c.post(f"/seller/collect/preview/{iid}/option-value",
               json={"orig": "四合一支架（紫色）", "value": "4in1 거치대 퍼플"}).get_json()
    assert r["ok"] and r["overrides"] == {"四合一支架（紫色）": "4in1 거치대 퍼플"}
    ex = json.loads(S.get(iid, seller_id=seller)["extra_json"])
    assert ex["option_value_overrides"]["四合一支架（紫色）"] == "4in1 거치대 퍼플"
    cands = c.get("/seller/listing/glossary-candidates").get_json()
    assert any(x["orig"] == "四合一支架（紫色）" and not x["in_glossary"] for x in cands["candidates"])
    assert "四合一支架（紫色）" not in G.OPTION_VALUE_LINES                            # 자동 반영 0


def test_overrides_and_translator_values_reach_the_uploader():
    from src.channel_sync._channel_bridge import to_collected
    from src.uploaders.coupang_uploader import CoupangUploader
    pd = {**_product(_skus()), "option_values_ko": FAKE_KO, "option_value_overrides": {"x": "y"}}
    prepared = CoupangUploader(access_key="a", secret_key="b", vendor_id="v").prepare_product(to_collected(pd))
    assert prepared["_values_ko"] == FAKE_KO and prepared["option_value_overrides"] == {"x": "y"}
    assert O.value_ko_map(prepared)["三合一充电支架（白色）"] == "3-in-1 충전 거치대 화이트"


# ── 환율 ──────────────────────────────────────────────────────────────────────

def test_sku_prices_carry_the_fx_used(monkeypatch):
    from src.channel_sync.coupang_uploader import with_sku_prices
    monkeypatch.setenv("FX_USE_LIVE", "0")
    monkeypatch.delenv("FX_CNYKRW", raising=False)
    pd = with_sku_prices({**_product(_skus(price_fn=None))})
    [fx] = pd["fx_info"]
    assert fx["currency"] == "CNY" and fx["rate"] == 185.0 and fx["source"] == "default"
    assert fx["label"] == "앱 기본값(고정)" and fx["updated_at"] == ""


_NOW_ISO = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()


def test_live_rate_is_used_when_the_fx_api_answers(monkeypatch):
    """프로덕션(FX_USE_LIVE 미설정) — 드로어와 **같은** 실시간 환율로 판매가를 낸다."""
    from src.channel_sync.coupang_uploader import with_sku_prices
    from src.seller_console import data_aggregator as DA
    monkeypatch.delenv("FX_USE_LIVE", raising=False)
    monkeypatch.setattr(DA, "get_fx_rates", lambda: {"USD": 1390.0, "JPY": 9.3, "EUR": 1500.0, "CNY": 195.5,
                                                     "is_mock": False, "source": "frankfurter",
                                                     # Z9: 묵은 갱신은 「n시간 전 환율」 — 여긴 방금 받은 실시간
                                                     "updated_at": _NOW_ISO})
    live = with_sku_prices({**_product(_skus(price_fn=None))})
    monkeypatch.setenv("FX_USE_LIVE", "0")
    fixed = with_sku_prices({**_product(_skus(price_fn=None))})
    assert live["fx_info"][0]["source"] == "live" and live["fx_info"][0]["rate"] == 195.5
    assert live["fx_info"][0]["label"] == "실시간 환율" and live["fx_info"][0]["updated_at"] == _NOW_ISO
    a = live["skus"][0]["sell_price_krw"]
    b = fixed["skus"][0]["sell_price_krw"]
    assert a > b > 0                                                        # 195.5원 > 185원 — 환율이 실제로 들어갔다


def test_option_block_renders_badges_fix_fields_and_fx():
    html = open("src/seller_console/templates/collect_preview.html", encoding="utf-8").read()
    assert "function kgpCpConfirm" in html and "번역기 값 — 확인" in html and "data-cp-fix" in html
    assert "function kgpCpFx" in html and 'data-role="cp-fx"' in html and "갱신 없음(고정값)" in html
    assert "option_values_ko: kgpValuesKoMap()" in html
