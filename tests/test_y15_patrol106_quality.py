"""순찰 106-B(오너 2026-10-26) — 사전검증 「등록 품질」(주의 · 보류 아님) + 「자동 수정」.

재현 재료 = 순찰 99 원피스 `5d1b6679`의 실측 넷: 사이즈 「36 80-105근」 · 상품명 「Taffa 타파파 …」(가게 「Taffa 唐发发」) ·
상세 2번 중국 가게 약관 사진(「그래도 넣기」로 들어감) · 의류인데 「대형화물」.
"""
from __future__ import annotations

import copy
import json

import pytest

EX = {"title": "Taffa 唐发发 2025夏季新款真丝连衣裙", "shop_name": "Taffa 唐发发", "title_ko": "Taffa 타파파 여름 신상 실크 원피스",
      "category_code": "CLO",
      "options": [{"name": "尺码", "name_ko": "사이즈", "values": ["36 80-105斤", "38 105-110斤"]}],
      "detail_images": ["https://a/1.jpg", "https://a/2.jpg", "https://a/3.jpg"],
      "detail_images_ko": [
          {"idx": 1, "status": "done", "url": "https://c/2.jpg", "promo_include": True,
           "source_text": "服务细则 顺丰包邮 中国大陆 7天无理由退换货"},
          {"idx": 2, "status": "done", "url": "https://c/3.jpg", "source_text": "面料 真丝 尺码 36 38"}]}


@pytest.fixture(autouse=True)
def _fresh_state():
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    yield
    q.reset_for_tests()


@pytest.fixture(autouse=True)
def _no_bulky(monkeypatch):
    from src.seller_console import shipping_ratio
    monkeypatch.setattr(shipping_ratio, "estimate", lambda pd, sid="", market="": {"state": "unknown", "line": "부피 미확인"})


def _pd(ex):
    from src.order_webhook import app
    from src.seller_console.product_builder import build_product
    with app.app_context():
        return build_product({"id": "it1", "title": ex["title"], "extra_json": json.dumps(ex, ensure_ascii=False)}, seller_id="s")


def _codes(ex, pd):
    from src.seller_console import listing_quality as lq
    return {f["code"]: f for f in lq.checks(ex, pd)}


def test_title_transliterating_the_shop_hanzi_is_flagged_and_fixed_to_latin_only():
    from src.seller_console import listing_quality as lq
    ex = copy.deepcopy(EX)
    pd = _pd(ex)
    f = _codes(ex, pd)["title_brand"]
    assert f["fix"] == "rule" and "唐发发" in f["line"] and "타파파" in f["line"] and "「Taffa 여름 신상 실크 원피스」" in f["line"]
    r = lq.apply_fixes(ex, pd, ai=False)
    assert ex["title_ko"] == pd["title_ko"] == "Taffa 여름 신상 실크 원피스" and r["changed"]
    assert "title_brand" not in _codes(ex, pd)


def test_title_without_transliteration_is_not_flagged():
    ex = dict(copy.deepcopy(EX), title_ko="Taffa 여름 신상 실크 원피스")
    assert "title_brand" not in _codes(ex, _pd(ex))
    ex = dict(copy.deepcopy(EX), shop_name="", brand="")
    assert "title_brand" not in _codes(ex, _pd(ex))                       # 브랜드 판정 없음 = 검사 없음


def test_outgoing_shop_policy_photo_is_flagged_and_auto_fix_drops_it():
    from src.services import detail_image_plan as dip
    from src.seller_console import listing_quality as lq
    ex = copy.deepcopy(EX)
    pd = _pd(ex)
    f = _codes(ex, pd)["shop_policy"]
    assert f["idx"] == [1] and "상세 2번" in f["line"]
    lq.apply_fixes(ex, pd, ai=False)
    assert dip.verdict(ex["detail_images_ko"][0], ex["detail_images"][1])["use"] == "excluded"
    assert "shop_policy" not in _codes(ex, pd)
    ex2 = copy.deepcopy(EX)                                               # 약관 사진이 이미 빠져 있으면(기본) 말하지 않는다
    ex2["detail_images_ko"][0].pop("promo_include")
    assert "shop_policy" not in _codes(ex2, _pd(ex2))


def test_jin_left_in_an_outgoing_option_value_is_converted_by_rule_and_kept_by_overlay():
    from src.services import ai_fix
    from src.seller_console import listing_quality as lq
    ex = copy.deepcopy(EX)
    ex["option_value_overrides"] = {"36 80-105斤": "36 80-105근"}           # 사람·옛 AI가 단위만 바꾼 값(순찰 99 실측)
    pd = _pd(ex)
    f = _codes(ex, pd)["option_cjk"]
    assert f["fix"] == "rule" and "36 80-105근" in f["line"] and "1근 = 0.5kg" in f["line"]
    r = lq.apply_fixes(ex, pd, ai=False)
    assert ex["option_value_overrides"]["36 80-105斤"] == "36 40~52.5kg" and any("40~52.5kg" in a for a in r["applied"])
    assert ex["ai_fixes"]["option_value:36 80-105斤"]["provider"] == "rule"      # Y8 기록 — 「AI가 고쳤어요」·되돌리기 그대로
    fresh = _pd(dict(ex, option_value_overrides={}))                       # 화면이 옛 값을 들고 와도 저장된 수정이 얹힌다
    ai_fix.overlay(fresh, ex)
    assert fresh["option_value_overrides"]["36 80-105斤"] == "36 40~52.5kg"


def test_hanzi_left_goes_through_the_y8_ai_path_with_its_guard(monkeypatch):
    from src.services import ai_fix
    from src.seller_console import listing_quality as lq
    ex = copy.deepcopy(EX)
    ex["options"] = [{"name": "颜色", "name_ko": "색상", "values": ["盘扣款", "立领款"]}]
    ex["option_value_overrides"] = {"盘扣款": "盘扣 스타일", "立领款": "立领 스타일"}
    pd = _pd(ex)
    assert _codes(ex, pd)["option_cjk"]["fix"] == "ai"
    asked = []
    monkeypatch.setattr(ai_fix, "_call", lambda task, pd: asked.append(task) or
                        {"json": {"values": {"盘扣款": "매듭 단추 스타일", "立领款": "立领 스타일"}}, "provider": "anthropic", "model": "m"})
    r = lq.apply_fixes(ex, pd)
    assert asked[0]["kind"] == "option_value" and set(asked[0]["values"]) == {"盘扣款", "立领款"}
    assert ex["option_value_overrides"]["盘扣款"] == "매듭 단추 스타일"
    assert ex["option_value_overrides"]["立领款"] == "立领 스타일"             # 한자 섞인 AI 답은 검사에서 버림
    assert any("검사에서 떨어졌어요" in x for x in r["left"])
    ex2, pd2 = copy.deepcopy(ex), _pd(ex)
    monkeypatch.setattr(ai_fix, "_call", lambda task, pd: (_ for _ in ()).throw(AssertionError("ai=False면 안 부른다")))
    assert lq.apply_fixes(ex2, pd2, ai=False)["left"]


def test_apparel_marked_bulky_is_a_caution_without_auto_fix(monkeypatch):
    from src.seller_console import listing_quality as lq
    from src.seller_console import shipping_ratio
    monkeypatch.setattr(shipping_ratio, "estimate", lambda pd, sid="", market="": {
        "state": "bulky", "code": "bulky_carrier", "bulky": ["실중량 135kg"], "line": "대형화물 — 실중량 49kg→135kg"})
    ex = copy.deepcopy(EX)
    pd = _pd(ex)
    f = _codes(ex, pd)["apparel_bulky"]
    assert f["fix"] == "" and "사이즈표의 몸무게" in f["line"] and "무게·크기 직접 넣기" in f["line"]
    assert any("의류 대형화물" in x for x in lq.apply_fixes(ex, pd, ai=False)["left"])
    ex2 = dict(copy.deepcopy(EX), category_code="FUR", title_ko="원목 소파 3인용")
    assert "apparel_bulky" not in _codes(ex2, _pd(ex2))


def test_card_shape_and_clean_product_has_no_card():
    from src.seller_console import listing_quality as lq
    ex = copy.deepcopy(EX)
    c = lq.card(lq.checks(ex, _pd(ex)))
    assert {x["code"] for x in c["lines"]} == {"title_brand", "shop_policy"} and c["fixable"] == 2
    clean = {"title": "实木椅子", "title_ko": "원목 의자", "options": [], "detail_images": [], "detail_images_ko": []}
    assert lq.card(lq.checks(clean, _pd(clean))) == {}


def test_quality_fix_route_saves_and_returns_the_new_title():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    ex = copy.deepcopy(EX)
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=99", seller_id="q1",
                   title=ex["title_ko"], price="1058", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "q1"
    d = c.post(f"/seller/collect/{iid}/quality-fix", json={"ai": False}).get_json()
    assert d["ok"] and d["changed"] and d["fields"]["title_ko"] == "Taffa 여름 신상 실크 원피스"
    assert d["quality"] == {}                                               # 남은 품질 줄 없음
    saved = json.loads(S.get(iid, seller_ids={"q1"})["extra_json"])
    assert saved["title_ko"] == "Taffa 여름 신상 실크 원피스" and not saved["detail_images_ko"][0].get("promo_include")
    with c.session_transaction() as s:
        s["user_id"] = "someone-else"
    assert c.post(f"/seller/collect/{iid}/quality-fix", json={}).status_code == 404


def test_both_cards_render_the_block_and_route_the_button():
    import pathlib
    rb = pathlib.Path("src/seller_console/templates/_risk_block.html").read_text(encoding="utf-8")
    assert "window.kgpQualityHtml" in rb and 'data-role="quality-fix"' in rb and "/quality-fix" in rb
    for t in ("collect_preview.html", "_m5_flow.html"):
        s = pathlib.Path("src/seller_console/templates", t).read_text(encoding="utf-8")
        assert "kgpQualityHtml(" in s and "quality-fix" in s and "kgpQualityFix(" in s, t


def test_coupang_name_keeps_adnominal_ending_before_dependent_noun():
    """D 실측(10-26 00:10 쿠팡 우주대행 16427134089): 「흐르는 듯」 → 「흐르 듯」 — 관형형 「는」을 조사로 떼었다."""
    from src.uploaders import coupang_title as ct
    p = {"title_ko": "Taffa 여름 신상 실크 원피스 흐르는 듯 우아한 민소매", "brand": "", "category_code": "CLO"}
    p["title"] = p["title_ko"]
    assert "흐르는 듯" in ct.build_name(p, "none")["name"]
    assert ct._strip_particle("원피스는", "예뻐요") == "원피스" and ct._strip_particle("흐르는", "듯") == "흐르는"
    assert ct._strip_particle("가방을", "") == "가방" and ct._strip_particle("빛나는", "것") == "빛나는"
