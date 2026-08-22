"""tests/test_register_pipe_p1.py — 등록 파이프 P1: 소싱 URL→수집·검증→검수표(등록 없음).

순수 로직 + 라우트 접근. 수집은 주입(발명 0). 등록 절대 안 함(registered=False 불변).
"""
from __future__ import annotations

from src.pipeline import register_pipe as RP


def test_row_krw_cost_recalc_margin():
    d = {"title_ko": "원목 식탁 4인용", "currency": "KRW", "price_original": 50000, "images": ["https://i/1.jpg"]}
    r = RP.build_source_review_row(d, url="https://x/1")
    assert r["excluded"] is False and r["registered"] is False
    assert r["cost_krw"] == 50000 and r["sale_krw"] == 71900 and r["margin_pct"] == 27.4   # ÷0.618 정합
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
    return [{"url": "https://x/1", "title_ko": "원목 식탁", "sale_krw": 71900, "excluded": False},
            {"url": "https://x/2", "title_ko": "스텐 텀블러", "sale_krw": 27200, "excluded": False},
            {"url": "https://x/3", "title_ko": "샤넬 향수", "sale_krw": 300000, "excluded": True}]  # 취급제외


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
    out = RP.register_source_rows(_p3_rows(), dispatch_fn=lambda pd, a: {"success": True},
                                  enrich_fn=lambda r: {"images": ["u"]}, account="foo", approved=True)
    assert out["ok"] is False and "알 수 없는 계정" in out["error"]


def test_p3_route_gated_or_registers(monkeypatch):
    c = _client(monkeypatch)
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_collect_real_draft",
                        lambda url, translate=True: {"title_ko": "원목 식탁", "currency": "KRW",
                                                     "price_original": 50000, "images": ["https://i/1.jpg"]})
    # dispatch를 몽키패치해 라이브 쿠팡 호출 없이 성공 반환.
    monkeypatch.setattr(V, "_coupang_account_dispatch",
                        lambda pd, account: {"success": True, "product_id": "CP1", "url": "https://coupang/CP1"})
    r = c.post("/seller/sourcing/register-pipe/register", data={"urls": "https://ok/1", "account": "gogane"})
    d = r.get_json()
    assert d["ok"] and d["mode"] == "canary" and d["registered"] == 1 and d["account"] == "gogane"
