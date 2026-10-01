"""J(오너 2026-09-30-J) — 수집하면 자동 번역 · 브랜드 병음 · 실측 화면 · 「예상 모습」 카운트 · 화면 A 검수.

  ① 브랜드: 제목 맨 앞 한자 2~4자 == 브랜드·가게 필드(「旗舰店」 뗌) → 번역기엔 빼고 보내고 병음 대문자를 앞에 + 배지
     필드가 비었거나 일치하지 않으면 평소대로 번역(제목만 보고 브랜드라 짐작하지 않음)
  ② 수집(확장) 순간 정리 규칙 단계가 돌아 values_ko가 저장되고, 남은 외국어 값만 큐에 들어간다
  ③ 큐: 일일 상한(값 수, KST) 안에서만 보내고 나머지는 대기 · 실패 20회 자동 일시정지 → 「재개」
  ④ 백필은 관리자만 · 규칙 즉시 + 큐 · 상품명 정리 전 값을 남긴다(전후 표) — 번역기는 버튼이 부른 워커만
  ⑤ 실측 화면(규칙/번역기/잔존 + 표본 + 상품명 전후) · 「예상 모습」 24h 비율(메타 빈 응답도 예상 모습)
  ⑥ 이미지 점검에 글자 모양 열 · 화면 A 미확인 iOS 이름엔 「(캡처 참고)」 · 결과 화면 붙여넣기 거부 자리
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.collectors import ko_polish as kp

FIX = json.loads(Path("tests/fixtures/ko_polish/recent48_2026-09-30.json").read_text(encoding="utf-8"))
VRSUK = FIX["vrsuk_values"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.db import option_translate_queue_pg as oq
    st.reset_for_tests()
    oq.reset_for_tests()
    kp.reset_cache()
    yield
    kp.reset_cache()


def _item(uid="u-j", **extra):
    from src.seller_console import collect_history_store as S
    ex = {"title": "懒小姐懒人沙发现货", "title_en": "懒小姐懒人沙发现货", "price": "199", "currency": "CNY",
          "options": [{"name": "颜色分类", "values": VRSUK[:2] + ["莫奈色溜溜鸭"]}]}
    ex.update(extra)
    return S.append(source="extension", url="https://item.taobao.com/item.htm?id=77", title=ex["title"],
                    price="199", currency="CNY", extra=ex, seller_id=uid)


def _extra(iid, uid="u-j"):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_ids={uid})["extra_json"])


# ① 브랜드 ─────────────────────────────────────────────────────────────────

def test_brand_rule_needs_field_match():
    info = kp.brand_prefix("懒小姐懒人沙发可躺", {"shop_name": "懒小姐旗舰店"})
    assert info and info["latin"] == "LANXIAOJIE" and info["rest"] == "懒人沙发可躺" and info["field"] == "shop_name"
    assert kp.brand_prefix("懒小姐懒人沙发", {"brand": ""}) is None                 # 필드 없음 → 판정 안 함
    assert kp.brand_prefix("懒小姐懒人沙发", {"brand": "力士"}) is None              # 불일치 → 번역
    assert kp.brand_prefix("懒小姐懒人沙发", {"brand": "懒小姐懒人沙发家居"}) is None  # 5자↑ 아님
    assert kp.attach_brand("빈백 소파", info) == "LANXIAOJIE 빈백 소파"


def test_collect_translation_keeps_brand_out_of_translator(monkeypatch):
    from src.api import extension_api as ext
    from src.seller_console.ai import translator as T
    sent = []

    def fake(self, p):
        sent.append(p["title"])
        return {"provider": "papago", "title_ko": "게으른 사람 소파", "description_ko": ""}

    monkeypatch.setattr(T.AITranslator, "translate_product", fake)
    out = ext._translate_payload({"title": "懒小姐懒人沙发现货", "description": "", "brand": "懒小姐"})
    assert sent == ["懒人沙发"]                                                     # 브랜드·판촉어 뺀 원문
    assert out["title_ko"] == "LANXIAOJIE 빈백 소파" and out["brand_romanized"]["latin"] == "LANXIAOJIE"


def test_brand_badge_on_drawer_and_phone_card():
    from src.order_webhook import app
    iid = _item(brand_romanized={"han": "懒小姐", "latin": "LANXIAOJIE", "field": "shop_name"})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-j"
    d = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    assert 'data-role="brand-romanized"' in d and "브랜드 표기 — 확인" in d and "LANXIAOJIE" in d
    m = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-brand-romanized"' in m
    from src.seller_console.views import _coupang_name_input
    from src.uploaders import coupang_title as ct
    ex = {"title_ko": "LANXIAOJIE 빈백 소파", "brand_romanized": {"latin": "LANXIAOJIE"}}
    assert ct.build_name(_coupang_name_input({}, ex), "front")["name"].startswith("LANXIAOJIE")  # 쿠팡명에서 안 빠짐


# ② 수집 순간 규칙 단계 + 큐 ───────────────────────────────────────────────

def test_rule_pass_fills_values_and_leaves_only_foreign():
    from src.services import option_translate_auto as oa
    ex = {"title": "椅", "options": [{"name": "颜色分类", "values": VRSUK[:2] + ["莫奈色溜溜鸭", "Black"]}]}
    st = oa.rule_pass(ex)
    o = ex["options"][0]
    assert st["changed"] and o["name_ko"] == "색상"
    assert o["values_ko"][0] == kp.option_value(VRSUK[0])["value"] and o["values_ko"][3] == "Black"
    assert st["pending"] == ["莫奈色溜溜鸭"]                                      # 남은 외국어만
    assert o["values_ko"][2] == "莫奈色溜溜鸭"                                      # 못 옮긴 자리는 원문(가짜 0)
    ex["options"][0]["values_ko"][2] = "모네 컬러"                                   # 오너가 고친 값은 안 덮음
    assert oa.rule_pass(ex)["pending"] == [] and ex["options"][0]["values_ko"][2] == "모네 컬러"


def test_extension_collect_runs_rules_then_queues(monkeypatch):
    from src.api import extension_api as ext
    from src.db import option_translate_queue_pg as oq
    from src.order_webhook import app
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-j", "scopes": ["collect.write"]})
    r = app.test_client().post("/api/v1/collect/extension", json={
        "url": "https://item.taobao.com/item.htm?id=4242", "title": "VRSUK躺椅", "price": "6995", "currency": "CNY",
        "translate": False, "images": [], "options": [{"name": "颜色分类", "values": VRSUK[:2] + ["莫奈色溜溜鸭"]}]})
    iid = r.get_json()["item_id"]
    assert r.get_json()["ok"]
    # translate:false면 규칙 단계도 큐도 안 돈다(오너가 끈 번역)
    assert "values_ko" not in _extra(iid)["options"][0] and oq.counts()["queued"] == 0
    r = app.test_client().post("/api/v1/collect/extension", json={
        "url": "https://item.taobao.com/item.htm?id=4343", "title": "VRSUK躺椅", "price": "6995", "currency": "CNY",
        "images": [], "options": [{"name": "颜色分类", "values": VRSUK[:2] + ["莫奈色溜溜鸭"]}]})
    iid = r.get_json()["item_id"]
    o = _extra(iid)["options"][0]
    assert o["values_ko"][0] == kp.option_value(VRSUK[0])["value"]               # 저장 전에 규칙이 돌았다
    assert oq.counts()["queued"] == 1                                             # 남은 값 → 큐(워커는 테스트에서 끔)
    from tests._ast_probe import calls_in
    assert "_auto_translate_options" in calls_in(ext.collect_enrich)              # 보강 완료 자리도 같은 입구


# ③ 큐: 상한·일시정지 ─────────────────────────────────────────────────────

def _fake_translator(monkeypatch, *, fail=False):
    from src.seller_console.ai import translator as T
    calls = {"title": 0, "values": 0}

    def tp(self, p):
        if fail:
            raise RuntimeError("quota")
        calls["title"] += 1
        return {"provider": "papago", "title_ko": "게으른 사람 소파", "description_ko": ""}

    def to(self, opts):
        if fail:
            raise RuntimeError("quota")
        vals = opts[0]["values"]
        calls["values"] += len(vals)
        return {"options": [{"name": "", "values": vals, "values_ko": [f"번역{i}" for i in range(len(vals))]}],
                "provider": "papago", "translated": True}

    monkeypatch.setattr(T.AITranslator, "translate_product", tp)
    monkeypatch.setattr(T.AITranslator, "translate_options", to)
    return calls


def test_daily_cap_counts_values_and_waits_until_kst_midnight(monkeypatch):
    from src.services import option_translate_auto as oa
    calls = _fake_translator(monkeypatch)
    monkeypatch.setenv("OPTION_TRANSLATE_DAILY_CAP", "3")
    vals = [f"莫奈{i}号溜溜鸭" for i in range(5)]
    iid = _item(options=[{"name": "颜色分类", "values": vals}], title_ko="")
    assert oa.enqueue_if_pending("u-j", iid, _extra(iid), kick_worker=False)
    oa.run_until_idle()
    s = oa.status()
    assert s["today"] == 3 and s["cap"] == 3 and s["queued"] == 1 and s["waiting_cap"]
    assert calls["title"] == 1 and calls["values"] == 2                           # 상품명 1 + 값 2 = 3
    ex = _extra(iid)
    assert ex["title_ko"] == "빈백 소파" and ex["options"][0]["values_ko"][:2] == ["번역0", "번역1"]
    # 다음 날(KST) — 남은 3개가 간다
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(oa, "_day_key", lambda now=None: "optko_auto:day:" +
                        oa.kst_day(datetime.now(timezone.utc) + timedelta(days=1)))
    oa.run_until_idle()
    assert not any(kp.has_han(v) for v in _extra(iid)["options"][0]["values_ko"]) and oa.status()["queued"] == 0


def test_twenty_failures_pause_until_resume(monkeypatch):
    from src.services import option_translate_auto as oa
    _fake_translator(monkeypatch, fail=True)
    monkeypatch.setattr(oa, "FAIL_PAUSE_AT", 2)
    for i in range(3):
        iid = _item(options=[{"name": "颜色分类", "values": [f"莫奈{i}号溜溜鸭"]}], title_ko="빈백")
        oa.enqueue_if_pending("u-j", iid, _extra(iid), kick_worker=False)
    oa.run_until_idle()
    s = oa.status()
    assert s["paused"] and "재개" in s["pause_reason"] and s["queued"] == 1        # 2회 실패 뒤 멈춤, 1건 대기
    _fake_translator(monkeypatch)
    monkeypatch.setenv("OPTION_TRANSLATE_AUTO_SYNC", "1")
    oa.resume()                                                                  # 재개 → 워커가 이어서
    assert not oa.status()["paused"] and oa.status()["queued"] == 0


# ④ 백필(관리자만) ─────────────────────────────────────────────────────────

def test_backfill_is_admin_only_and_records_title_before(monkeypatch):
    from src.order_webhook import app
    from src.db import option_translate_queue_pg as oq
    from src.seller_console.ai import translator as T
    monkeypatch.setattr(T.AITranslator, "translate_product",
                        lambda self, p: (_ for _ in ()).throw(AssertionError("백필이 직접 번역하면 안 된다")))
    iid = _item(uid="owner", title_ko="임스 라운지 의자 재고 있음")
    seller = app.test_client()
    with seller.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "seller"
    assert seller.post("/seller/collect/translate-audit/backfill", json={}).status_code == 403
    admin = app.test_client()
    with admin.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    d = admin.post("/seller/collect/translate-audit/backfill", json={}).get_json()
    assert d["ok"] and d["titles"] == 1 and d["queued"] == 1 and oq.counts()["queued"] == 1
    ex = _extra(iid, "owner")
    assert ex["title_polish_before"] == "임스 라운지 의자 재고 있음" and ex["title_ko"] == "임스 라운지 의자"
    assert ex["options"][0]["values_ko"][0] == kp.option_value(VRSUK[0])["value"]


# ⑤ 실측 화면 · 예상 모습 ──────────────────────────────────────────────────

def test_translate_audit_counts_rule_translator_left(monkeypatch):
    from src.order_webhook import app
    _item(uid="u-a", title_ko="LANXIAOJIE 빈백 소파", title_polish_before="LANXIAOJIE 빈백 소파 재고 있음",
          options=[{"name": "颜色分类", "values": [VRSUK[0], "莫奈色溜溜鸭", "梵高星空款"],
                    "values_ko": ["", "모네 컬러", "梵高星空款"]}])
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-a"
    d = c.get("/seller/collect/translate-audit?format=json").get_json()
    a = d["audit"]
    assert a["counts"] == {"rule": 1, "translator": 1, "left": 1} and a["values"] == 3
    assert a["translator_samples"] == [{"src": "莫奈色溜溜鸭", "ko": "모네 컬러"}]
    assert a["titles"][0]["before"].endswith("재고 있음") and a["titles_promo_left"] == 0
    h = c.get("/seller/collect/translate-audit").get_data(as_text=True)
    assert 'data-role="ta-samples"' in h and 'data-role="ta-titles"' in h and 'id="taBackfill"' not in h  # 셀러엔 버튼 없음


def test_preview_estimated_counts_meta_missing(monkeypatch):
    from src.channel_sync import coupang_uploader as cu
    from src.order_webhook import app
    from src.services import preview_stats
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-j"
    iid = _item()
    monkeypatch.setattr(cu, "option_form", lambda p: {"ok": True, "category": "1", "meta_ok": False, "items": [],
                                                      "holds": [], "notes": []})
    d = c.get(f"/seller/m/item/{iid}/coupang-preview").get_json()
    assert d["estimated"] and any("예상 모습" in n for n in d["notes"])              # 메타 빈 응답도 예상 모습
    monkeypatch.setattr(cu, "option_form", lambda p: {"ok": True, "category": "1", "meta_ok": True, "items": [],
                                                      "holds": [], "notes": []})
    assert not c.get(f"/seller/m/item/{iid}/coupang-preview").get_json()["estimated"]
    w = preview_stats.window(24)
    assert w["total"] == 2 and w["estimated"] == 1 and w["ratio"] == 0.5 and w["over"]
    assert w["reasons"] == {"카테고리 메타 빈 응답": 1}
    assert w["started_at"].startswith("20")                                     # K-3: 카운터 시작 시각이 남는다


# ⑥ 이미지 글자 모양 · 화면 A ─────────────────────────────────────────────

def test_image_audit_shows_geometry_columns():
    from src.order_webhook import app
    e = {"idx": 0, "status": "done", "use": True, "text_area": 0.31, "band": "top", "lines": 12,
         "source_text": "国庆狂欢 88VIP", "target_text": "국경절"}
    _item(uid="u-g", images=["https://img/1.jpg", "https://img/2.jpg"], images_ko=[e])
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-g"
    h = c.get("/seller/collect/image-audit").get_data(as_text=True)
    assert 'data-role="geo-table"' in h and "31.0%" in h and ">위<" in h and "88VIP" in h
    assert "기록 1장 / 기준 제안까지 50장" in h and 'data-role="audit-translate-link"' in h


def test_screen_a_marks_unverified_ios_labels_and_result_has_denied_slot(monkeypatch):
    from src.order_webhook import app
    h = app.test_client().get("/seller/guide/iphone").get_data(as_text=True)
    a = h[h.index('data-role="step-a1"'):h.index('data-role="install-trouble"')]
    assert a.count('data-role="unverified"') == 1                                # 홈 화면 올리기만(「단축어 추가」는 Q에서 오너 실측 확정)
    assert "「단축어」 앱을 열고" in a
    u = app.test_client().get("/seller/guide/iphone/use").get_data(as_text=True)
    assert u.count('data-role="unverified"') == 1                                # 공유 목록 모양
    import src.seller_console.views as V
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-j"
    r = c.get("/seller/collect/share?v=2&src=clip&text=&clip=").get_data(as_text=True)
    # O(2026-10-01) 실측: 붙여넣기 허용 창은 안 뜬다 → 그 자리는 빼고 「처리 단계」로 어디서 멈췄는지 보인다.
    assert 'data-role="share-paste-denied"' not in r and 'data-role="share-stages"' in r
    assert V is not None
