"""F(오너 2026-10-06) — Y6 확장: 상표 게이트를 **옵션 값·규격표 값**에도.

운영 실측: 쿠팡 고가네 16401838524 옵션 「디올 블루 미디 스커트」가 통과 — 게이트가 상품명만 봤다.
걸리면 상품 보류가 아니라 그 값만 바꿀 말을 제안하고 검수 카드(M5)에 보인다. 치환표는 코드 상수(`BRAND_COLOR_SUBS`).
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize("value,suggest", [
    ("디올 블루 미디 스커트", "딥 블루 미디 스커트"),          # 운영 실측 값
    ("迪奥蓝", "딥 블루"),
    ("迪奥蓝色", "딥 블루"),
    ("디올블루", "딥 블루"),
    ("티파니 블루 원피스", "민트 블루 원피스"),
    ("蒂芙尼蓝", "민트 블루"),
    ("에르메스 오렌지", "브라이트 오렌지"),
    ("爱马仕橙", "브라이트 오렌지"),
    ("샤넬 블랙 L", "블랙 L"),
    ("구찌 그린", "딥 그린"),
    ("팬톤 피치 퍼즈", "피치 퍼즈"),                             # 팬톤 → 삭제
    ("디즈니 공주 머리띠", "공주 머리띠"),                       # 그 밖의 상표명(trademarks)은 빼서 제안
])
def test_brand_value_fix_table(value, suggest):
    from src.collectors import ko_polish as K
    r = K.brand_value_fix(value)
    assert r["hits"] and r["suggest"] == suggest


@pytest.mark.parametrize("value", ["블랙", "딥 블루 미디 스커트", "白色", "M", "애플워치 호환 스트랩"])
def test_brand_value_fix_no_hit(value):
    from src.collectors import ko_polish as K
    assert K.brand_value_fix(value) == {"value": value, "suggest": value, "hits": []}


def test_table_is_code_constant():
    from src.collectors import ko_polish as K
    t = dict(K.BRAND_COLOR_SUBS)
    assert t["디올 블루"] == t["迪奥蓝"] == "딥 블루" and t["티파니 블루"] == t["蒂芙尼蓝"] == "민트 블루"
    assert t["에르메스 오렌지"] == t["爱马仕橙"] == "브라이트 오렌지" and t["샤넬 블랙"] == "블랙"
    assert t["구찌 그린"] == "딥 그린" and t["팬톤"] == ""


def test_suggestions_not_applicable_cases():
    from src.collectors import ko_polish as K
    rows = K.brand_value_suggestions([("색상", "팬톤"), ("색상", "迪奥蓝白"), ("색상", "블랙"), ("색상", "팬톤")])
    assert [r["value"] for r in rows] == ["팬톤", "迪奥蓝白"]                 # 같은 값 한 번 · 안 걸린 값 없음
    assert rows[0]["applicable"] is False and "남는 말이 없어요" in rows[0]["why"]
    assert rows[1]["applicable"] is False and "한자" in rows[1]["why"]


def _pd(**kw):
    return {"title": "여성 플리츠 미디 스커트", "title_ko": "여성 플리츠 미디 스커트", "title_src": "百褶半身裙",
            "price": "30000", "currency": "KRW", "images": ["https://img.alicdn.com/a.jpg"],
            "options": [{"name": "颜色分类", "name_ko": "색상", "values": ["디올 블루 미디 스커트", "블랙 미디 스커트"]}],
            "skus": [{"spec": ["디올 블루 미디 스커트"], "price": "30000", "stock": 5},
                     {"spec": ["블랙 미디 스커트"], "price": "30000", "stock": 5}],
            "description": "플리츠 스커트입니다.", **kw}


def test_option_value_brand_does_not_hold():
    """상품 보류 아님 — 상표 보류(fix=trademark)가 옵션 값 「디올 블루」 때문에 생기지 않는다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    holds = UploadDispatcher.readiness_holds(_pd(), "coupang")
    assert not [h for h in holds if h["fix"] == "trademark"]


def test_title_ip_gate_unchanged():
    """Y6 제목 게이트는 그대로 — 원문 제목의 IP명은 여전히 보류."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    holds = UploadDispatcher.readiness_holds(_pd(title_src="迪士尼百褶裙"), "coupang")
    assert [h for h in holds if h["fix"] == "trademark" and "디즈니" in h["short"]]


def _item(seller, **extra):
    from src.seller_console import collect_history_store as S
    pd = _pd()
    ex = {"title_ko": pd["title_ko"], "title": pd["title_src"], "images": pd["images"], "options": pd["options"],
          "skus": pd["skus"], "price": "30000", "currency": "KRW", **extra}
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=16401838524", seller_id=seller,
                    title=pd["title_ko"], price="30000", currency="KRW", extra=ex)


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"] = seller
    return c


def test_m5_card_shows_suggestion_and_apply():
    from src.seller_console import collect_history_store as S
    seller = "owner-f-brand"
    iid = _item(seller, detail_specs=[["颜色", "迪奥蓝"], ["材质", "聚酯纤维"]])
    c = _client(seller)
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-brand-values"' in h and 'data-role="m5-brand-fix"' in h
    assert "「디올 블루 미디 스커트」" in h and "<strong>딥 블루 미디 스커트</strong>" in h
    assert "규격표 颜色: 「迪奥蓝」" in h and "<strong>딥 블루</strong>" in h
    assert "상품은 보류하지 않아요" in h
    r = c.post(f"/seller/collect/{iid}/brand-value-fix", json={})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and len(d["applied"]) == 2 and d["left"] == []
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert ex["option_value_overrides"]["디올 블루 미디 스커트"] == "딥 블루 미디 스커트"
    assert ex["skus"][0]["spec"] == ["디올 블루 미디 스커트"]                # 원문·SKU는 그대로(해석 순서 0번으로만)
    assert ex["detail_specs"][0] == ["颜色", "딥 블루"] and ex["detail_specs_src"][0] == ["颜色", "迪奥蓝"]
    h2 = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-brand-values"' not in h2 and "딥 블루 미디 스커트" in h2   # 카드 옵션 줄도 바뀐 값
    assert c.post(f"/seller/collect/{iid}/brand-value-fix", json={}).status_code == 400   # 더 바꿀 값 없음


def test_clean_item_has_no_block():
    seller = "owner-f-clean"
    iid = _item(seller, options=[{"name": "颜色", "values": ["블랙"]}], skus=[{"spec": ["블랙"], "price": "1", "stock": 1}])
    h = _client(seller).get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-brand-values"' not in h
