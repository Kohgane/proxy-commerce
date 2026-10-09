"""Y6-D(오너 2026-10-09 19:45 KST, 플리츠 세트) — 쿠팡 필수 옵션 「패션의류/잡화 사이즈」 자동 채움 회귀.

증거: 쿠팡 SKU 칸 「지금 상태로는 멈춥니다: 필수 옵션: 패션의류/잡화 사이즈」. 10/07 16:26 같은 상품 = 「SKU별 8개」 → 승인.

원인(운영 DB `ae9cee70…` + 재현)
- 코드 회귀가 아니라 **저장된 옵션 이름 덮어쓰기 한 줄**이 방아쇠: `option_name_overrides`
  = `{"尺码": "패션의류/잡화 사이즈", "패션의류/잡화 사이즈": "색상"}` — 두 번째 줄은 10-09 01:21 KST(Z9 장면,
  쿠팡 메타 확인 못 함) 「옵션 이름 고르기」에서 **메타 이름을 열쇠로** 저장됐다(glossary_candidates 시각으로 확인).
- 그 줄이 먹힌 이유 둘:
  ① 편집 화면은 축을 **보이는 이름**(「패션의류/잡화 사이즈」)으로 보내고 원문은 `src_name`에 싣는다 — 덮어쓰기 표를
     보이는 이름으로 찾아 「→ 색상」이 사이즈 축을 가로챘다(01:21 이름 고르기도 그 보이는 이름을 열쇠로 저장).
  ② SKU별 계획(`plan_sku_items`)이 축을 메타 이름으로 바꾼 뒤 SKU마다 `with_meta_names`가 **같은 표로 다시 해석**.
  메타에 「색상」이 있을 때만 드러난다(10/07엔 그 줄이 없었다).
- #871·#870·#861은 쿠팡 옵션 계획을 바꾸지 않았다(파일 이력 확인).
"""
from __future__ import annotations

import json

META = [{"attributeTypeName": "색상", "required": "OPTIONAL"},
        {"attributeTypeName": "패션의류/잡화 사이즈", "required": "MANDATORY"},
        {"attributeTypeName": "수량", "required": "OPTIONAL"}]
COLORS = ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"]
COLORS_KO = ["블랙 상의", "블랙 스커트", "블루 상의", "블루 스커트", "모스 그린 상의", "모스 그린 스커트", "로열 블루 상의", "로열 블루 스커트"]
BAD = {"尺码": "패션의류/잡화 사이즈", "패션의류/잡화 사이즈": "색상"}


def _pleats(nov=None):
    opts = [{"name": "颜色分类", "values": COLORS, "name_ko": "색상", "values_ko": COLORS_KO},
            {"name": "尺码", "values": ["均码"], "name_ko": "사이즈", "values_ko": ["프리사이즈"]}]
    skus = [{"sku_id": str(i), "spec": [v, "均码"], "price": "168", "currency": "CNY", "stock": 180, "sell_price_krw": 52000}
            for i, v in enumerate(COLORS)]
    return {"title": "플리츠 미니멀 여성 여름 세트", "options": opts, "skus": skus,
            "option_name_overrides": dict(nov if nov is not None else BAD)}


def test_stored_1945_overrides_still_fill_size_for_every_sku():
    from src.uploaders.coupang_options import plan_for, option_form
    plan = plan_for(META, _pleats())
    assert plan["multi"] and not plan["holds"], plan["holds"]
    assert len(plan["items"]) == 8
    sizes = [{a["attributeTypeName"]: a["attributeValueName"] for a in it["attributes"]}["패션의류/잡화 사이즈"]
             for it in plan["items"]]
    # 10/07 승인본과 같은 모양: 均码 → 「프리사이즈」 + 색상(메타에서 선택 칸)을 붙여 SKU 8개가 서로 다른 값
    assert sizes[0] == "프리사이즈 블랙 상의" and len(set(sizes)) == 8 and all(x.startswith("프리사이즈 ") for x in sizes)
    f = option_form(META, _pleats())
    assert ("패션의류/잡화 사이즈", "SKU별 8개") in [(x["name"], x["value"]) for x in f["fields"]]


def test_edit_screen_shape_uses_the_source_name_for_overrides():
    """편집 화면이 보내는 모양 — 보이는 이름 + `src_name`. 덮어쓰기는 원문(尺码)으로만 찾는다."""
    from src.uploaders.coupang_options import plan_for, plan_sku_items
    p = _pleats()
    p["options"] = [{"name": "색상", "values": COLORS_KO, "src_name": "颜色分类", "src_values": COLORS},
                    {"name": "패션의류/잡화 사이즈", "values": ["프리사이즈"], "src_name": "尺码", "src_values": ["均码"]}]
    plan = plan_for(META, p)
    assert plan["multi"] and not plan["holds"], plan["holds"]
    # 이름을 골라야 할 때도 열쇠는 원문 — 보이는 이름으로 저장하지 않는다
    p2 = dict(p, options=[{"name": "규격", "values": ["A", "B"], "src_name": "商品规格", "src_values": ["A", "B"]}],
              skus=[{"sku_id": "1", "spec": ["A"], "stock": 1, "sell_price_krw": 1}, {"sku_id": "2", "spec": ["B"], "stock": 1, "sell_price_krw": 1}],
              option_name_overrides={})
    picks = plan_sku_items(META, p2)["name_picks"]
    assert picks and picks[0]["orig"] == "商品规格" and picks[0]["label"] == "규격"


def test_free_size_axis_without_any_override():
    from src.uploaders.coupang_options import plan_for
    plan = plan_for(META, _pleats(nov={}))
    assert plan["multi"] and not plan["holds"]
    vals = [a["attributeValueName"] for it in plan["items"] for a in it["attributes"]
            if a["attributeTypeName"] == "패션의류/잡화 사이즈"]
    assert len(vals) == 8 and all(v.startswith("프리사이즈") for v in vals)          # 均码 → 프리사이즈 자동


def test_name_pick_route_refuses_a_meta_name_as_key(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "u-y6d-name"
    iid = S.append(url="https://detail.tmall.com/item.htm?id=1556", title="t", price="168", currency="CNY",
                   source="extension", seller_id=seller,
                   extra={"options": [{"name": "颜色分类", "values": COLORS}, {"name": "尺码", "values": ["均码"]}]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    r = c.post(f"/seller/collect/preview/{iid}/option-name", json={"orig": "패션의류/잡화 사이즈", "name": "색상"})
    assert r.status_code == 400 and "원래 옵션 이름이 아니에요" in r.get_json()["error"]
    assert "option_name_overrides" not in json.loads(S.get(iid, seller_id=seller)["extra_json"])
    ok = c.post(f"/seller/collect/preview/{iid}/option-name", json={"orig": "尺码", "name": "패션의류/잡화 사이즈"}).get_json()
    assert ok["ok"] and ok["overrides"] == {"尺码": "패션의류/잡화 사이즈"}


def test_translator_badge_says_it_is_usable_as_is():
    html = open("src/seller_console/templates/collect_preview.html", encoding="utf-8").read()
    assert "번역기 값(그대로 써도 됨)" in html and "번역기 값 — 확인" not in html
