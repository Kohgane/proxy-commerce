"""Y7-I(오너 2026-10-09 23:25 KST, 플리츠 세트 · 셰고가) — 네이버 400 `optionInfo` 「중복된 옵션이 있습니다. (옵션명 : 색상)」.

원인: 네이버 그룹 이름(`option_ko.axis_ko`)이 덮어쓰기 표를 **보이는 이름**으로 찾았다(Y6-D와 같은 결함 — 쿠팡만 고쳤다).
편집 화면은 사이즈 축을 「패션의류/잡화 사이즈」(쿠팡 메타 이름 — SKU 칸에서 고른 것)로 보내고, 01:21 KST 줄
「패션의류/잡화 사이즈 → 색상」이 그 축을 「색상」으로 바꿔 그룹 이름이 [색상, 색상]이 됐다.
또 한 표(`option_name_overrides`)에 **사람이 고친 보이는 이름**과 **쿠팡 메타 이름**이 섞여 있었다 — 쿠팡 메타 이름이
네이버 그룹 이름·화면까지 갔다.

계약
- 축 이름은 한 함수(`option_ko.axis_ko`, 원문 열쇠) — 쿠팡·네이버·화면 같은 함수. 덮어쓰기 해석은 그 안에서 한 번.
- 저장값은 `split_name_overrides`로 둘로: 사람 이름(모든 마켓) / 쿠팡 메타 이름(쿠팡만). 원문 아닌 열쇠는 버린다.
- 그룹 이름 중복·빈 이름은 전송 전 `naver_option_dup` 보류(사전검증·등록 같은 함수).
- 단일값 축(사이즈 = 프리사이즈): 문서에서 허용 여부를 못 찾아 그대로 둔다(그룹 2개) — 거부되면 응답 원문.
"""
from __future__ import annotations

import json

COLORS = ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"]
COLORS_KO = ["블랙 상의", "블랙 스커트", "블루 상의", "블루 스커트", "모스 그린 상의", "모스 그린 스커트", "로열 블루 상의", "로열 블루 스커트"]
PICKS = [{"at": "2026-10-02T07:07:33Z", "kind": "name", "orig": "尺码", "value": "패션의류/잡화 사이즈"},
         {"at": "2026-10-08T16:21:20Z", "kind": "name", "orig": "패션의류/잡화 사이즈", "value": "색상"}]
DIRTY = {"尺码": "패션의류/잡화 사이즈", "패션의류/잡화 사이즈": "색상"}


def _extra(nov=None, picks=None, coupang=None):
    """운영 `ae9cee70…` 저장값 모양."""
    ex = {"options": [{"name": "颜色分类", "values": COLORS, "name_ko": "색상", "values_ko": COLORS_KO},
                      {"name": "尺码", "values": ["均码"], "name_ko": "사이즈", "values_ko": ["프리사이즈"]}],
          "skus": [{"sku_id": str(i), "spec": [v, "均码"], "price": "168", "currency": "CNY", "stock": 180, "sell_price_krw": 52000}
                   for i, v in enumerate(COLORS)],
          "option_name_overrides": dict(DIRTY if nov is None else nov),
          "glossary_candidates": list(PICKS if picks is None else picks)}
    if coupang is not None:
        ex["coupang_option_names"] = coupang
    return ex


def _built(ex):
    """서버가 저장값으로 만드는 상품(폰 카드·사전검증 잡) — product_builder 와 같은 정규화."""
    from src.collectors.option_ko import split_name_overrides
    human, cp = split_name_overrides(ex)
    return {**ex, "option_name_overrides": human, "coupang_option_names": cp}


def test_split_drops_non_source_keys_and_separates_coupang_picks():
    from src.collectors.option_ko import split_name_overrides
    human, cp = split_name_overrides(_extra())
    assert human == {} and cp == {"尺码": "패션의류/잡화 사이즈"}        # 「패션의류/잡화 사이즈 → 색상」 버림


def test_1_stored_values_with_dirty_line_give_color_size_and_8_combos():
    from src.uploaders.naver_options import plan
    p = plan(_built(_extra()))
    assert p["mode"] == "combo", p
    assert p["option_info"]["optionCombinationGroupNames"] == {"optionGroupName1": "색상", "optionGroupName2": "사이즈"}
    assert len(p["option_info"]["optionCombinations"]) == 8
    assert p["option_info"]["optionCombinations"][0]["optionName2"] == "프리사이즈"


def test_edit_screen_shape_goes_through_server_split(monkeypatch):
    """화면은 보이는 이름 + src_name + 저장값 그대로의 덮어쓰기 표를 보낸다 — 서버(`_outbound_images`)가 저장값으로 다시 나눈다."""
    from src.seller_console import collect_history_store as CH
    import src.seller_console.views as V
    from src.services import image_reachability as R
    monkeypatch.setattr(R, "check_all", lambda *a, **k: None)
    iid = CH.append(source="test", url="https://detail.tmall.com/item.htm?id=1556", title="플리츠", price="168",
                    currency="CNY", extra=_extra(), seller_id="y7i")
    iid = iid[0] if isinstance(iid, tuple) else iid
    form = {"options": [{"name": "색상", "values": COLORS_KO, "src_name": "颜色分类", "src_values": COLORS},
                        {"name": "패션의류/잡화 사이즈", "values": ["프리사이즈"], "src_name": "尺码", "src_values": ["均码"]}],
            "skus": _extra()["skus"], "option_name_overrides": dict(DIRTY), "item_id": iid}
    from src.order_webhook import app
    with app.test_request_context():
        from flask import session
        session["user_id"] = "y7i"
        pd, _w, _r = V._outbound_images(form, iid)
    assert pd["option_name_overrides"] == {} and pd["coupang_option_names"] == {"尺码": "패션의류/잡화 사이즈"}
    from src.uploaders.naver_options import group_names, plan
    # 화면이 보인 이름 「패션의류/잡화 사이즈」는 그 축의 쿠팡 메타 이름 — 사람 이름이 아니라 원문 해석(사이즈)으로 간다
    assert group_names(pd, 2) == ["색상", "사이즈"]
    p = plan(pd)
    assert p["mode"] == "combo" and len(p["option_info"]["optionCombinations"]) == 8, p


def test_after_cleanup_same_groups_and_coupang_keeps_meta_name():
    """저장값 정리(원문 아닌 열쇠 삭제 · 쿠팡 고른 이름은 쿠팡 표로) 뒤에도 같은 결과 · 쿠팡은 메타 이름을 그대로 쓴다."""
    clean = _extra(nov={}, picks=[], coupang={"尺码": "패션의류/잡화 사이즈"})
    from src.uploaders.naver_options import plan
    p = plan(_built(clean))
    assert p["option_info"]["optionCombinationGroupNames"] == {"optionGroupName1": "색상", "optionGroupName2": "사이즈"}
    from src.uploaders.coupang_options import plan_for
    meta = [{"attributeTypeName": "색상", "required": "OPTIONAL"},
            {"attributeTypeName": "패션의류/잡화 사이즈", "required": "MANDATORY"}]
    cp = plan_for(meta, _built(clean))
    assert cp["multi"] and not cp["holds"] and len(cp["items"]) == 8


def test_duplicate_group_names_are_held_before_sending():
    from src.uploaders.naver_options import plan, limit_hold, REASON_GROUP_DUP
    dup = _built(_extra(nov={"颜色分类": "색상", "尺码": "색상"}, picks=[]))
    p = plan(dup)
    assert p["mode"] == "hold" and p["reason_code"] == REASON_GROUP_DUP == "naver_option_dup"
    assert "겹쳐요" in p["why"] and limit_hold(dup) == p["why"]          # 사전검증과 같은 함수


def test_prevalidate_reports_naver_option_dup(monkeypatch):
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    pd = {**_built(_extra(nov={"颜色分类": "색상", "尺码": "색상"}, picks=[])), "title_ko": "플리츠", "price": 168,
          "images": ["https://img.alicdn.com/a.jpg"], "description": "본문", "item_id": "it-7i"}
    r = UD.UploadDispatcher().prevalidate(pd, ["smartstore"])[0]
    assert r.hold and r.error_code == "naver_option_dup"
    assert r.action_url == "/seller/collect/preview/it-7i?tab=options"


def test_upload_never_sends_duplicate_groups(monkeypatch):
    import pytest
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "image_upload_enabled", False)
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: pytest.fail("중복 그룹으로 네이버에 보냄"))
    p = {**_built(_extra(nov={"颜色分类": "색상", "尺码": "색상"}, picks=[])), "sku": "P", "title": "플리츠",
         "price": 52000, "images": ["https://a/b.jpg"], "description_html": "<p>본문</p>"}
    res = up.upload_product(p)
    assert res["held"] is True and res["reason_code"] == "naver_option_dup"
