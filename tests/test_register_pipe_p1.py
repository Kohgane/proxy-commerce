"""tests/test_register_pipe_p1.py — 등록 파이프 P1: 소싱 URL→수집·검증→검수표(등록 없음).

순수 로직 + 라우트 접근. 수집은 주입(발명 0). 등록 절대 안 함(registered=False 불변).
"""
from __future__ import annotations

from src.pipeline import register_pipe as RP


def test_row_krw_cost_recalc_margin():
    d = {"title_ko": "원목 식탁 4인용", "currency": "KRW", "price_original": 50000, "images": ["https://i/1.jpg"]}
    r = RP.build_source_review_row(d, url="https://x/1")
    assert r["excluded"] is False and r["registered"] is False
    assert r["cost_krw"] == 50000 and r["sale_krw"] == 71900            # ÷0.618 정합(판매가 불변)
    assert r["target_margin_pct"] == 27.4                                # 목표 마진
    # P2: margin_pct = 실마진(채널 수수료 3% 반영·배송 미상=0 → 목표 근사, 근사값 아님·단일 소스).
    assert r["margin_pct"] == 27.5 and r["net_krw"] == 19743
    assert r["ship_status"] == "미검증" and r["ship_over_35pct"] is False
    assert r["image_count"] == 1 and r["thumbnail"] == "https://i/1.jpg"


def test_row_forbidden_excluded_with_reason():
    r = RP.build_source_review_row({"title_ko": "샤넬 향수 오드퍼퓸", "currency": "KRW", "price_original": 100000})
    assert r["excluded"] is True and r["forbidden"]          # 취급 제외 + 사유(조용한 탈락 금지)
    assert r["registered"] is False
    # 주입 blacklist도 반영.
    inj = RP.build_source_review_row({"title_ko": "특정금지품 XYZ", "currency": "KRW", "price_original": 5000},
                                     blacklist=["특정금지품"])
    assert inj["excluded"] is True


def test_forbidden_detail_shows_matched_token_and_span():
    # 오탐 판별용: 어느 금지 항목이 제목의 어느 부분에 걸렸는지 명시(토라스 Chanel 패턴명 전례).
    r = RP.build_source_review_row({"title_ko": "토라스 샤넬패턴 케이스", "currency": "KRW", "price_original": 20000},
                                   blacklist=["샤넬"])
    d = r["forbidden_detail"]
    assert d["kind_ko"] == "금지어 목록" and d["term"] == "샤넬"
    assert d["matched"] == "샤넬" and "⟦샤넬⟧" in d["snippet"] and "패턴" in d["snippet"]   # 걸린 위치 노출
    # 금지 카테고리도 동일 형식.
    cat = RP.build_source_review_row({"title_ko": "디올 향수 100ml", "currency": "KRW", "price_original": 50000})
    assert cat["forbidden_detail"]["kind_ko"] == "금지 카테고리" and cat["forbidden_detail"]["term"] == "향수"
    # 통과 행은 detail 없음.
    ok = RP.build_source_review_row({"title_ko": "원목 식탁", "currency": "KRW", "price_original": 30000})
    assert ok["forbidden_detail"] is None


def test_explain_forbidden_direct():
    assert RP.explain_forbidden(None, "x") is None
    e = RP.explain_forbidden("blacklist:bose", "Bose QuietComfort Headphones")
    assert e["term"] == "bose" and e["matched"] == "Bose" and "⟦Bose⟧" in e["snippet"]   # 원문 대소문자 보존


def test_row_foreign_cost_honest_when_no_fx():
    r = RP.build_source_review_row({"title_ko": "USB 허브", "currency": "USD", "price_original": 19.99})
    assert r["cost_krw"] is None and r["sale_krw"] is None        # 가짜 환산 0
    assert "환율 미상" in r["price_reason"]
    # fx 있으면 환산.
    r2 = RP.build_source_review_row({"title_ko": "USB 허브", "currency": "USD", "price_original": 20}, fx_rate=1350)
    assert r2["cost_krw"] == 27000 and r2["sale_krw"] is not None


def test_row_no_price_is_honest_missing():
    r = RP.build_source_review_row({"title_ko": "가격 없는 상품", "currency": "KRW"})
    assert r["cost_krw"] is None and r["sale_krw"] is None and "원가 미입력" in r["price_reason"]


def test_build_source_review_dedup_and_failed_separation():
    good = {"title_ko": "원목 식탁", "currency": "KRW", "price_original": 30000, "images": ["u"]}
    def _collect(url):
        if "fail" in url:
            return None
        if "boom" in url:
            raise RuntimeError("타임아웃")
        return good
    out = RP.build_source_review(["https://ok/1", "https://ok/1", "https://fail/2", "https://boom/3"],
                                 collect_fn=_collect)
    assert out["requested"] == 3                              # 중복 제거(ok/1 두 번 → 1)
    assert out["count"] == 1 and len(out["review_pass"]) == 1
    assert len(out["failed"]) == 2                            # 수집 실패 + 예외 각각 사유
    assert all(f.get("reason") for f in out["failed"])       # 조용한 탈락 금지
    assert all(r["registered"] is False for r in out["review_pass"])   # 등록 없음


def test_build_source_review_cap():
    out = RP.build_source_review([f"https://x/{i}" for i in range(60)],
                                 collect_fn=lambda u: {"title_ko": "t", "currency": "KRW", "price_original": 1000},
                                 cap=50)
    assert out["count"] == 50 and out["capped"] is True


# ── P2: 배송(ship_real) 서버화 — 플래그만(등록 차단 안 함) ─────────────────────────
def test_ship_blocked_brand_flagged_not_excluded():
    # ALPAKA/ULANZI/HydraPak = 등록 전 걸러진 전례 → 배송불가 플래그, 그러나 excluded는 False(차단 아님).
    r = RP.build_source_review_row({"title_ko": "ALPAKA Metro 백팩", "brand": "ALPAKA",
                                    "currency": "KRW", "price_original": 100000})
    assert r["ship_viable"] is False and r["ship_status"] == "배송불가"
    assert "ALPAKA" in r["ship_reason"] and r["excluded"] is False       # 플래그만(등록 차단 안 함)
    u = RP.build_source_review_row({"title_ko": "ULANZI 삼각대", "currency": "KRW", "price_original": 30000})
    assert u["ship_status"] == "배송불가"


def test_ship_check_fn_kr_marker_and_tuple_unpack():
    # 실측: 홈 HTML value="KR" 있으면 배송가능. get 튜플(status, body) 반환도 안전 언패킹(지뢰 방어).
    ok = RP.build_source_review_row({"title_ko": "니치 지갑", "currency": "KRW", "price_original": 40000},
                                    url="https://shop/x",
                                    ship_check_fn=lambda url: (200, '<option value="KR">Korea</option>'))
    assert ok["ship_viable"] is True and ok["ship_status"] == "배송가능"
    no = RP.build_source_review_row({"title_ko": "니치 지갑", "currency": "KRW", "price_original": 40000},
                                    url="https://shop/x",
                                    ship_check_fn=lambda url: '<option value="US">United States</option>')
    assert no["ship_viable"] is False and "KR 없음" in no["ship_reason"]
    err = RP.build_source_review_row({"title_ko": "니치 지갑", "currency": "KRW", "price_original": 40000},
                                     url="https://shop/x",
                                     ship_check_fn=lambda url: (_ for _ in ()).throw(RuntimeError("타임아웃")))
    assert err["ship_viable"] is None and err["ship_status"] == "미검증"   # 조회 실패 = 미검증 정직


def test_ship_default_unverified():
    r = RP.build_source_review_row({"title_ko": "일반 니치 상품", "currency": "KRW", "price_original": 40000})
    assert r["ship_viable"] is None and r["ship_status"] == "미검증"       # 실측 미조회=미검증(가짜 판정 0)


# ── P2: 마진 정밀화 — 실마진(수수료·배송비) 단일 소스, 35% 위반 플래그 ──────────────
def test_real_margin_reflects_shipping_and_35pct_flag():
    # 배송비 20,000 = 원가 50,000의 40% > 35% → 위반 플래그 + 실마진 급락(단일 소스 반영).
    r = RP.build_source_review_row({"title_ko": "부피 큰 상품", "currency": "KRW", "price_original": 50000},
                                   ship_cost_fn=lambda **k: 20000)
    assert r["ship_cost_krw"] == 20000 and r["ship_over_35pct"] is True
    assert r["margin_pct"] < 27.4 and r["net_krw"] < 19743               # 배송비가 마진을 깎음
    # 배송비 미상이면 마진 미반영(0)·정직 표기.
    r2 = RP.build_source_review_row({"title_ko": "부피 큰 상품", "currency": "KRW", "price_original": 50000})
    assert r2["ship_cost_krw"] is None and "미상" in r2["ship_cost_basis"] and r2["ship_over_35pct"] is False


def test_real_margin_single_source_matches_calc():
    # 실마진 공식 = MarginCalculator._calc_margin(단일 소스). 새 공식 정의 0 검증.
    from decimal import Decimal
    from src.seller_console.margin_calculator import MarginCalculator
    r = RP.build_source_review_row({"title_ko": "원목 식탁", "currency": "KRW", "price_original": 50000})
    net, pct = MarginCalculator._calc_margin(Decimal("71900"), Decimal("50000"), Decimal("3") / Decimal("100"))
    assert r["net_krw"] == int(net) and r["margin_pct"] == float(round(pct, 1))


# ── 라우트(등록 없음·검수표 렌더) ─────────────────────────────────────────────────
def _client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    return app.test_client()


def test_route_get_renders_input(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/seller/sourcing/register-pipe")
    assert r.status_code == 200 and "소싱 URL 검수" in r.get_data(as_text=True)


def test_route_post_builds_review_table_no_register(monkeypatch):
    c = _client(monkeypatch)
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_collect_real_draft",
                        lambda url, translate=True: ({"title_ko": "원목 식탁", "currency": "KRW",
                                                      "price_original": 40000, "images": ["https://i/1.jpg"]}
                                                     if "ok" in url else None))
    r = c.post("/seller/sourcing/register-pipe", data={"urls": "https://ok/1\nhttps://fail/2"})
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "검수표" in body and "수집 실패" in body


# ── P3: 승인 게이트 + 카나리 쿠팡 실등록 ──────────────────────────────────────────
def _p3_rows():
    # URL은 **식별자(ASIN)가 뽑히는 실형태** — SKU 게이트(카나리 8차)가 파편 URL을 막는다.
    return [{"url": "https://www.amazon.com/dp/B0AAAAAAA1", "title_ko": "원목 식탁",
             "sale_krw": 71900, "excluded": False},
            {"url": "https://www.amazon.de/-/en/dp/B0BBBBBBB2?ref_=x", "title_ko": "스텐 텀블러",
             "sale_krw": 27200, "excluded": False},
            {"url": "https://www.amazon.com/dp/B0CCCCCCC3", "title_ko": "샤넬 향수",
             "sale_krw": 300000, "excluded": True}]  # 취급제외


def test_p3_canary_registers_only_one():
    calls = []
    def disp(pd, acct):
        calls.append((pd["title_ko"], acct))
        return {"success": True, "product_id": "CP%d" % len(calls), "url": "https://coupang/CP"}
    out = RP.register_source_rows(_p3_rows(), dispatch_fn=disp,
                                  enrich_fn=lambda r: {"images": ["https://i/1.jpg", "https://i/2.jpg"]},
                                  account="gogane", sleep_fn=lambda s: None)
    assert out["ok"] and out["mode"] == "canary" and out["target"] == 1 and out["registered"] == 1
    assert len(calls) == 1 and calls[0][1] == "gogane"          # 첫 통과분 1건만(취급제외 제외)
    assert out["results"][0]["product_id"] == "CP1"


def test_p3_batch_registers_passing_only_and_account_routes():
    calls = []
    def disp(pd, acct):
        calls.append(acct); return {"success": True, "product_id": "X", "url": "u"}
    out = RP.register_source_rows(_p3_rows(), dispatch_fn=disp,
                                  enrich_fn=lambda r: {"images": ["u"]},
                                  account="woojoo", batch_ok=True, n=5, sleep_fn=lambda s: None)
    assert out["registered"] == 2 and out["target"] == 2         # 통과 2건(샤넬 제외)
    assert calls == ["woojoo", "woojoo"]                          # 계정 라우팅


def test_p3_no_image_not_registered_and_partial_failure_no_rollback():
    def disp(pd, acct):
        # 스텐 텀블러만 성공, 원목은 이미지 있으나 dispatch 거부.
        if "텀블러" in pd["title_ko"]:
            return {"success": True, "product_id": "OK", "url": "u"}
        return {"success": False, "error": "쿠팡 등록 거부: 카테고리 사전승인"}
    def enrich(r):
        return {"images": []} if "식탁" in r["title_ko"] else {"images": ["u"]}
    out = RP.register_source_rows(_p3_rows(), dispatch_fn=disp, enrich_fn=enrich,
                                  account="gogane", batch_ok=True, n=5, sleep_fn=lambda s: None)
    # 원목=이미지0 보류, 텀블러=성공 → 성공분 유지(롤백 금지), 실패분 사유.
    assert out["registered"] == 1 and out["failed"] == 1
    noimg = [x for x in out["results"] if "식탁" in x["title"]][0]
    assert noimg["registered"] is False and "이미지 0장" in noimg["reason"]


def test_p3_gated_when_not_approved():
    out = RP.register_source_rows(_p3_rows(), dispatch_fn=lambda pd, a: {"success": True},
                                  enrich_fn=lambda r: {"images": ["u"]}, approved=False)
    assert out["ok"] is False and out["approved"] is False and "미승인" in out["error"]


def test_p3_unknown_account_rejected():
    """계정 축 검증은 **어댑터** 책임으로 이관됐다(P5 — 마켓마다 축이 다르다).

    파이프라인은 빈 계정만 막고, 잘못된 계정명은 어댑터가 정직 차단한다(보호는 그대로).
    """
    from src.pipeline.register_adapters import get_adapter
    # ① 파이프라인: 빈 계정 차단(조용한 무계정 등록 방지).
    empty = RP.register_source_rows(_p3_rows(), dispatch_fn=lambda pd, a: {"success": True},
                                    enrich_fn=lambda r: {"images": ["u"]}, account="", approved=True)
    assert empty["ok"] is False and "계정이 지정되지" in empty["error"]
    # ② 어댑터: 축이 다른 계정명 차단(쿠팡 계정으로 스마트스토어 등록 불가).
    res = get_adapter("smartstore").register({"title_ko": "x"}, "foo")
    assert res["success"] is False and res["held"] is True
    assert "스마트스토어 계정이 아닙니다" in res["error"]


def test_p3_route_gated_or_registers(monkeypatch):
    c = _client(monkeypatch)
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_collect_real_draft",
                        lambda url, translate=True: {"title_ko": "원목 식탁", "currency": "KRW",
                                                     "price_original": 50000, "images": ["https://i/1.jpg"]})
    # dispatch를 몽키패치해 라이브 쿠팡 호출 없이 성공 반환.
    monkeypatch.setattr(V, "_coupang_account_dispatch",
                        lambda pd, account: {"success": True, "product_id": "CP1", "url": "https://coupang/CP1"})
    r = c.post("/seller/sourcing/register-pipe/register",
               data={"urls": "https://www.amazon.com/dp/B0AAAAAAA1", "account": "gogane"})
    d = r.get_json()
    assert d["ok"] and d["mode"] == "canary" and d["registered"] == 1 and d["account"] == "gogane"
