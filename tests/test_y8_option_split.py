"""Y8(오너 2026-10-04 20:44 실측, 티몰 JOYE 멀티탭) — 광고문형 옵션 값 분해 · SKU 1:1 · 30자 · 중국 표준 콘센트 소싱 제외.

값 12개는 오너가 보고한 모양(「✅弹簧线ꙮPD65W快充✅双层粘夹白色【7五孔+1A1C】⭐升降桌专用款⭐」)을 따라 **재구성한 표본**이다
(실제 12개 원문은 운영 데이터에 있음 — 배포 뒤 그 상품으로 다시 잰다).
"""
from __future__ import annotations

import json

VALUES = [
    "✅弹簧线ꙮPD65W快充✅双层粘夹白色【7五孔+1A1C】⭐升降桌专用款⭐",
    "✅弹簧线ꙮPD65W快充✅双层粘夹曜石黑【7五孔+1A1C】⭐升降桌专用款⭐",
    "✅PD65W快充✅白色【7五孔+1A1C】1.8米⭐新品⭐",
    "✅PD65W快充✅曜石黑【7五孔+1A1C】1.8米⭐新品⭐",
    "✅弹簧线ꙮPD20W快充✅白色【5五孔+2A1C】⭐升降桌专用款⭐",
    "✅弹簧线ꙮPD20W快充✅曜石黑【5五孔+2A1C】⭐升降桌专用款⭐",
    "✅PD20W快充✅白色【5五孔+2A1C+抽拉线】1.8米",
    "✅PD20W快充✅曜石黑【5五孔+2A1C+抽拉线】1.8米",
    "✅15W✅白色【4五孔+1A2C】1.8米⭐新品⭐",
    "✅15W✅黑色【4五孔+1A2C】1.8米⭐新品⭐",
    "✅弹簧线ꙮ15W✅白色【4五孔+1A2C】⭐升降桌专用款⭐",
    "✅弹簧线ꙮ15W✅黑色【4五孔+1A2C】⭐升降桌专用款⭐",
]
PRICES = ["139", "139", "119", "119", "99", "99", "109", "109", "79", "79", "89", "89"]


def _extra():
    return {"title": "JOYE 桌面插座", "title_ko": "JOYE 데스크 멀티탭", "price": "79", "currency": "CNY",
            "images": ["https://img.alicdn.com/a.jpg"],
            "options": [{"name": "颜色", "values": list(VALUES)}],
            "skus": [{"spec": [v], "price": p, "stock": 10 + i} for i, (v, p) in enumerate(zip(VALUES, PRICES))]}


def test_clean_drops_symbols_brackets_and_ad_tails():
    from src.collectors.option_split import clean
    assert clean(VALUES[0]) == "弹簧线 PD65W快充 双层粘夹白色 7五孔+1A1C"


def test_twelve_values_split_into_axes_one_to_one():
    from src.collectors.option_split import apply
    ex = _extra()
    rec = apply(ex)
    assert rec["state"] == "split" and 4 <= len(rec["axes"]) <= 5, rec
    assert rec["axes"] == ["색상", "구성", "출력", "케이블", "길이"]
    vals = [v for o in ex["options"] for v in o["values"]]
    assert all(len(v) <= 30 for v in vals)
    assert {o["name"]: o["values"] for o in ex["options"]}["구성"] == ["7구+1A1C", "5구+2A1C", "5구+2A1C+인출선", "4구+1A2C"]
    assert ex["skus"][0]["spec"] == ["화이트", "7구+1A1C", "PD65W", "스프링", "기본"]
    assert ex["skus"][3]["spec"] == ["오닉스 블랙", "7구+1A1C", "PD65W", "일반", "1.8m"]
    assert len(ex["skus"]) == 12 and len({tuple(k["spec"]) for k in ex["skus"]}) == 12
    assert [k["price"] for k in ex["skus"]] == PRICES and [k["stock"] for k in ex["skus"]] == list(range(10, 22))
    assert ex["options_src"][0]["values"] == VALUES                       # 원본 보존
    assert apply(ex) is None                                              # 한 번만


def test_not_one_to_one_is_left_as_is_with_reason():
    from src.collectors.option_split import apply
    ex = _extra()
    ex["options"][0]["values"] = VALUES[:2] + ["✅弹簧线ꙮPD65W快充✅双层粘夹白色【7五孔+1A1C】⭐新品⭐"]   # 1번과 같은 조합
    ex["skus"] = [{"spec": [v], "price": "1"} for v in ex["options"][0]["values"]]
    rec = apply(ex)
    assert rec["state"] == "none" and "1:1" in rec["why"] and ex["options"][0]["values"][0] == VALUES[0]


def test_compact_fallback_color_config_power():
    from src.collectors.option_split import split_values
    r = split_values(["✅白色【7五孔+1A1C】PD65W⭐升降桌专用款⭐", "✅白色【5五孔+2A1C】PD20W⭐新品⭐"])
    assert r["state"] == "split"                                        # 축 2개(구성·출력)면 분해
    r = split_values(["✅白色加厚款PD65W【7五孔+1A1C】超长款式说明文字测试", "✅黑色加厚款PD65W【7五孔+1A1C】超长款式说明文字测试"])
    assert r["state"] == "compact"                                      # 다른 축은 색상 하나뿐 → 색상·구성·출력 한 값
    assert r["axes"] == [("옵션", ["화이트 · 7구+1A1C · PD65W", "블랙 · 7구+1A1C · PD65W"])]


def test_coupang_gets_three_axes_max():
    from src.collectors.option_split import apply, cap_axes
    ex = _extra()
    apply(ex)
    pd = dict(ex, option_split=ex["option_split"])
    c = cap_axes(pd)
    assert len(c["options"]) == 3 and c["options"][2]["name"] == "사양"
    assert c["skus"][0]["spec"] == ["화이트", "7구+1A1C", "PD65W · 스프링 · 기본"]
    assert all(len(v) <= 30 for o in c["options"] for v in o["values"])
    assert len({tuple(k["spec"]) for k in c["skus"]}) == 12 and [k["price"] for k in c["skus"]] == PRICES
    assert len(ex["options"]) == 5                                        # 원본 dict는 그대로(다른 마켓은 5축)


def test_rule_pass_splits_and_readiness_blocks_cn_plug():
    from src.services.option_translate_auto import rule_pass
    from src.seller_console.upload_dispatcher import UploadDispatcher, unresolved_option_values
    ex = _extra()
    rule_pass(ex)
    assert ex["option_split"]["state"] == "split"
    pd = dict(ex, options_src=ex["options_src"])
    assert unresolved_option_values(pd) == []                             # 분해 뒤 30자 초과 미해석 0
    for m in ("coupang", "smartstore"):
        h = [h for h in UploadDispatcher.readiness_holds(pd, m) if h["fix"] == "block"]
        assert h and h[0]["short"].startswith("중국 표준 콘센트(五孔") and "KC" in h[0]["line"]


def test_plug_flag_on_title_only_and_m5_card(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title_src": "公牛国标插座 USB", "title": "멀티탭", "images": ["https://x/a.jpg"], "price": "10"}
    assert any("国标插座" in h["short"] for h in UploadDispatcher.readiness_holds(pd, "coupang"))
    ok = {"title_src": "北欧落地灯", "title": "플로어 스탠드", "images": ["https://x/a.jpg"], "price": "10"}
    assert not any("콘센트" in h["short"] for h in UploadDispatcher.readiness_holds(ok, "coupang"))
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "owner-y8"
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id=seller,
                   title="JOYE 데스크 멀티탭", price="79", currency="CNY", extra=_extra())
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert "중국 표준 콘센트(五孔) — 소싱 제외" in h


def test_options_tab_does_not_call_korean_values_untranslated():
    from pathlib import Path
    h = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    # Y6-C A1: 칸 값 = 사슬이 옮긴 한국어, 못 옮긴 값만 원문 그대로(「아직(…)」 표시 줄은 힌트 줄과 함께 없앴다).
    #   원문에 한자가 없는 값(분해한 「화이트」·「PD65W」)은 사슬이 그대로 돌려준다 — 「미번역」으로 부르지 않는다.
    assert "values: (a.values || []).map(v => v.ko || v.src).join(', ')" in h
