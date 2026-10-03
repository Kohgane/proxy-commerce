"""Y2(오너 2026-10-04) — 옵션 탭 「한국어로 번역」(축 이름 + 값 한 번에) · 축 이름 사전 大小/尺寸/尺码→사이즈, 颜色/颜色分类→색상.

시나리오: 大小/颜色分类 상품 → 버튼 1번(`/collect/<id>/translate-now`) → 사이즈/색상 + 값 번역 →
쿠팡 필수 옵션(사이즈·색상)이 채워져 계획에 보류 0 → 사전검증 준비 판정(옵션 미해석) 통과.
"""
from __future__ import annotations

import json

import pytest

META = [{"attributeTypeName": "색상", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED"},
        {"attributeTypeName": "사이즈", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED"}]


def _product():
    return {"title": "블랙홀 무드등", "title_ko": "블랙홀 무드등", "price": "69.90", "currency": "CNY",
            "images": ["https://img.alicdn.com/a.jpg"],
            "options": [{"name": "大小", "values": ["小号"]},
                        {"name": "颜色分类", "values": ["朦胧月光款"]}],
            "skus": [{"spec": ["小号", "朦胧月光款"], "price": "69.90", "stock": 10}]}


@pytest.mark.parametrize("name,expected", [("大小", "사이즈"), ("尺寸", "사이즈"), ("尺码", "사이즈"),
                                           ("颜色", "색상"), ("颜色分类", "색상")])
def test_axis_name_glossary(name, expected):
    from src.services.option_translate_auto import rule_pass
    ex = {"options": [{"name": name, "values": ["S"]}]}
    rule_pass(ex)
    assert ex["options"][0]["name_ko"] == expected


def test_one_button_translates_axes_and_values_and_fills_coupang_required(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.seller_console.ai import translator as T
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.uploaders.coupang_options import plan_for

    def opts(self, options):
        tbl = {"朦胧月光款": "문라이트", "小号": "소형", "大号": "대형"}
        vals = options[0]["values"]
        return {"provider": "papago", "options": [{"values": vals, "values_ko": [tbl.get(v, v) for v in vals]}]}
    monkeypatch.setattr(T.AITranslator, "translate_options", opts)
    monkeypatch.setattr(T.AITranslator, "translate_product", lambda self, p: {"title_ko": "", "provider": "none"})
    seller = "owner-y2"
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id=seller,
                   title="블랙홀 무드등", price="69.90", currency="CNY", extra=_product())
    before = _product()
    assert any("미해석" in h["short"] for h in UploadDispatcher.readiness_holds(before, "coupang"))
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    d = c.post(f"/seller/collect/{iid}/translate-now", json={}).get_json()
    assert d["ok"], d
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    names = {o["name"]: o.get("name_ko") for o in ex["options"]}
    assert names == {"大小": "사이즈", "颜色分类": "색상"}
    assert ex["options"][1]["values_ko"] == ["문라이트"]
    assert not any("미해석" in h["short"] for h in UploadDispatcher.readiness_holds(ex, "coupang"))
    plan = plan_for(META, {**ex, "title": "블랙홀 무드등"}, meta_ok=True)
    assert plan["holds"] == [], plan["holds"]
    got = {a.get("attributeTypeName"): a.get("attributeValueName") for a in plan["attributes"]}
    assert got.get("사이즈") == "소형" and got.get("색상") == "문라이트", got


def test_options_tab_has_translate_button():
    from pathlib import Path
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-role="options-translate"' in pv and "translateOptionsKo" in pv and "/translate-now" in pv
