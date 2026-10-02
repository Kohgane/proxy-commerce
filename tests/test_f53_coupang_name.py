"""F53 — 쿠팡 상품명 정규화(오너 2026-09-28).

실측: 번역 제목이 문장형 + 검색어 나열로 쿠팡에 갔다 — 「수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용,
S8 무선 iwatch 신형 Ultra2 시계 거치대, Airpods…」. 게다가 업로더는 `[해외직구] ` + 앞 50자로 잘라 보냈다.
쿠팡 규정: 브랜드 · 상품명 · 핵심 속성 — 조사·문장·중복 금지.

이 파일이 못박는 것:
  ① 수행방패 → 「SPORTLINK 3in1 애플워치 충전 거치대 (에어팟 겸용)」 — 조사 0 · 중복 0 · 100자 이내(오너 회귀)
  ② 핵심 속성은 옵션 원문 **전부에 공통**인 용어집 토큰만 · 겸용은 본문에 **있는** 것만(지어내지 않음)
  ③ 브랜드 위치 = 카테고리별 오너 설정(앞/뒤/빼기)
  ④ 사전검증: 상품명 규칙은 **보류가 아니라 경고 + 자동안**, 자동 생성이면 「확인」 안내
  ⑤ 오너가 고친 이름이 간다 · AI 다듬기는 규칙 검사를 통과할 때만 · 다른 마켓 제목 영향 0
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.uploaders import coupang_title as ct

DIAG = Path("fixtures/realpages/diag/kgp-diagnostic-detail-tmall-com-item-htm-id-617129397971.html")
SHIELD_KO = ("수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용, S8 무선 iwatch 신형 Ultra2 시계 거치대, "
             "Airpods 이어폰 거치대")
PARTICLES = re.compile(r"[가-힣](은|는|을|를|에서|으로)(\s|,|$)")


def _shield() -> dict:
    t = DIAG.read_text(encoding="utf-8")
    e = json.loads(re.search(r'<script type="application/json" id="kgp-diagnostic">(.*?)</script>', t, re.S).group(1))["extracted"]
    return {"title_ko": SHIELD_KO, "title_original": e["title"], "options": e["options"], "skus": e["skus"], "brand": ""}


# ① 오너 회귀
def test_shield_becomes_brand_type_attributes():
    r = ct.build_name(_shield())
    assert r["name"] == "SPORTLINK 3in1 애플워치 충전 거치대 (에어팟 겸용)", r
    assert r["source"] == "rule" and r["warnings"] == []
    assert not PARTICLES.search(r["name"]) and len(r["name"]) <= 100
    assert r["parts"] == {"brand": "SPORTLINK", "type": "애플워치 충전 거치대", "attrs": ["3in1"],
                          "compat": ["에어팟"], "brand_pos": "front"}


def test_the_translated_sentence_is_flagged():
    w = ct.check_name(SHIELD_KO)
    assert any("문장형" in x for x in w) and any("나열" in x for x in w) and any("거치대" in x for x in w)
    assert any("100자" in x for x in ct.check_name("가방 " * 60))


# ② 지어내지 않는다
def test_attributes_come_only_from_values_every_sku_shares():
    p = _shield()
    p["options"] = [{"name": "颜色分类", "values": ["三合一充电支架（白色）", "带理线器（黑色）"]}]
    assert ct.common_attrs(p) == []                       # 한쪽에만 있는 三合一는 핵심 속성이 아니다
    assert "3in1" not in ct.build_name(p)["name"]
    p["options"] = [{"name": "颜色分类", "values": ["白色"]}]
    assert ct.common_attrs(p) == []                       # 값이 하나면 공통을 말할 수 없다


def test_compat_is_only_what_the_text_says():
    ear = {"title_ko": "무선 블루투스 이어폰", "title_original": "无线蓝牙耳机", "brand": "SomeBrand"}
    assert ct.build_name(ear)["name"] == "SomeBrand 무선 블루투스 이어폰"   # 耳机(이어폰) ≠ 에어팟
    pen = {"title_ko": "아이패드 거치대", "title_original": "iPad stand for Apple Pencil", "brand": ""}
    assert ct.build_name(pen)["name"] == "아이패드 거치대 (펜슬 겸용)"


def test_no_type_means_no_invented_name():
    r = ct.build_name({"title_ko": "AAAA BBBB", "brand": "X"})
    assert r["name"] == "" and "직접 적어" in r["warnings"][0]


# ③ 브랜드 위치
def test_brand_position_front_back_omit():
    p = _shield()
    assert ct.build_name(p, "back")["name"] == "3in1 애플워치 충전 거치대 (에어팟 겸용) SPORTLINK"
    assert ct.build_name(p, "omit")["name"] == "3in1 애플워치 충전 거치대 (에어팟 겸용)"


def test_brand_position_is_remembered_per_category():
    from src.db import image_translate_queue_pg as st
    st.reset_for_tests() if hasattr(st, "reset_for_tests") else None
    assert ct.brand_pos_for("u-f53", "DIG") == "front"
    ct.save_brand_pos("u-f53", "DIG", "back")
    ct.save_brand_pos("u-f53", "*", "omit")
    assert ct.brand_pos_for("u-f53", "DIG") == "back" and ct.brand_pos_for("u-f53", "HOM") == "omit"
    with pytest.raises(ValueError):
        ct.save_brand_pos("u-f53", "DIG", "middle")


# ⑤ 우선순위 · AI · 다른 마켓
def test_owner_name_wins_and_is_checked():
    r = ct.effective_name({**_shield(), "coupang_name": "SPORTLINK 애플워치 거치대 화이트", "coupang_name_source": "manual"})
    assert r == {"name": "SPORTLINK 애플워치 거치대 화이트", "source": "manual", "warnings": []}
    r = ct.effective_name({**_shield(), "coupang_name": SHIELD_KO})
    assert r["source"] == "manual" and r["warnings"]


def test_llm_is_accepted_only_when_it_passes_the_rules():
    p = _shield()
    rule = ct.build_name(p)
    bad = ct.llm_rewrite(p, rule, call=lambda _: "SPORTLINK는 애플워치를 충전하는 거치대입니다")
    assert bad["name"] == rule["name"] and "규칙에 걸려" in bad["note"]
    nobrand = ct.llm_rewrite(p, rule, call=lambda _: "3in1 애플워치 충전 거치대")
    assert nobrand["name"] == rule["name"] and "브랜드" in nobrand["note"]
    good = ct.llm_rewrite(p, rule, call=lambda _: "SPORTLINK 3in1 애플워치 충전 거치대 (에어팟·펜슬 겸용)")
    assert good["source"] == "llm" and good["name"].startswith("SPORTLINK")
    boom = ct.llm_rewrite(p, rule, call=lambda _: (_ for _ in ()).throw(RuntimeError("x")))
    assert boom["name"] == rule["name"] and "실패" in boom["note"]


def test_uploader_sends_the_coupang_name_and_other_markets_keep_theirs():
    from src.channel_sync._channel_bridge import to_collected
    from src.uploaders.coupang_uploader import CoupangUploader
    pd = {"title": SHIELD_KO, "title_ko": SHIELD_KO, "title_en": _shield()["title_original"], "price": 29.9,
          "currency": "CNY", "options": _shield()["options"], "skus": _shield()["skus"], "sell_price_krw": 30000}
    prep = CoupangUploader().prepare_product(to_collected(pd))
    assert prep["title"] == "SPORTLINK 3in1 애플워치 충전 거치대 (에어팟 겸용)" and prep["coupang_name_source"] == "rule"
    prep = CoupangUploader().prepare_product(to_collected({**pd, "coupang_name": "SPORTLINK 애플워치 거치대",
                                                            "coupang_name_source": "manual"}))
    assert prep["title"] == "SPORTLINK 애플워치 거치대" and prep["coupang_name_source"] == "manual"
    # 규칙안을 못 만들면 예전 모양(사전검증이 경고로 말한다)
    prep = CoupangUploader().prepare_product(to_collected({**pd, "title": "ABC", "title_ko": "ABC", "title_en": "", "options": [], "skus": []}))
    assert prep["title"].startswith("[해외직구]") and prep["coupang_name_source"] == "fallback"
    # 다른 마켓 — Shopify 제목 판정은 그대로(쿠팡 이름을 안 본다)
    from src.seller_console.upload_dispatcher import shopify_title
    assert shopify_title({**pd, "coupang_name": "SPORTLINK 3in1"}) == ""


# ④ 사전검증 — 경고 + 자동안(보류 아님)
@pytest.fixture
def up(monkeypatch):
    from tests.test_f48_coupang_register import SHIP_ENV, _meta, _no_post
    from src.uploaders.coupang_uploader import CoupangUploader
    for k, v in SHIP_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("COUPANG_IMAGE_SCREEN", "0")
    u = CoupangUploader()
    monkeypatch.setattr(u, "predict_category", lambda *a, **k: "1001")
    monkeypatch.setattr(u, "overseas_outbound_place_code", "OVS1")
    _no_post(u, _meta(attrs=[]))
    return u


def _prep(up, **kw):
    from src.channel_sync._channel_bridge import to_collected
    pd = {"title": SHIELD_KO, "title_ko": SHIELD_KO, "title_en": _shield()["title_original"], "price": 29.9,
          "currency": "CNY", "options": _shield()["options"], "sell_price_krw": 30000, **kw}
    return up.prepare_product(to_collected(pd))


def test_precheck_says_auto_name_needs_a_look(up):
    out = up.precheck(_prep(up))
    assert out["name"]["source"] == "rule" and out["name"]["warnings"] == []
    assert any(n.startswith("상품명 자동 생성 — 확인: 「SPORTLINK 3in1 애플워치 충전 거치대 (에어팟 겸용)」") for n in out["notes"])
    assert not any("상품명" in h for h in out["holds"])


def test_precheck_warns_a_sentence_name_and_offers_the_auto_one(up):
    out = up.precheck(_prep(up, coupang_name=SHIELD_KO, coupang_name_source="manual"))
    note = [n for n in out["notes"] if n.startswith("상품명 규칙:")]
    assert note and "문장형" in note[0] and "자동안 「SPORTLINK 3in1 애플워치 충전 거치대 (에어팟 겸용)」" in note[0]
    assert not any("상품명" in h for h in out["holds"])          # 경고지 보류가 아니다


# 드로어 · 라우트
def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def _seed(seller, **extra):
    from src.seller_console import collect_history_store as S
    sh = _shield()
    iid = S.append(source="extension", seller_id=seller, url="https://detail.tmall.com/item.htm?id=617129397971",
                   title=SHIELD_KO, price="29.90", currency="CNY",
                   extra={"title": SHIELD_KO, "title_ko": SHIELD_KO, "title_en": sh["title_original"],
                          "options": sh["options"], "skus": sh["skus"], "category_code": "DIG", **extra})
    return iid[0] if isinstance(iid, tuple) else iid


def test_route_builds_and_respects_brand_position():
    seller = "u-f53-route"
    c, iid = _client(seller), _seed(seller)
    d = c.get(f"/seller/collect/preview/{iid}/coupang-name").get_json()
    # T3(오너 2026-10-02): 상표는 원문에 있어도 「○○ 호환」으로만 — 애플워치 → 애플워치 호환
    assert d["ok"] and d["name"] == "SPORTLINK 3in1 애플워치 호환 충전 거치대 (에어팟 겸용)" and d["source"] == "rule"
    assert d["brand_pos"] == "front" and d["title_warnings"]
    assert c.post("/seller/coupang/brand-pos", json={"category": "DIG", "pos": "back"}).get_json()["ok"]
    d = c.get(f"/seller/collect/preview/{iid}/coupang-name").get_json()
    assert d["brand_pos"] == "back" and d["name"].endswith("SPORTLINK")
    assert c.post("/seller/coupang/brand-pos", json={"category": "DIG", "pos": "x"}).status_code == 400
    d = c.get(f"/seller/collect/preview/{iid}/coupang-name?check=" + SHIELD_KO).get_json()
    assert d["check_warnings"]


def test_save_keeps_only_owner_names():
    from src.seller_console import collect_history_store as S
    seller = "u-f53-save"
    c, iid = _client(seller), _seed(seller)
    base = {"title": SHIELD_KO}
    c.post(f"/seller/collect/preview/{iid}/save", json={**base, "coupang_name": "SPORTLINK 애플워치 거치대",
                                                          "coupang_name_source": "manual"})
    ex = json.loads(S.get(iid, seller_id=seller)["extra_json"])
    assert ex["coupang_name"] == "SPORTLINK 애플워치 거치대" and ex["coupang_name_source"] == "manual"
    c.post(f"/seller/collect/preview/{iid}/save", json={**base, "coupang_name": "자동안", "coupang_name_source": "rule"})
    ex = json.loads(S.get(iid, seller_id=seller)["extra_json"])
    assert "coupang_name" not in ex                                  # 자동안은 굳히지 않는다


def test_drawer_has_the_coupang_name_block():
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-role="coupang-name"' in t and 'id="cpName"' in t and 'id="cpBrandPos"' in t
    assert "자동 생성 — 확인" in t and "AI로 다듬기" in t and "다른 마켓 제목은 그대로" in t
    assert "coupang_name: ((document.getElementById('cpName')" in t
