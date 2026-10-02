"""T-S3(오너 2026-10-02 폰 등록) — 옵션 축 이름을 쿠팡 카테고리 메타 속성에 **자동으로** 붙인다.

실측: 「尺码(→사이즈)이 카테고리 메타에 없음, 필수: 패션의류/잡화 사이즈」 → 오너가 수동으로 골라야 통과했다.
메타 이름은 앞에 분류가 붙는다(「패션의류/잡화 사이즈」) — 같은 이름 비교만 하던 해석이 못 찾았다.

  1 축 이름(용어집·번역기 한국어)이 들어 있는 메타 속성명으로 자동 연결 — 「자동 매핑 — 확인」(confirm)
  2 후보가 여럿이면 **필수 속성 먼저**, 그다음 짧은 이름
  3 오너 수정이 이긴다 · 시드 밖 축(款式→종류)은 지어 붙이지 않고 예전처럼 보류(고를 목록)
  4 오너 상품 모양(사이즈 SKU 8개)이 이름 보류 없이 SKU 계획까지 간다 · 화면 배지(드로어·폰)
"""
from __future__ import annotations

from pathlib import Path

META = [{"attributeTypeName": "패션의류/잡화 색상", "required": "OPTIONAL"},
        {"attributeTypeName": "신발사이즈", "required": "OPTIONAL"},
        {"attributeTypeName": "패션의류/잡화 사이즈", "required": "MANDATORY"},
        {"attributeTypeName": "수량", "required": "OPTIONAL"}]


def test_owner_case_maps_size_to_the_required_attribute():
    from src.uploaders.coupang_options import resolve_option_name
    r = resolve_option_name("尺码", [m["attributeTypeName"] for m in META], required=["패션의류/잡화 사이즈"])
    assert r == {"meta": "패션의류/잡화 사이즈", "how": "auto", "candidate": "사이즈", "why": "", "confirm": True}
    r2 = resolve_option_name("颜色分类", [m["attributeTypeName"] for m in META])
    assert r2["meta"] == "패션의류/잡화 색상" and r2["confirm"]
    r3 = resolve_option_name("Size", ["색상", "사이즈"], name_ko="사이즈")           # 같은 이름이 있으면 그것(배지 없음)
    assert r3["meta"] == "사이즈" and r3["how"] != "auto"


def test_override_wins_and_unknown_axes_still_hold():
    from src.uploaders.coupang_options import resolve_option_name
    names = [m["attributeTypeName"] for m in META]
    assert resolve_option_name("尺码", names, override="신발사이즈")["meta"] == "신발사이즈"
    held = resolve_option_name("款式", names)
    assert held["meta"] == "" and "골라 주세요" in held["why"]


def test_sku_plan_runs_without_a_name_hold():
    from src.uploaders.coupang_options import plan_sku_items
    sizes = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
    product = {"title": "플리츠 셔츠", "options": [{"name": "尺码", "values": sizes}],
               "skus": [{"sku_id": str(i), "spec": [s], "price": "199", "currency": "CNY", "stock": 5,
                         "sell_price_krw": 39000} for i, s in enumerate(sizes)]}
    plan = plan_sku_items(META, product)
    assert plan["multi"] and len(plan["items"]) == 8
    assert not plan["name_picks"] and not any("메타 속성에 없어" in h for h in plan["holds"])
    assert plan["axis_names"] == [{"orig": "尺码", "meta": "패션의류/잡화 사이즈", "how": "auto", "confirm": True}]
    assert plan["items"][0]["label"] == "S"


def test_screens_show_the_auto_mapping_badge():
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert 'data-role="cp-auto-axis"' in pv and "자동 매핑 — 확인" in pv
    assert 'data-role="m5-cp-auto-axis"' in m5 and "d.auto_axes" in m5
