"""tests/test_v88_c_pilot.py — v88-C 파일럿 배선: 모집단 396 결정성 · 50 선정 · 하드 정지 · 검수표 · admin 트리거.

라이브 실행 없음(트리거까지만). 순수 로직·라우트 접근/게이트 검증. 난수 금지(재현성).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline import coupang_replicate as CR


# ── 합성 sourcing_map (결정성·대표선정 검증) ─────────────────────────────────────
def _sm():
    return {
        # sid=100: 두 ASIN 그룹 → 대표 1 (krw+usd 보유 우선)
        "AAA00000A1": {"name_ko": "가", "krw": 1000, "sources": [{"url": "https://x/a", "priority": 1}], "coupang_sid": 100},
        "BBB00000B1": {"name_ko": "나", "krw": 2000, "usd": 2, "sources": [{"url": "https://x/b", "ship_usd": 0, "priority": 1}], "coupang_sid": 100},
        # sid=50: 단일
        "CCC00000C1": {"name_ko": "다", "krw": 3000, "sources": [{"url": "https://s.myshopify.com/products/c", "priority": 1}], "coupang_sid": 50},
        # coupang_sid 없음 → 모집단 제외
        "DDD00000D1": {"name_ko": "라", "krw": 4000, "sources": [{"url": "https://x/d"}]},
    }


def test_population_636_to_396_shape_and_determinism():
    r1 = CR.build_pilot_population(_sm())
    r2 = CR.build_pilot_population(_sm())
    # coupang_sid truthy 3 → distinct sid 2 (sid=100 중복 1 제거).
    assert r1["reduction"] == {"truthy": 3, "distinct_sid": 2, "dropped_dup": 1}
    assert r1["count"] == 2
    # 결정성: 두 번 돌려 동일 sid 시퀀스(sid 오름차순).
    assert [p["sid"] for p in r1["population"]] == [p["sid"] for p in r2["population"]] == [50, 100]


def test_representative_priority_krw_usd_then_ship_then_asin():
    pop = {p["sid"]: p for p in CR.build_pilot_population(_sm())["population"]}
    # sid=100 대표 = BBB(krw+usd 보유) — AAA(krw만)보다 우선.
    assert pop[100]["asin"] == "BBB00000B1"
    assert "krw+usd" in pop[100]["reason"]


def test_select_pilot_deterministic_and_count():
    pop = [{"sid": i, "asin": f"A{i}"} for i in range(200)]
    a = CR.select_pilot(pop, n=50)
    b = CR.select_pilot(list(reversed(pop)), n=50)   # 입력 순서 무관(내부 sid 정렬)
    assert len(a) == 50 and [x["sid"] for x in a] == [x["sid"] for x in b]   # 재현성
    assert [x["sid"] for x in a] == sorted(x["sid"] for x in a)              # sid 오름차순 stride
    # 모집단 <= n 이면 전량.
    assert len(CR.select_pilot(pop[:30], n=50)) == 30


def test_register_gate_approved_and_guard_passes():
    # 오너 최종 승인("전부가라") → 해제. 안전은 카나리 게이트(register_pilot_rows batch_ok)로 이관.
    assert CR.PILOT_REGISTER_APPROVED is True
    CR.pilot_register_guard()          # 승인됐으므로 raise 안 함


class _FakeUploadResult:
    def __init__(self, ok, url=None, message=None):
        self.market = "woocommerce"; self.success = ok; self.external_url = url; self.message = message


class _FakeDispatch:
    def __init__(self, ok=True): self.ok = ok; self.calls = []
    def __call__(self, product_data, markets):
        self.calls.append(product_data)
        class _DR:
            results = [_FakeUploadResult(self.ok, url="https://shop/p/%s" % product_data.get("title_ko"),
                                         message=None if self.ok else "WC 인증 실패")]
        return _DR()


def _rows(n=3):
    return [{"sid": 100 + i, "asin": "A%d" % i, "title_ko": "상품%d" % i, "sale_krw": 10000 + i,
             "excluded": False} for i in range(n)]


def test_register_canary_registers_only_first_without_batch_ok():
    disp = _FakeDispatch(ok=True)
    out = CR.register_pilot_rows(_rows(3), dispatch_fn=disp, sleep_fn=lambda s: None)
    assert out["mode"] == "canary" and out["target"] == 1 and out["registered"] == 1
    assert len(disp.calls) == 1                     # 첫 1건(Ystudio)만 — 46건 금지
    assert disp.calls[0]["status"] == "draft"       # draft 등록
    assert out["results"][0]["url"].startswith("https://shop/p/")


def test_register_batch_ok_registers_all_and_reports_per_row():
    disp = _FakeDispatch(ok=True)
    out = CR.register_pilot_rows(_rows(3), dispatch_fn=disp, n=47, batch_ok=True, sleep_fn=lambda s: None)
    assert out["mode"] == "batch" and out["target"] == 3 and out["registered"] == 3
    assert all(r["registered"] and r["status"] == "draft" for r in out["results"])


def test_register_partial_failure_no_rollback_and_honest_reason():
    # 첫 성공·둘째 실패 → 성공분 유지(롤백 금지), 실패분 사유 표기(조용한 실패 금지).
    class _Mixed(_FakeDispatch):
        def __call__(self, product_data, markets):
            ok = product_data["title_ko"] != "상품1"
            class _DR:
                results = [_FakeUploadResult(ok, url=("u" if ok else None), message=(None if ok else "가격 0"))]
            return _DR()
    out = CR.register_pilot_rows(_rows(3), dispatch_fn=_Mixed(), n=3, batch_ok=True, sleep_fn=lambda s: None)
    assert out["registered"] == 2 and out["failed"] == 1
    fail = [r for r in out["results"] if not r["registered"]][0]
    assert fail["reason"] and fail["url"] is None      # 사유 존재·롤백 안 함(성공 2건 유지)


def test_sourcing_map_resolves_source_url_not_none(tmp_path):
    # 등록 사후 근원 수리: 엔트리에 top-level url 없고 sources[].url만 있어도 해석(이미지 0장 근원).
    p = tmp_path / "sm.json"
    p.write_text(json.dumps({"B0AAA": {"name_ko": "가", "krw": 1000,
                 "sources": [{"url": "https://amz/dp/B0AAA", "priority": 2},
                             {"url": "https://amz/dp/BEST", "priority": 1}], "coupang_sid": 7}}), encoding="utf-8")
    m = CR.load_sourcing_map(str(p))["map"]
    assert m["B0AAA"] == "https://amz/dp/BEST"       # 우선순위 1 소스
    assert CR._best_source_url({"sources": []}) == "" and CR._best_source_url({"url": "u"}) == "u"


def test_register_silent_failure_guard_and_stock():
    # 이미지 0장인데 등록 성공 → warning(백필 필요) 표기(조용한 성공 금지) + no_image 집계.
    disp = _FakeDispatch(ok=True)
    out = CR.register_pilot_rows(_rows(1), dispatch_fn=disp, sleep_fn=lambda s: None)  # enrich 없음 → 이미지 0
    assert out["no_image"] == 1
    assert out["results"][0]["registered"] is True and out["results"][0]["warning"] == "이미지 0장 — 백필 필요"
    # 재고: 무재고 모델 — manage_stock off + instock.
    assert disp.calls[0]["manage_stock"] is False and disp.calls[0]["stock_status"] == "instock"


def test_backfill_images_matches_by_meta_idempotent_and_honest():
    rows = [{"sid": 10, "asin": "A", "excluded": False}, {"sid": 11, "asin": "B", "excluded": False},
            {"sid": 12, "asin": "C", "excluded": False}]
    products = [
        {"id": 101, "meta_data": [{"key": "_kgp_pilot_sid", "value": "10"}], "images": []},          # 매칭·백필
        {"id": 102, "meta_data": [{"key": "_kgp_pilot_sid", "value": "11"}], "images": [{"src": "x"}]},  # 이미 이미지 → 스킵
        # sid 12 → WC에 없음(unmatched)
    ]
    updated = {}
    def _upd(pid, patch): updated[pid] = patch; return True
    def _enrich(r):
        return {"images": ["https://i/1.jpg", "https://i/2.jpg", "https://i/3.jpg"]} if r["sid"] == 10 else {"images": []}
    out = CR.backfill_images(rows, enrich_fn=_enrich, list_products_fn=lambda: products, update_fn=_upd,
                             image_cap=2, stock_patch={"manage_stock": False, "stock_status": "instock"},
                             sleep_fn=lambda s: None)
    assert out["updated"] == 1 and out["skipped"] == 1 and out["unmatched"] == 1
    assert len(updated[101]["images"]) == 2                 # 2장 캡
    assert updated[101]["manage_stock"] is False and updated[101]["stock_status"] == "instock"  # 재고 동승


def test_prepare_product_data_stock_and_status_override():
    from src.vendors import woocommerce_client as wc
    prod = wc.prepare_product_data(
        {"title_ko": "테스트", "status": "draft", "manage_stock": False, "stock_status": "instock",
         "extra_meta": [{"key": "_kgp_pilot_sid", "value": "9"}]}, 10000)
    assert prod["status"] == "draft" and prod["manage_stock"] is False and prod["stock_status"] == "instock"
    assert "stock_quantity" not in prod                     # 관리 off면 수량 제거
    assert any(m["key"] == "_kgp_pilot_sid" for m in prod["meta_data"])


def test_register_flags_suspect_cjk_into_meta():
    disp = _FakeDispatch(ok=True)
    row = {"sid": 9, "asin": "Z", "title_ko": "세일러 万年筆", "sale_krw": 5000, "excluded": False,
           "title_truncated_suspect": True, "title_cjk_residual": True}
    CR.register_pilot_rows([row], dispatch_fn=disp, sleep_fn=lambda s: None)
    keys = {m["key"] for m in disp.calls[0]["pilot_meta"]}
    assert "_kgp_title_suspect" in keys and "_kgp_cjk_residual" in keys and "_kgp_pilot_sid" in keys


def test_review_row_blacklist_and_price_and_no_register():
    # 금지 카테고리 → excluded + 사유(조용한 탈락 금지).
    bad = CR.build_review_row({"sid": 1, "asin": "X", "name_ko": "샤넬 향수", "krw": 10000},
                              channel="woocommerce_multishop")
    assert bad["excluded"] is True and bad["forbidden"].startswith("forbidden-category")
    assert bad["registered"] is False
    # 정상 → 원가기준 가격(멀티샵 3%·마진 27.4%) 14,400.
    ok = CR.build_review_row({"sid": 2, "asin": "Y", "name_ko": "원목 식탁", "krw": 10000},
                             channel="woocommerce_multishop")
    assert ok["excluded"] is False and ok["sale_krw"] == 14400 and ok["registered"] is False
    # 주입 blacklist85 반영.
    inj = CR.build_review_row({"sid": 3, "asin": "Z", "name_ko": "특정금지품 XYZ", "krw": 5000},
                              channel="woocommerce_multishop", blacklist=["특정금지품"])
    assert inj["excluded"] is True and inj["forbidden"].startswith("blacklist")


# ── admin 트리거 라우트 (오너 세션 인증 · 등록 하드 정지) ─────────────────────────
def _admin_client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner"
        s["user_role"] = "admin"       # is_admin_session True
    return c


def test_pilot_route_requires_admin(monkeypatch):
    from src.order_webhook import app
    c = app.test_client()
    r = c.post("/admin/coupang-pilot")   # 세션 없음 → 로그인 리다이렉트(비-200)
    assert r.status_code in (301, 302, 403)


def test_pilot_route_returns_population_selection_and_gate(monkeypatch):
    c = _admin_client(monkeypatch)
    monkeypatch.delenv("COUPANG_BLACKLIST85", raising=False)
    # blacklist 미설정 → 가드가 400 → 전체 경로 검증 위해 명시적 우회.
    r = c.post("/admin/coupang-pilot?n=50&allow_no_blacklist=1")
    assert r.status_code == 200, r.status_code
    d = r.get_json()
    assert d["ok"] is True
    assert d["registered"] is False and "PILOT_REGISTER_APPROVED=True" in d["register_gate"]
    # 레포에 data/pilot_population.json(396) 존재 → 그 모집단 사용.
    if Path("data/pilot_population.json").is_file():
        assert d["population_count"] == 396 and d["selected"] == 50
    # 제외 테이블 키 존재(조용한 탈락 금지).
    assert "excluded_table" in d and "review_table" in d
    # 라이브 미충족(샌드박스) → 현행가 아님 표기.
    assert "현행가 아님" in d["price_basis"] or d["live"] is True


def test_pilot_route_blacklist_guard_blocks_on_zero(monkeypatch):
    # 조용한 실패 금지: blacklist 0건이면 표 산출 중단·400(빈 필터 전량 통과 금지).
    c = _admin_client(monkeypatch)
    monkeypatch.delenv("COUPANG_BLACKLIST85", raising=False)
    r = c.post("/admin/coupang-pilot?n=10")   # 우회 없음
    assert r.status_code == 400, r.status_code
    d = r.get_json()
    assert d["ok"] is False and d["blacklist85_loaded"] == 0
    assert "review_table" not in d           # 표를 만들지 않았다
    assert "COUPANG_BLACKLIST85" in d["how_to_load"]


def test_build_pilot_report_live_price_flips_basis_and_recalcs():
    # 계약(task 3): relay 주입 + price_fn(현행가) → price_basis="coupang live" + 마진 재계산.
    pop = [{"sid": 7, "asin": "A7", "name_ko": "원목 선반", "krw": 10000, "source": "amazon"}]
    access = {"ready": True, "missing": [], "relay_mode": "mkt.php(MARKET_API_RELAY_URL)",
              "coupang_accounts": {"우주대행": True}}
    relay = {"ready": True, "mode": "mkt.php(MARKET_API_RELAY_URL)"}
    # 현행가 재조회 stub: sourcing krw(10000)와 다른 현행가(20000) → 재계산 결과가 달라야 한다.
    live = CR.build_pilot_report(pop, n=1, access=access, relay=relay,
                                 price_fn=lambda sid: 20000, blacklist=["__none__"])
    assert live["live"] is True and live["live_price_used"] is True
    assert live["price_basis"].startswith("coupang live")
    sale_live = live["review_table"][0]["sale_krw"]
    # price_fn 없으면 sourcing krw 기준 → 다른 판매가 + basis 표기 달라짐.
    off = CR.build_pilot_report(pop, n=1, access=access, relay=relay,
                                price_fn=None, blacklist=["__none__"])
    assert off["live_price_used"] is False and "현행가 아님" in off["price_basis"]
    assert sale_live != off["review_table"][0]["sale_krw"], "현행가 재조회가 마진 재계산에 반영 안 됨"
