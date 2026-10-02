"""T(오너 2026-10-02) — 번역 점검(translate-audit 16:33: 규칙 157 · 번역기 46 · 남음 362(64%) · 고유 565) 후속.

표본은 운영 collect_history 옵션 값·상품명(읽기 전용 실측) — `tests/fixtures/ko_polish/t1_samples_2026-10-02.json`.

  T1 이모지·장식 기호 제거 · 판촉·보증·주장 삭제 · 용어 치환 · 「44cm高棕色」 높이/색 분리 · 용도 꼬리 · 28자 축약은
     판촉 → 용도 꼬리 → 기능 나열 뒤부터(색상 조각은 남김), 그래도 넘으면 **자르지 않고 미해석**
  T2 상품명 재정리(게으른 아가씨→빈백 소파 · 티몰 인기 상품 · 라오치엔펑→올드머니 룩 · 미니멀 · ins풍) ·
     「판촉 직역 남음」 판정 = 삭제표 그 자체
  T3 원문에 없는 고유명(미야케 아키라) 결과 폐기 · 三宅→플리츠 · 상표 호환 접미 · 가구 레플리카 삭제+보류 ·
     临期/过期/清仓/尾货 → 「유통기한 임박·떨이 소싱 — 등록 차단」
  T4 백필 2단계(1단계 비용 0 — 번역기 0 / 2단계 버튼 — 큐) · 「어색」 표본
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.collectors import ko_polish as kp

FIX = json.loads(Path("tests/fixtures/ko_polish/t1_samples_2026-10-02.json").read_text(encoding="utf-8"))["samples"]


@pytest.fixture(autouse=True)
def _fresh():
    from src.db import image_translate_queue_pg as st
    from src.db import option_translate_queue_pg as oq
    st.reset_for_tests()
    oq.reset_for_tests()                 # Papago 일 상한 카운터 — 앞 계약이 소진 표시를 남겼어도 깨끗이
    kp.reset_cache()
    yield
    kp.reset_cache()
    oq.reset_for_tests()


# ── T1 ────────────────────────────────────────────────────────────────────────

def test_t1_twenty_owner_samples():
    from src.uploaders.coupang_options import resolve_option_value
    out = [resolve_option_value(s["src"], values_ko=s["values_ko"]) for s in FIX]
    solved = [r["value"] for r in out if r["value"]]
    assert len(solved) >= 17, [(s["src"], r["why"]) for s, r in zip(FIX, out) if not r["value"]]   # 전: 5/20
    assert all(len(v) <= kp.MAX_OPTION_VALUE for v in solved)
    assert not any(ch in v for v in solved for ch in "✅⚡🌟⭐ꔛ【】")
    by = {s["src"]: r["value"] for s, r in zip(FIX, out)}
    assert by["30cm高棕色 【玄关换鞋】"] == "높이 30cm 브라운 / 현관용"
    assert by["44cm高红色 【客厅餐椅】"] == "높이 44cm 레드 / 식탁용"
    assert by["黑色|整装发货·九宫格大包围·静音万向轮·环保无味【高弹坐感·护腰靠背】"] == "블랙 / 저소음 바퀴 / 고탄성 시트 · 허리 받침"
    pw = by["✅新品PD65W快充+过载开关✅双层粘夹黑色1.8米【6五孔+1A2C】"]
    assert pw.startswith("PD65W 고속충전") and "블랙" in pw and "새 제품" not in pw and "신품" not in pw
    promo = resolve_option_value("【超长3年质保】", values_ko="[최대 3년 품질 보증]")
    # U4(오너 2026-10-02): 보증 문구 SKU는 「옵션 아님 — 제외」(T1의 「판촉·보증 문구뿐」 미해석보다 먼저 가른다)
    assert promo["value"] == "" and promo["how"] == "non_option" and "옵션 아님" in promo["why"]


def test_t1_never_cuts_and_drops_tail_first():
    long_v = "아주 긴 옵션 값 이름 하나 둘 셋 넷 다섯 여섯 일곱 여덟 아홉"     # 조각 경계 없음 — 줄일 수 없다(U3: 30자 넘게)
    assert kp.shorten(long_v) == long_v and not kp.fits(long_v)        # 자르지 않는다 → 호출부가 미해석
    assert kp.shorten("높이 44cm 브라운 비즈니스 스타일 의자 / 화장대용 쿠션 포함 세트") .endswith("세트") is False
    assert "화장대용" not in kp.shorten("높이 52cm 블랙 고급 원목 스툴 화장대용 쿠션 포함 세트")   # U3: 30자 넘는 모양


# ── T2 ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ko,want", [
    ("게으른 아가씨 블랙 가죽 1인용 게으른 소파 의자, 모던 심플 거실 휴식 의자", "빈백 소파 블랙 가죽 1인용 의자, 모던 심플 거실 휴식 의자"),
    ("티몰 인기 상품】너무 예쁜 세트 원피스", "너무 예쁜 세트 원피스"),
    ("라오치엔펑 뮬러 남성용 가을용 외출용 슬리퍼", "올드머니 룩 뮬러 남성용 가을용 외출용 슬리퍼"),
    ("의식적인 미니멀리즘 스타일의 편안한 1인용 소파", "미니멀 편안한 1인용 소파"),
    ("콩창 무릎 소파, ins풍 가죽 의자", "콩창 빈백 소파, 가죽 의자"),
    ("수형 방패 애플 워치 거치대 재고 있음", "애플워치 호환 거치대"),
])
def test_t2_title_repolish(ko, want):
    assert kp.polish_ko(ko) == want


def test_t2_promo_counter_uses_the_deletion_table():
    from src.services import option_translate_auto as optauto
    ko = "✅신품 인기템 2단 클램프 무료 배송"
    left = kp.promo_left(ko)
    assert len(left) >= 3                                               # 기호·신품·인기템·무료 배송 — 예전 표(delete_ko 낱말)는 2
    row = {"id": "x", "extra_json": json.dumps({"title": "插座", "title_ko": ko})}
    assert optauto.audit([row])["titles"][0]["promo_left"] == left


# ── T3 ────────────────────────────────────────────────────────────────────────

def test_t3_invented_name_is_discarded_for_the_next_engine(monkeypatch):
    import requests
    from src.seller_console.ai.translator import AITranslator
    for k in ("NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET", "DEEPL_API_KEY"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("TRANSLATE_CHAIN_ORDER", "papago,deepl")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)   # CI는 dry-run(=stub) — 체인 자체를 재는 계약이라 끈다

    class R:
        def __init__(self, p): self.p = p
        status_code = 200
        text = ""
        def raise_for_status(self): pass
        def json(self): return self.p
    monkeypatch.setattr(requests, "post", lambda url, **k: R({"message": {"result": {"translatedText": "미야케 아키라의 미니멀 세트"}}})
                        if "papago" in url else R({"translations": [{"text": "플리츠 미니멀 세트"}, {"text": ""}]}))
    res = AITranslator().translate_product({"title": "三宅艺创极简风套装女", "description": ""})
    assert res["provider"] == "deepl" and res["title_ko"] == "플리츠 미니멀 세트"
    assert "원문에 없는 고유명(아키라" in res["attempts"][0]["error"]
    # 다 같은 이름을 만들면 정리 규칙(이름 → 플리츠)을 건 값 + 경고
    monkeypatch.setattr(requests, "post", lambda url, **k: R({"message": {"result": {"translatedText": "미야케 아키라의 미니멀 세트"}}})
                        if "papago" in url else R({"translations": [{"text": "미야케 아키라 세트"}, {"text": ""}]}))
    res2 = AITranslator().translate_product({"title": "三宅艺创极简风套装女", "description": ""})
    assert "아키라" not in res2["title_ko"] and "플리츠" in res2["title_ko"] and res2.get("translate_warn")


def test_t3_trademarks_compat_and_replica():
    assert kp.polish_ko("3-in-1 magsafe 무선 충전 거치대") == "3-in-1 맥세이프 호환 무선 충전 거치대"
    assert kp.polish_ko("Airpods 이어폰 거치대, 에어팟 수납") == "에어팟 호환 이어폰 거치대, 수납"
    assert kp.polish_ko("VRSUK 심플 Eames 라운지 의자") == "VRSUK 심플 라운지 의자"
    assert kp.replica_hits("简约伊姆斯躺椅油蜡皮Eames") == ["임스"]


def test_t3_risk_holds_in_prevalidation():
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    base = {"title": "라운지 의자", "price": "6995", "images": ["/seller/static/icon-512.png"]}
    h = UploadDispatcher.readiness_holds(dict(base, title_src="VRSUK简约伊姆斯躺椅Eames"), "coupang")
    assert readiness_message(h) == "사전검증 — 보류: 상표 위험(임스) → 상표를 뺀 상품으로 다시 확인 후"
    h2 = UploadDispatcher.readiness_holds(dict(base, title_src="【临期处理】酒店线洗手液"), "coupang")
    assert readiness_message(h2) == "사전검증 — 보류: 유통기한 임박·떨이 소싱 — 등록 차단"
    h3 = UploadDispatcher.readiness_holds(dict(base, options=[{"name": "香味", "values": ["洗发水 27年2月过期"]}]), "shopify")
    assert any(x["fix"] == "block" for x in h3)                       # 옵션 값의 过期도 본다 · 마켓 무관


def test_t3_phone_card_shows_the_risk():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1842648f", seller_id="u-t3", title="핸드워시",
                   price="39", currency="CNY", extra={"title": "【临期处理】酒店线帕尔玛之水洗手液", "title_ko": "임박 처리】호텔 라인 핸드워시",
                                                     "price": "39", "currency": "CNY", "images": []})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-t3"
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-risk"' in h and "유통기한 임박·떨이 소싱 — 등록 차단" in h


# ── T4 ────────────────────────────────────────────────────────────────────────

def test_t4_audit_lists_awkward_translator_values_and_two_buttons():
    from src.services import option_translate_auto as optauto
    # U3(오너 2026-10-02): 판정은 **등록이 쓰는 해석 체인 그대로**(정리 → 축약 → 30자).
    #   판촉·기호가 붙었던 번역기 값은 정리하면 깨끗이 나가므로(「모네 컬러」) 어색이 아니다 — 줄여도 30자를 넘는 것만 남는다.
    vals, kos = ["莫奈色梵高星空款", "梵高向日葵莫奈睡莲款式超长"], ["✅ 모네 컬러 신품 인기템", "반 고흐 해바라기와 모네 수련 스타일 특대형 긴 버전 모델"]
    row = {"id": "x", "extra_json": json.dumps({"options": [{"name": "颜色", "values": vals, "values_ko": kos}]})}
    got = optauto.audit([row])
    whys = {a["src"]: a for a in got["awkward_samples"]}
    assert set(whys) == {vals[1]} and whys[vals[1]]["why"] == "30자 넘음(줄여도)" and got["awkward_over"] == 1
    tpl = Path("src/seller_console/templates/translate_audit.html").read_text(encoding="utf-8")
    assert "1단계 — 규칙·재정리(비용 0)" in tpl and "2단계 — 남은 값 번역기로" in tpl and 'data-role="ta-awkward"' in tpl


def test_t4_stage1_repolishes_translated_values_without_translator(monkeypatch):
    from src.services import option_translate_auto as optauto
    ex = {"options": [{"name": "颜色", "values": [FIX[0]["src"]], "values_ko": [FIX[0]["values_ko"]]}]}
    st = optauto.rule_pass(ex)
    assert st["changed"] and "✅" not in ex["options"][0]["values_ko"][0] and "새 제품" not in ex["options"][0]["values_ko"][0]
