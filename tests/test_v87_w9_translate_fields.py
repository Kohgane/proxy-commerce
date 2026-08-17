"""tests/test_v87_w9_translate_fields.py — v87-W9: 번역 전필드 신뢰화.

item1 언어감지 교정(가나·한자→ja) · item2 상용구 변형 내성 · item3 옵션값 번역(원문보존) ·
item4/5 필드별 상태·뱃지 잔존 소거 · item6 판정 모순(없음확인 분모 제외).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.seller_console.ai.translator import (
    AITranslator, strip_market_boilerplate, _route_src_lang)
from src.collectors.collect_status import compute_collect_status


# ── item1: 언어 감지 교정 + 감지/체인 기록 ───────────────────────────
def test_route_src_lang_kana_or_han_is_ja():
    assert _route_src_lang("玉渕") == "ja"            # 한자 1자(가나 없음)도 ja(zh 오판 방지)
    assert _route_src_lang("SUPERONE 手帳") == "ja"   # 라틴 비율 무관
    assert _route_src_lang("ブラウン") == "ja"
    assert _route_src_lang("스마트폰") == "ko"
    assert _route_src_lang("phone grip") == "en"


def test_translate_product_records_detected_lang_and_chain(monkeypatch):
    monkeypatch.delenv("TRANSLATE_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "a")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "b")
    import requests

    def _post(url, headers=None, data=None, timeout=None, **k):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"message": {"result": {"translatedText": "옥연"}}}
        return R()
    monkeypatch.setattr(requests, "post", _post)
    res = AITranslator().translate_product({"title": "玉渕", "description": ""})
    assert res["detected_lang"] == "ja"
    assert res["chain"][0] == "papago"          # ja → papago 선두(mymemory 아님)


# ── item2: 상용구 변형 내성 ──────────────────────────────────────────
@pytest.mark.parametrize("raw,expect_absent", [
    ("楽ギフ_包装 TSUMUGI 紬", "楽ギフ"),
    ("楽ギフ＿包装　TSUMUGI", "包装"),
    ("【楽ギフ_包装】木製ケース", "楽ギフ"),
    ("楽ギフ包装 レコード", "楽ギフ"),
])
def test_boilerplate_variants_stripped(raw, expect_absent):
    out = strip_market_boilerplate(raw)
    assert expect_absent not in out
    assert out.strip()                          # 빈 제목 아님(상품어 보존)


def test_boilerplate_keeps_product_words():
    assert strip_market_boilerplate("TSUMUGI 木製ケース") == "TSUMUGI 木製ケース"


# ── item3: 옵션 값 번역 + 원문 보존 ──────────────────────────────────
def test_translate_options_translates_and_preserves(monkeypatch):
    monkeypatch.delenv("TRANSLATE_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "a")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "b")
    import requests
    kmap = {"ブラウン": "브라운", "ブラック": "블랙", "カラー": "컬러"}

    def _post(url, headers=None, data=None, timeout=None, **k):
        txt = (data or {}).get("text", "")
        class R:
            def raise_for_status(self): pass
            def json(self): return {"message": {"result": {"translatedText": "\n".join(kmap.get(l, l) for l in txt.split("\n"))}}}
        return R()
    monkeypatch.setattr(requests, "post", _post)
    res = AITranslator().translate_options([{"name": "カラー", "values": ["ブラウン", "ブラック"]}])
    o = res["options"][0]
    assert res["translated"] is True
    assert o["values_ko"] == ["브라운", "블랙"]      # 번역
    assert o["values"] == ["ブラウン", "ブラック"]    # 원문 보존(병기)


def test_translate_options_empty_is_noop():
    assert AITranslator().translate_options([])["options"] == []


# ── item6: 판정 모순 — 없음 확인 분모 제외 ────────────────────────────
def test_single_product_is_full_score():
    r = compute_collect_status({"price": "1706", "price_status": "ok", "images": ["a"],
                                "description": "x" * 30, "rating": "4.5", "review_count": 10})
    assert r["status"] == "성공" and r["filled"] == r["total"]   # 옵션 없음(단일) 분모 제외 → 만점
    opt = [f for f in r["fields"] if f["key"] == "options"][0]
    assert opt["na"] is True                     # '해당 없음' 표기(수집 실패 아님)


def test_zero_reviews_counts_as_present_full_score():
    # review_count=0 = '리뷰 0개' 정보 확보 → present(만점, 부분 아님).
    r = compute_collect_status({"price": "1706", "price_status": "ok", "images": ["a"],
                                "description": "x" * 30, "review_count": 0})
    assert r["status"] == "성공" and r["filled"] == r["total"]


def test_confirmed_none_reviews_excluded_from_denominator():
    # 리뷰 섹션 없음 확인(reviews_none) + 옵션 없음(단일) → 둘 다 분모 제외 → 3/3.
    r = compute_collect_status({"price": "1706", "price_status": "ok", "images": ["a"],
                                "description": "x" * 30, "reviews_none": True})
    assert r["status"] == "성공" and r["total"] == 3
    rev = [f for f in r["fields"] if f["key"] == "reviews"][0]
    assert rev["na"] is True


def test_real_extraction_failure_is_not_na():
    r = compute_collect_status({"price": "", "images": []})
    assert r["status"] == "실패"                  # 핵심 미확보 = 수집 실패(없음확인 아님)


def test_missing_detail_is_partial_not_na():
    r = compute_collect_status({"price": "1706", "price_status": "ok", "images": ["a"],
                                "options": [{"name": "색상", "values": ["A"]}]})
    assert r["status"] == "부분"                  # 상세 누락은 수집 실패지 없음확인 아님


# ── item5: 필드별 상태 저장 + 목록 뱃지 소거(소스 계약) ────────────────
def test_bulk_translate_stores_field_flags_and_clears_error(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    monkeypatch.setattr(V, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    iid = ch.append(source="extension", url="https://item.rakuten.co.jp/x/9/", title="TSUMUGI 紬",
                    price="1706", currency="JPY", seller_id="u1",
                    extra={"translate_error": "옛 실패", "options": [{"name": "カラー", "values": ["ブラウン"]}]})

    class _T:
        def translate_product(self, s):
            return {"title_ko": "쓰무기", "description_ko": "상세", "provider": "papago",
                    "detected_lang": "ja", "attempts": [{"provider": "papago", "ok": True}]}
        def translate_options(self, opts):
            return {"options": [{"name": "カラー", "name_ko": "컬러", "values": ["ブラウン"], "values_ko": ["브라운"]}],
                    "provider": "papago", "translated": True}
    import src.seller_console.ai.translator as _tr
    monkeypatch.setattr(_tr, "AITranslator", lambda: _T())

    from src.order_webhook import app
    with app.test_client() as c:
        r = c.post("/seller/collect/bulk-translate", json={"item_ids": [iid]})
        j = r.get_json()
    assert j["results"][0]["title_ok"] is True
    ex = json.loads(ch.get(iid, seller_id="u1")["extra_json"])
    assert "translate_error" not in ex                        # 잔존 소거
    assert ex["title_translated"] is True and ex["desc_translated"] is True
    assert ex["translation_lang"] == "ja"
    assert ex["options"][0]["values_ko"] == ["브라운"]         # 옵션값 번역 저장(원문 보존)


def test_list_js_removes_stale_badge_on_success():
    t = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    assert "kgp-tr-badge" in t and "querySelectorAll('.kgp-tr-badge')" in t   # 성공 시 뱃지 DOM 제거
    rows = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert rows.count("kgp-tr-badge") >= 3                     # 세 뱃지에 클래스 부여
