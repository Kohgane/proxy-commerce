"""Y6-C A(오너 2026-10-07) — 옵션 한국어 한 함수.

실측 상품 「플리츠 미니멀 여성 여름 세트」(taobao 09-27, SKU 8, 운영 id ae9cee70…): 옵션칸은 원문, 힌트 줄은 번역기 값
(「검은색 상의 · 이끼색 상의 · 코코넛 블루 상의 · 검은색 미디 스커트」), 쿠팡 SKU는 용어집 값(「블랙 상의 · 모스 그린 상의」).
원인: 힌트 줄 = `values_ko` 원문, 쿠팡 = `resolve_option_value` 사슬 — 서로 다른 소스. 이제 옵션칸·SKU 조합표·쿠팡 SKU·
네이버 옵션 값이 전부 `option_ko`(= `resolve_option_value` 한 사슬)를 지난다.
"""
from __future__ import annotations

import json

import pytest

SRC = ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"]
WANT = ["블랙 상의", "블랙 스커트", "블루 상의", "블루 스커트", "모스 그린 상의", "모스 그린 스커트", "로열 블루 상의", "로열 블루 스커트"]
# 오너 캡처의 번역기 값(힌트 줄) — 이 값이 있어도 용어집이 이긴다(「검은색/이끼색」 계열 금지).
TRANSLATOR = ["검은색 상의", "검은색 미디 스커트", "파란색 상의", "파란색 미디 스커트", "이끼색 상의", "이끼빛 그린 미디 스커트",
              "코코넛 블루 상의", "블루 미디 스커트"]


def _extra():
    return {"title": "百褶极简女夏套装", "title_ko": "플리츠 미니멀 여성 여름 세트", "price": "168", "currency": "CNY",
            "options": [{"name": "颜色分类", "values": list(SRC), "name_ko": "색상", "values_ko": list(TRANSLATOR)},
                        {"name": "尺码", "values": ["均码"], "name_ko": "사이즈", "values_ko": ["원 사이즈"]}],
            "skus": [{"sku_id": str(i), "spec": [v, "均码"], "price": 168.0, "currency": "CNY", "stock": 10,
                      "sell_price_krw": 52000} for i, v in enumerate(SRC)],
            "images": ["https://img.alicdn.com/a.jpg"]}


def test_glossary_entries():
    from src.uploaders.coupang_options import resolve_option_value
    want = {"黑色": "블랙", "蓝色": "블루", "宝蓝": "로열 블루", "藏蓝": "네이비", "苔藓绿": "모스 그린", "军绿": "카키 그린",
            "米白": "아이보리", "杏色": "베이지", "卡其": "카키", "酒红": "와인", "上衣": "상의", "半裙": "스커트",
            "连衣裙": "원피스", "套装": "세트", "均码": "프리사이즈"}
    for cn, ko in want.items():
        assert resolve_option_value(cn)["value"] == ko, cn
    assert resolve_option_value("黑色半裙", values_ko="검은색 미디 스커트")["value"] == "블랙 스커트"   # 길이 수식어 없이
    from src.uploaders.coupang_options import OPTION_NAME_GLOSSARY
    assert OPTION_NAME_GLOSSARY["颜色分类"] == "색상" and OPTION_NAME_GLOSSARY["尺码"] == "사이즈"


def test_four_paths_identical():
    from src.collectors import option_ko as K
    from src.uploaders.coupang_options import plan_sku_items
    ex = _extra()
    # ① 옵션칸
    view = K.options_view(ex)
    assert [a["name_ko"] for a in view] == ["색상", "사이즈"]
    assert [v["ko"] for v in view[0]["values"]] == WANT and [v["ko"] for v in view[1]["values"]] == ["프리사이즈"]
    # ② SKU 조합표
    assert [K.spec_ko(ex, k["spec"]) for k in ex["skus"]] == [[w, "프리사이즈"] for w in WANT]
    # ③ 쿠팡 SKU별 등록(실제 계획 함수)
    meta = [{"attributeTypeName": "색상", "required": "MANDATORY"}, {"attributeTypeName": "사이즈", "required": "MANDATORY"}]
    plan = plan_sku_items(meta, ex)
    labels = [it["label"] for it in plan["items"]]
    assert labels == [f"{w} / 프리사이즈" for w in WANT], labels
    # ④ 네이버 옵션 값
    assert K.naver_option_values(ex) == [{"group": "색상", "values": WANT}, {"group": "사이즈", "values": ["프리사이즈"]}]


def test_original_kept_in_data_and_override_wins_everywhere():
    from src.collectors import option_ko as K
    ex = _extra()
    ex["option_value_overrides"] = {"宝蓝上衣": "코발트 블루 상의"}
    assert ex["options"][0]["values"] == SRC and ex["skus"][0]["spec"] == ["黑色上衣", "均码"]      # 원문 보존
    assert K.options_view(ex)[0]["values"][6]["ko"] == "코발트 블루 상의"
    assert K.spec_ko(ex, ["宝蓝上衣", "均码"]) == ["코발트 블루 상의", "프리사이즈"]


@pytest.fixture
def item():
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share_text", url="https://item.taobao.com/item.htm?id=1", seller_id="y6c",
                   title="플리츠 미니멀 여성 여름 세트", price="168", currency="CNY", extra=_extra())
    return iid


def _client():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y6c"
    return c


def test_drawer_shows_korean_with_original_toggle_and_no_hint_line(item):
    h = _client().get(f"/seller/collect/preview/{item}").get_data(as_text=True)
    view = json.loads(h.split("const _OPT_VIEW = ")[1].split(";\n")[0])
    assert [v["ko"] for v in view[0]["values"]] == WANT and view[0]["name_ko"] == "색상"
    assert 'data-role="opt-src-toggle"' in h and "원문 보기" in h
    assert "'한국어 — '" not in h and "_optKoLine" not in h                      # 힌트 줄 없음(값 자체가 한국어)
    sku = h.split('data-role="sku-table"')[1].split("</table>")[0]
    assert "블랙 상의 / 프리사이즈" in sku and "로열 블루 스커트 / 프리사이즈" in sku
    assert 'data-role="sku-src"' in sku and "黑色上衣 / 均码" in sku                # 원문은 「원문 보기」로만(숨김 줄)


def test_save_keeps_original_and_records_edits_as_overrides(item):
    from src.seller_console import collect_history_store as S
    edited = list(WANT)
    edited[6] = "코발트 블루 상의"                                               # 하나만 고침
    body = {"title": "플리츠 미니멀 여성 여름 세트", "price": "168", "currency": "CNY",
            "options": [{"name": "색상", "values": edited, "src_name": "颜色分类", "src_values": SRC},
                        {"name": "사이즈", "values": ["프리사이즈"], "src_name": "尺码", "src_values": ["均码"]}]}
    r = _client().post(f"/seller/collect/preview/{item}/save", json=body)
    assert r.status_code == 200 and r.get_json()["ok"]
    ex = json.loads(S.get(item, seller_ids={"y6c"})["extra_json"])
    assert ex["options"][0]["values"] == SRC and ex["options"][1]["values"] == ["均码"]        # 원문 그대로
    assert ex["options"][0]["values_ko"] == TRANSLATOR                                          # 번역기 값도 지우지 않는다
    assert ex["option_value_overrides"] == {"宝蓝上衣": "코발트 블루 상의"}                    # 고친 값만
    assert ex["option_name_overrides"] == {}


def test_new_option_without_src_saved_as_typed(item):
    from src.seller_console import collect_history_store as S
    body = {"title": "x", "options": [{"name": "색상", "values": ["블랙", "화이트"]}]}
    _client().post(f"/seller/collect/preview/{item}/save", json=body)
    ex = json.loads(S.get(item, seller_ids={"y6c"})["extra_json"])
    assert ex["options"] == [{"name": "색상", "values": ["블랙", "화이트"]}]
