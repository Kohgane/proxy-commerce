"""T1/T2(오너 2026-09-30-H) — 번역 정리(ko_polish) · 옵션 값 해석.

캡처 좌표: VRSUK Eames 의자(ztb.tmall, 6995 CNY, SKU 16) — 「옵션 값 16개를 한국어로 옮기지 못했습니다」,
값 예 `棕红[Oilwaxed防水油蜡半皮]带踏 海外特供`. 상품명 번역본 끝 「재고 있음」(现货).

  ① 16값이 규칙만으로 한국어가 되고(한자 0), 서로 다르고, 쿠팡 28자 안(소재부터 축약)
  ② 쿠팡 SKU 계획에서 「옵션 값 16개를 옮기지 못했습니다」 보류가 사라진다 — 값마다 「확인」 배지
  ③ 번역 **전** 판촉어·가격 삭제, **후** 판촉 직역(재고 있음·해외 특공…) 삭제 + 직역 바로잡기
  ④ 표시광고 위험 문구(할인율·기간·쿠폰·1위)는 **등록을 막는다** — 사전검증과 전송 둘 다
  ⑤ translate_options: 앞 40개 제한 폐지·작은 묶음·묶음 단위 실패 격리 · 워커도 옵션을 번역한다
  ⑥ 규칙표는 관리자 화면에서 재배포 없이 바뀐다
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.collectors import ko_polish as kp

FIX = json.loads(Path("tests/fixtures/ko_polish/recent48_2026-09-30.json").read_text(encoding="utf-8"))
VRSUK = FIX["vrsuk_values"]


@pytest.fixture(autouse=True)
def _fresh_rules():
    from src.db import image_translate_queue_pg as st
    if hasattr(st, "reset_for_tests"):
        st.reset_for_tests()
    kp.reset_cache()
    yield
    kp.reset_cache()


def test_vrsuk_16_values_become_korean_unique_and_fit_coupang():
    outs = []
    for v in VRSUK:
        r = kp.option_value(v)
        assert r["left"] == "" and r["value"], (v, r["draft"])
        s = kp.shorten(r["value"])
        assert len(s) <= kp.MAX_OPTION_VALUE and not kp.has_han(s) and "발받침 포함" in s
        assert "해외" not in s and "特供" not in s
        outs.append(s)
    assert len(set(outs)) == 16
    assert outs[0] == "브라운레드 오일왁스 반가죽 / 발받침 포함"            # 조각별 치환 + 소재 축약


def test_coupang_sku_plan_no_longer_holds_the_16_values():
    from src.uploaders import coupang_options as O
    from tests.test_f51_coupang_multi_sku import META
    skus = [{"spec": [v], "sku_id": f"s{i}", "price": "6995.00", "currency": "CNY", "stock": 5,
             "sell_price_krw": 1500000} for i, v in enumerate(VRSUK)]
    product = {"title": "VRSUK 의자", "price": 6995, "currency": "CNY", "sku": "4ebaf1b8", "origin": "중국",
               "options": [{"name": "颜色分类", "name_ko": "색상", "values": list(VRSUK)}], "skus": skus}
    plan = O.plan_for(META["attributes"], product)
    assert plan["multi"] and len(plan["items"]) == 16
    assert not any("한국어로 옮기지 못했습니다" in h or "미해석" in h for h in plan["holds"]), plan["holds"]
    assert all(i["confirm"] for i in plan["items"])                       # 「번역기 값 — 확인」 배지
    assert len({i["label"] for i in plan["items"]}) == 16
    assert all(r["how"] == "polish" for i in plan["items"] for r in i["resolved"])


def test_title_polish_before_and_after_translation():
    assert kp.strip_cn("VRSUK{商务系列}简约伊姆斯躺椅油蜡皮Eames办公旋转升降现货单椅").endswith("升降 单椅")
    ko = "VRSUK{비즈니스 시리즈} 심플 이임스 리클라이너 오일 왁스 가죽 Eames 사무용 회전 승강 단일 의자 재고 있음"
    out = kp.polish_ko(ko)
    # T3(오너 2026-10-02): Eames(임스)는 가구 레플리카 상표 — 상품명에서 지우고 등록은 「상표 위험」으로 보류.
    assert "재고 있음" not in out and out.endswith("1인 의자") and "임스" not in out and "Eames" not in out
    # T2(오너 2026-10-02): 「게으른 아가씨」도 빈백 소파로 — 같은 말이 두 번 생기면 하나만.
    assert kp.polish_ko("게으른 아가씨 인기템, 게으른 사람들을 위한 소파") == "빈백 소파"
    assert kp.polish_ko("수행 방패(SPORTLINK)는 애플 워치 충전 거치대").startswith("SPORTLINK")


def test_share_and_f53_titles_are_polished():
    from src.collectors.share_text import finalize_title
    assert "재고 있음" not in finalize_title("심플 리클라이너 의자 재고 있음")


def test_ad_claim_phrases_block_prevalidate_and_dispatch(monkeypatch):
    t = FIX["vrsuk_image0"]["target_text"]
    hits = kp.ban_hits(t)
    assert "55% 할인" in hits and "88VIP" in hits
    from src.seller_console.upload_dispatcher import UploadDispatcher
    d = UploadDispatcher()
    prod = {"title": "의자 55% 할인 9.28-10.05", "coupang_name": "임스 라운지 의자 최저가", "price": 100, "currency": "CNY"}
    r = d._prevalidate_market(prod, "coupang")
    assert not r.ok and r.error_code == "ad_claim_risk" and any("최저가" in x for x in r.details)
    called = []
    monkeypatch.setattr(d, "_upload_to_market", lambda p, m: called.append(m))
    res = d.dispatch(prod, ["coupang"])
    assert res.failed == 1 and not called and res.results[0].error_code == "ad_claim_risk"
    ok = d._ad_claim_hits({"title": "임스 라운지 의자 오일왁스 가죽"}, "coupang")
    assert ok == []                                                        # 평범한 이름은 안 막는다


def test_translate_options_no_40_cap_and_batch_isolation(monkeypatch):
    from src.seller_console.ai import translator as T
    calls = []

    def fake(self, p):
        lines = p["description"].split("\n")
        calls.append(len(lines))
        if len(calls) == 2:                                                # 두 번째 묶음만 줄 수가 어긋남
            return {"provider": "papago", "description_ko": "하나뿐"}
        return {"provider": "papago", "description_ko": "\n".join(f"값{len(calls)}-{i}" for i in range(len(lines)))}

    monkeypatch.setattr(T.AITranslator, "translate_product", fake)
    vals = [f"莫奈{i:02d}号溜溜鸭" for i in range(45)]                       # 규칙표에 없는 말 45개
    out = T.AITranslator().translate_options([{"name": "颜色分类", "values": vals}])
    ko = out["options"][0]["values_ko"]
    assert out["options"][0]["name_ko"] == "색상"                           # 규칙으로(번역기 안 부름)
    assert len(calls) >= 3 and max(calls) <= 15                            # 작은 묶음
    assert ko[0].startswith("값1-") and ko[-1].startswith("값")            # 40개 넘어도 끝까지
    second = ko[15:30]
    assert all(v in vals for v in second)                                  # 어긋난 묶음만 원문(가짜 번역 0)
    assert out["translated"] is True


def test_worker_translates_options_too():
    """워커가 옵션 번역을 **부른다**(전엔 버튼 경로만) — 문자열이 아니라 호출 구조로 잰다(메타 계약)."""
    from tests._ast_probe import calls_in
    from src.seller_console import translate_worker as W
    assert "translate_options" in calls_in(W.drain_once)


def test_rules_override_without_redeploy():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/seller/admin/ko-polish").get_data(as_text=True)
    assert 'data-role="kp-hash"' in h and "海外特供" in h
    r = dict(kp.rules())
    r["delete_ko"] = list(r["delete_ko"]) + ["테스트삭제어"]
    c.post("/seller/admin/ko-polish", data={"rules": json.dumps(r, ensure_ascii=False)})
    assert kp.polish_ko("의자 테스트삭제어") == "의자"
    t = c.post("/seller/admin/ko-polish", data={"action": "try", "sample": VRSUK[0]}).get_data(as_text=True)
    assert "브라운레드 오일왁스 반가죽 / 발받침 포함" in t
    bad = c.post("/seller/admin/ko-polish", data={"rules": '{"ban_ko": ["("]}'}).get_data(as_text=True)
    assert 'data-role="kp-err"' in bad
    c.post("/seller/admin/ko-polish", data={"action": "reset"})
    assert kp.polish_ko("의자 테스트삭제어") == "의자 테스트삭제어"
    seller = app.test_client()
    with seller.session_transaction() as s:
        s["user_id"], s["user_role"] = "u1", "seller"
    assert seller.get("/seller/admin/ko-polish").status_code == 403


def test_han_regex_does_not_eat_hangul():
    """호환 한자(U+F900)를 글자로 적으면 정규화돼 범위가 한글까지 먹는다 — 실제로 났던 결함."""
    assert not kp.has_han("브라운레드 오일왁스") and kp.has_han("棕红")
