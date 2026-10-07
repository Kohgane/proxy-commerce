"""Z6(오너 2026-10-08) — 배송비 엔진: 퍼센티 배대지 요율표(data/shipping/percenty_2026-10-08.json)를 **표 그대로**.

계약: 세 표 30행 재현 · 0.5 단위 올림(1.72→2.0) · 부피>실중량 · 대형화물 3분기(20kg/150cm/100cm) · 표 밖 외삽 estimated ·
LCL cbm 올림 · 부가서비스 하한(~) · 카드 세 줄·입력칸·해운/항공 토글 · 마진 계산기·설정 화면이 같은 엔진.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SEA = [(0.5, 4600), (1, 5200), (1.5, 5800), (2, 6400), (2.5, 7000), (3, 7600), (3.5, 8200), (4, 8800), (4.5, 9400), (5, 10000)]
AIR = [(0.5, 4700), (1, 6000), (1.5, 6900), (2, 7900), (2.5, 9000), (3, 10000), (3.5, 11100), (4, 12200), (4.5, 13300), (5, 14400)]
LCL = [(1, 94500), (1.5, 145000), (2, 173700), (2.5, 207700), (3, 241700), (3.5, 275600), (4, 309600), (4.5, 343600),
       (5, 377500), (5.5, 411500)]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("SHIPPING_VOL_DIVISOR", raising=False)
    monkeypatch.delenv("SHIPPING_RATE_KRW_PER_KG_CN", raising=False)
    from src.seller_console import shipping_ratio as SR
    monkeypatch.setattr(SR, "_fx", lambda c: 190.0 if c == "CNY" else None)
    from src.db import image_translate_queue_pg as st
    for k in ("ship_settings:shared", "ship_settings:z6", "ship_settings:default"):
        st.state_set(k, {})


def _modes():
    from src.seller_console import shipping_engine as E
    return E.table("percenty")["modes"]


def test_table_file_records_version_source_date():
    raw = json.loads(Path("data/shipping/percenty_2026-10-08.json").read_text(encoding="utf-8"))
    assert raw["version"] == "percenty_2026-10-08" and raw["captured_at"] == "2026-10-08" and "퍼센티" in raw["source"]
    assert set(raw["providers"]["percenty"]["modes"]) == {"sea", "air", "lcl"}


@pytest.mark.parametrize("mode, rows", [("sea", SEA), ("air", AIR), ("lcl", LCL)])
def test_three_tables_thirty_rows_exact(mode, rows):
    from src.seller_console import shipping_engine as E
    mt = _modes()[mode]
    assert [tuple(r) for r in mt["rows"]] == [(float(q) if isinstance(q, float) else q, k) for q, k in rows]
    for q, k in rows:
        assert E.price(mt, q) == {"qty": float(q), "krw": k, "estimated": False, "why": ""}


def test_half_kg_round_up():
    from src.seller_console import shipping_engine as E
    sea = _modes()["sea"]
    assert E.price(sea, 1.72)["qty"] == 2.0 and E.price(sea, 1.72)["krw"] == 6400 and not E.price(sea, 1.72)["estimated"]
    assert E.price(sea, 2.0)["qty"] == 2.0 and E.price(sea, 2.01)["qty"] == 2.5 and E.price(sea, 0.1)["qty"] == 0.5


def test_beyond_table_is_extrapolated_and_flagged():
    from src.seller_console import shipping_engine as E
    m = _modes()
    s6 = E.price(m["sea"], 6)
    assert s6 == {"qty": 6.0, "krw": 11200, "estimated": True, "why": s6["why"]} and "외삽" in s6["why"]   # +600/0.5kg
    a6 = E.price(m["air"], 6)
    assert a6["krw"] == 16600 and a6["estimated"]                                                           # +1,100/0.5kg
    assert E.price(m["sea"], 41)["krw"] == 10000 + 600 * 70 + 600 * 2                                      # 40kg 넘어도 같은 기울기
    assert E.price(m["air"], 41)["krw"] == 14400 + 1100 * 70 + 2500 * 2                                    # 40kg 이상 0.5kg당 2,500
    l6 = E.price(m["lcl"], 6)
    assert l6["krw"] == 445500 and l6["estimated"]                                                          # +34,000/0.5cbm
    small = E.price(m["lcl"], 0.36)
    assert small["qty"] == 1.0 and small["krw"] == 94500 and small["estimated"] and "표 최소" in small["why"]


def test_lcl_cbm_rounds_up_to_two_decimals():
    from src.seller_console import shipping_engine as E
    assert E.cbm([65, 48, 100]) == 0.32            # 0.312 → 0.32
    assert E.cbm([50, 50, 40]) == 0.1              # 딱 맞음
    assert E.cbm([101, 100, 100]) == 1.01
    assert E.cbm(None) == 0.0


def test_volume_weight_beats_actual():
    from src.seller_console import shipping_engine as E
    q = E.quote({"weight_kg": 1.0, "dims_cm": [40, 30, 20], "pkg_m3": 0}, mode="sea")   # 부피 24,000÷6000 = 4kg
    assert q["actual"]["krw"] == 5200 and q["volume"]["kg"] == 4.0 and q["volume"]["krw"] == 8800
    assert q["applied"]["krw"] == 8800 and q["applied"]["basis"] == "부피 무게"
    q = E.quote({"weight_kg": 6.0, "dims_cm": [40, 30, 20], "pkg_m3": 0}, mode="sea")
    assert q["applied"]["basis"] == "실제 무게" and q["applied"]["krw"] == 11200 and q["estimated"]


def test_divisor_env_and_setting(monkeypatch):
    from src.seller_console import shipping_engine as E
    assert E.divisor({}) == 6000.0
    monkeypatch.setenv("SHIPPING_VOL_DIVISOR", "5000")
    assert E.divisor({}) == 5000.0 and E.divisor({"vol_divisor": 8000}) == 8000.0


@pytest.mark.parametrize("title, why", [
    ("캠핑 박스 무게 20kg", "실중량 20kg ≥ 20kg"),
    ("수납장 50x50x50cm", "세 변 합 150cm ≥ 150cm"),
    ("스탠드 행거 100x20x10cm", "한 변 100cm ≥ 100cm"),
])
def test_bulky_three_branches(title, why):
    from src.seller_console import shipping_ratio as SR
    e = SR.estimate({"url": "https://item.taobao.com/item.htm?id=9", "title": title, "price": "300", "currency": "CNY"})
    assert e["code"] == "bulky_carrier" and why in e["line"] and e["line"].startswith("대형화물 — 국내 배송비 별도(경동택배 표준운임)")
    assert e["jeju_line"] == "제주·도서산간은 추가 운임이 붙어요."


@pytest.mark.parametrize("title", ["캠핑 박스 무게 19.9kg", "수납장 50x50x49cm", "스탠드 행거 99x20x10cm"])
def test_just_under_bulky_is_normal(title):
    from src.seller_console import shipping_ratio as SR
    e = SR.estimate({"url": "https://item.taobao.com/item.htm?id=9", "title": title, "price": "300", "currency": "CNY"})
    assert not e.get("code") and e["state"] == "ok"


def test_addons_min_krw_marks_at_least():
    from src.seller_console import shipping_engine as E
    prov = E.table("percenty")
    ad = E.addons_total(prov, ["precise_inspect", "polybag_aircap", "nope"])
    assert ad == {"krw": 4500, "at_least": True, "items": ["정밀검수 3,000원", "폴리백(에어캡) 1,500원~"]}


def _item(extra, seller="z6"):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "파우치", "price": "35", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"]}
    ex.update(extra)
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=9", seller_id=seller, title="파우치",
                    price="35", currency="CNY", extra=ex)


def _client(seller="z6"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def test_card_three_lines_toggle_and_input_route():
    iid = _item({"title_ko": "파우치(크기 모름)"})
    c = _client()
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-ship-input" open' in h and "부피 미확인" in h                       # 모르면 입력칸이 열려 있다
    assert c.post(f"/seller/collect/{iid}/ship-input", json={"weight_kg": "1.72", "l": "", "w": "", "h": ""}).get_json()["ok"]
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    lines = re.findall(r"<li>([^<]*)</li>", h.split('data-role="m5-ship-3lines"')[1].split("</ul>")[0])
    assert lines == ["실제 무게 비용: 1.72kg → 2kg 6,400원", "부피 무게 비용: 치수 모름", "적용 배송비: 6,400원(실제 무게 · 해운)"]
    assert c.post(f"/seller/collect/{iid}/ship-mode", json={"mode": "air"}).get_json()["ok"]
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert "적용 배송비: 7,900원(실제 무게 · 항공)" in h and 'is-on" data-mode="air"' in h
    assert c.post(f"/seller/collect/{iid}/ship-mode", json={"mode": "ship"}).status_code == 400
    assert c.post(f"/seller/collect/{iid}/ship-input", json={"weight_kg": "-1"}).status_code == 400
    assert _client("other").post(f"/seller/collect/{iid}/ship-mode", json={"mode": "sea"}).status_code == 404   # 남의 상품 0


def test_lcl_line_for_business_over_threshold():
    c = _client()
    c.post("/seller/settings/shipping", data={"provider": "percenty", "default_mode": "sea", "business": "1",
                                               "lcl_threshold_cbm": "0.1"})
    iid = _item({"title_ko": "수납함 60x50x30cm"})                                            # 0.09cbm · 세 변 합 140 → 대형 아님
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-ship-lcl"' not in h and 'data-role="m5-bulky"' not in h          # 0.09cbm < 0.1
    c.post("/seller/settings/shipping", data={"provider": "percenty", "default_mode": "sea", "business": "1",
                                               "lcl_threshold_cbm": "0.05"})
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert "LCL 견적 0.09cbm(청구 1cbm) → 94,500원 (표 밖 추정) — LCL: 관부가세·국내운송 별도" in h


def test_settings_page_shows_version_and_validates():
    c = _client()
    h = c.get("/seller/settings/shipping").get_data(as_text=True)
    # Z6 후속 갱신: 셀러 화면엔 캡처일만(버전 이름 percenty_… · 출처 문구는 관리자만) · 배대지 표시명 「기본 배대지」
    assert "요율표 2026-10-08 기준" in h and "폴리백(에어캡) — 1,500원~" in h and "해운 LCL(사업자 전용)" in h
    assert ">기본 배대지</option>" in h
    r = c.post("/seller/settings/shipping", data={"provider": "percenty", "default_mode": "sea", "vol_divisor": "50",
                                                   "lcl_threshold_cbm": "0.5"}).get_data(as_text=True)
    assert "부피 제수는 1000~10000 사이" in r


def test_margin_calculator_uses_engine():
    iid = _item({"title_ko": "파우치 무게 1.72kg"})
    h = _client().get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    assert "const _SHIP_EST_KRW = 6400;" in h and 'data-role="mc-ship-note">추정 배송비 6,400원' in h


def test_image_includes_rate_table():
    """빠지면 운영이 「요율 미설정」으로 떨어진다(지뢰 Render 배포누락)."""
    assert "COPY data/shipping/ ./data/shipping/" in Path("Dockerfile").read_text(encoding="utf-8")
    assert "!data/shipping/" in Path(".dockerignore").read_text(encoding="utf-8")


# ── Z6 후속(오너 2026-10-08): 배송비 숫자는 시스템에 하나 · 셀러 화면에 경쟁 서비스명 0 ─────────────────────────────
def test_card_margin_calculator_and_pricing_use_one_shipping_number():
    """같은 상품(무게 1.72kg · CNY)에 카드 · 마진 계산기 · 가격 계산기 세 곳의 배송비가 같은 값이어야 한다."""
    from src.pricing.calculator import calculate_listing_price
    iid = _item({"title_ko": "파우치 무게 1.72kg"})
    c = _client()
    card = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    card_krw = int(re.search(r"적용 배송비: ([\d,]+)원", card).group(1).replace(",", ""))
    margin = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    margin_krw = int(re.search(r"const _SHIP_EST_KRW = (\d+);", margin).group(1))
    price = calculate_listing_price(source_price=35, source_currency="CNY", weight_kg=1.72, market="coupang", category="기타",
                                    seller_id="z6")
    assert card_krw == margin_krw == int(price.shipping_krw) == 6400
    assert price.shipping_source == "engine" and price.shipping_estimated is False
    # 실제 등록 판매가(price.calc_sell_price)의 국제배송비도 같은 한 숫자(오너 2026-10-08 결정: 엔진으로 통일)
    from src.seller_console import collect_history_store as S
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = build_product(S.get(iid, seller_ids={"z6"}), seller_id="z6")
    assert UploadDispatcher._engine_shipping_fee(pd) == 6400


def test_registration_price_falls_back_only_when_size_unknown(monkeypatch):
    """무게·크기를 모르면 등록 판매가는 예전처럼 SHIPPING_FEE_DEFAULT(폴백) — 엔진이 지어내지 않는다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    seen = {}
    import src.price as P
    real = P.calc_sell_price
    monkeypatch.setattr(P, "calc_sell_price", lambda **kw: seen.update(kw) or real(**kw))
    base = {"url": "https://item.taobao.com/item.htm?id=9", "price": "35", "currency": "CNY", "target_margin_pct": 20}
    UploadDispatcher._landed_krw(dict(base, title="파우치"), "coupang")
    assert seen["shipping_fee"] is None                                   # 모름 → 폴백(price.py가 SHIPPING_FEE_DEFAULT)
    UploadDispatcher._landed_krw(dict(base, title="파우치 무게 1.72kg"), "coupang")
    assert seen["shipping_fee"] == 6400


def test_pricing_has_no_per_kg_path_left():
    """구조로 잰다(소스 문자열 핀 금지) — 가격 계산기는 엔진(ship_cost)을 부르고, kg당 키는 값으로도 안 쓴다."""
    from tests._ast_probe import calls_in, string_constants_in
    from src.pricing.calculator import calculate_listing_price
    assert "_ship_cost" in calls_in(calculate_listing_price)
    assert not any("per_kg" in s for s in string_constants_in(calculate_listing_price))
    from src.pricing.policy import default_policy
    assert "intl_ship_per_kg_krw" not in default_policy()["shipping"]


def test_seller_screens_never_show_competitor_name():
    """「퍼센티」 금지 가드와 같은 이유(경쟁 서비스명) — 렌더된 셀러 화면에 퍼센티·percenty 0. 관리자만 출처를 본다."""
    iid = _item({"title_ko": "파우치 무게 1.72kg"})
    c = _client()
    pages = [c.get(f"/seller/m/item/{iid}").get_data(as_text=True), c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True),
             c.get("/seller/settings/shipping").get_data(as_text=True)]
    for h in pages:
        # 화면에 보이는 글자 기준(provider 키 percenty는 폼 값으로만 남는다 — 오너 결정: 키는 그대로)
        visible = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", h, flags=re.S)
        assert "퍼센티" not in visible and "percenty" not in visible.lower()
    assert "기본 배대지 해운" in pages[0]
    from src.order_webhook import app
    a = app.test_client()
    with a.session_transaction() as s:
        s.update(user_id="z6-admin", user_role="admin")
    assert "percenty_2026-10-08" in a.get("/seller/settings/shipping").get_data(as_text=True)
