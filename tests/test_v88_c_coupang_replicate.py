"""tests/test_v88_c_coupang_replicate.py — v88-C: 복제 파이프라인 코어 계약(오프라인, 합성 입력).

라이브 조인/파일럿은 sourcing_map+쿠팡 자격 필요(이 서버엔 없음) → access_status가 정직 게이트.
순수 로직(가격·필터·조인·중복·파일럿 계획)은 합성 입력으로 전량 검증. 가짜 수치 0.
"""
from __future__ import annotations

import pytest

from src.pipeline import coupang_replicate as CR


# ── 가격: 원가 기준 재계산(문서식 재사용) ────────────────────────────────────────
def test_recalc_multishop_cost_based_formula():
    r = CR.recalc_channel_price(10000, "woocommerce_multishop", margin_rate=27.4)
    assert r["ok"]
    assert r["fee_rate"] == 3.0 and r["margin_rate"] == 27.4
    # 판매가 = 원가/(1-0.03-0.274)=10000/0.696=14367.8 → 100원 올림 14400. (쿠팡 판매가 역산 아님)
    assert r["sale_price_krw"] == 14400, r


def test_recalc_shopify_fee_unknown_is_honest_not_fake(monkeypatch):
    monkeypatch.delenv("SHOPIFY_FEE_RATE", raising=False)
    r = CR.recalc_channel_price(10000, "shopify_global")
    assert r["ok"] is False and "수수료율 미상" in r["reason"]   # 가짜 0 금지
    monkeypatch.setenv("SHOPIFY_FEE_RATE", "5.0")
    r2 = CR.recalc_channel_price(10000, "shopify_global", margin_rate=27.4)
    assert r2["ok"] and r2["fee_rate"] == 5.0


def test_recalc_margin_plus_fee_over_100_rejected():
    r = CR.recalc_channel_price(10000, "woocommerce_multishop", margin_rate=99.0)
    assert r["ok"] is False


# ── 취급금지 필터 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("title,cat,expect", [
    ("샤넬 향수 50ml", "", "forbidden-category:향수"),
    ("아로마 캔들 세트", "", "forbidden-category:캔들"),
    ("Apple 정품 케이스", "", "forbidden-category:apple"),
    ("애플워치 밴드", "", "forbidden-category:애플"),
    ("CASETiFY 폰케이스", "", "forbidden-category:casetify"),
    ("일반 원목 식탁", "가구", None),
])
def test_forbidden_category_filter(title, cat, expect):
    assert CR.is_forbidden(title, cat) == expect


def test_forbidden_blacklist_injected_not_hardcoded():
    # 쿠팡 85 blacklist는 오너 자산 — 주입식(하드코딩 아님).
    assert CR.is_forbidden("어떤상품 특정금지어X", blacklist=["특정금지어X"]) == "blacklist:특정금지어X"
    assert CR.is_forbidden("어떤상품 특정금지어X") is None   # 미주입이면 통과(발명 0)


# ── 소스 분류 + 조인 ─────────────────────────────────────────────────────────────
def test_classify_source():
    assert CR.classify_source("https://www.amazon.co.jp/dp/B0XXXX") == "amazon"
    assert CR.classify_source("https://item.rakuten.co.jp/shop/x/") == "rakuten"
    assert CR.classify_source("https://brand.myshopify.com/products/foo") == "shopify_d2c"
    assert CR.classify_source("https://someshop.com/products/foo") == "shopify_d2c"
    assert CR.classify_source("https://unknown.example/x") == "other"


def test_join_inventory_counts_and_distribution():
    items = [
        {"account": "고가네", "seller_product_id": "1", "external_vendor_sku": "B001", "title": "A"},
        {"account": "고가네", "seller_product_id": "2", "external_vendor_sku": "B002", "title": "B"},
        {"account": "우주대행", "seller_product_id": "3", "external_vendor_sku": "B999", "title": "미매칭"},
    ]
    smap = {"B001": "https://brand.myshopify.com/products/a", "B002": "https://amazon.com/dp/B002"}
    rep = CR.join_inventory(items, smap)
    assert rep.on_sale == 3 and rep.matched == 2 and rep.unmatched == 1
    assert rep.by_source == {"shopify_d2c": 1, "amazon": 1}
    assert rep.as_table()["판매중"] == 3


# ── 중복 방지(멱등) ──────────────────────────────────────────────────────────────
def test_dedup_decision_idempotent():
    from src.collectors.product_key import normalize_product_key as key
    url = "https://brand.myshopify.com/products/foo"
    assert CR.dedup_decision(url, existing_source_keys={key(url)}) == "update"
    assert CR.dedup_decision(url, existing_source_keys=set()) == "new"


# ── 파일럿 계획(등록 직전 정지) ─────────────────────────────────────────────────
def test_plan_pilot_prefers_shopify_excludes_rakuten_no_sideeffect():
    rows = [
        CR.JoinRow("고가네", "1", "B1", "t", "https://s.myshopify.com/products/a", "shopify_d2c"),
        CR.JoinRow("고가네", "2", "B2", "t", "https://amazon.com/dp/x", "amazon"),
        CR.JoinRow("고가네", "3", "B3", "t", "https://item.rakuten.co.jp/x/", "rakuten"),
    ]
    plan = CR.plan_pilot(rows, n=50, prefer="shopify_d2c")
    assert plan["excluded_rakuten"] == 1
    assert all(r.source != "rakuten" for r in plan["selected"])       # 라쿠텐 서버크롤 차단 → 제외
    assert plan["selected"][0].source == "shopify_d2c"               # 신뢰도 최고 소스 우선
    assert "등록 직전 정지" in plan["note"]                          # 비가역 게이트


# ── 접근성 게이트(정직) ──────────────────────────────────────────────────────────
def test_sourcing_map_absent_is_honest(monkeypatch):
    # 후보 폴백(data/sourcing_map.json 실재)까지 비워 순수 부재 분기 검증.
    monkeypatch.setattr(CR, "_SOURCING_MAP_CANDIDATES", [])
    sm = CR.load_sourcing_map("nonexistent-path-xyz.json")
    assert sm["available"] is False and sm["count"] == 0 and "lookup" in sm


def test_sourcing_map_real_file_parses_richformat():
    # 실 파일(키=ASIN, 값에 coupang_sid/krw) 로드 계약 — count>0.
    if __import__("pathlib").Path("data/sourcing_map.json").is_file():
        sm = CR.load_sourcing_map("data/sourcing_map.json")
        assert sm["available"] is True and sm["count"] > 1000


def _clear_coupang(monkeypatch):
    for v in ["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "MARKET_RELAY_URL",
              "SOURCING_MAP_PATH", "COUPANG_GOGANE_ACCESS", "COUPANG_GOGANE_SECRET", "COUPANG_GOGANE_VENDOR",
              "COUPANG_WOOJOO_ACCESS", "COUPANG_WOOJOO_SECRET", "COUPANG_WOOJOO_VENDOR"]:
        monkeypatch.delenv(v, raising=False)


def test_access_status_blocks_live_without_assets(monkeypatch):
    _clear_coupang(monkeypatch)
    # sourcing_map은 이제 레포에 실재(main 착지) → 부재 분기를 결정적으로 테스트하려면 후보경로를 비운다.
    monkeypatch.setattr(CR, "_SOURCING_MAP_CANDIDATES", [])
    st = CR.access_status()
    assert st["ready"] is False
    assert "sourcing_map.json" in st["missing"]
    assert st["coupang_accounts"] == {"고가네": False, "우주대행": False}
    assert st["base_key"]["present"] is False and st["base_key"]["resolved_account"] is None
    assert st["owner_action"]


def test_access_status_sourcing_map_present_when_committed():
    # 실재 파일(main 착지) 계약: 후보경로에 data/sourcing_map.json 있으면 available·count>0.
    st = CR.access_status()
    if __import__("pathlib").Path("data/sourcing_map.json").is_file():
        assert st["sourcing_map"]["available"] is True and st["sourcing_map"]["count"] > 0
        assert "sourcing_map.json" not in st["missing"]


def test_base_key_resolves_to_single_account_by_vendor_id(monkeypatch):
    # 무접두 COUPANG_* + VENDOR_ID=A01381223 → 고가네만 ready(우주대행 False, 이중화 금지).
    _clear_coupang(monkeypatch)
    monkeypatch.setenv("COUPANG_VENDOR_ID", "A01381223")
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "x")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "y")
    assert CR.resolve_base_account() == "gogane"
    st = CR.access_status()
    assert st["coupang_accounts"] == {"고가네": True, "우주대행": False}
    assert st["base_key"]["resolved_account"] == "고가네"


def test_base_key_unknown_vendor_is_honest_no_attribution(monkeypatch):
    # 무접두 키는 있으나 VENDOR_ID가 두 계정과 불일치 → 어느 계정에도 부여 안 함(정직).
    _clear_coupang(monkeypatch)
    monkeypatch.setenv("COUPANG_VENDOR_ID", "A09999999")
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "x")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "y")
    assert CR.resolve_base_account() is None
    st = CR.access_status()
    assert st["coupang_accounts"] == {"고가네": False, "우주대행": False}
    assert st["base_key"]["present"] is True and st["base_key"]["resolved_account"] is None
    assert "불일치" in (st["base_key"]["note"] or "")


def test_prefixed_woojoo_credentials_ready(monkeypatch):
    _clear_coupang(monkeypatch)
    for k in ("ACCESS", "SECRET", "VENDOR"):
        monkeypatch.setenv(f"COUPANG_WOOJOO_{k}", "z")
    st = CR.access_status()
    assert st["coupang_accounts"]["우주대행"] is True and st["coupang_accounts"]["고가네"] is False


def test_run_inventory_join_not_ready_no_fake_numbers():
    # 자산/자격 미주입 → 가짜 수치 대신 access 보고(ok=False).
    out = CR.run_inventory_join()
    assert out["ok"] is False and "access" in out


def test_run_inventory_join_ready_with_injected_fetcher():
    # 주입식(테스트) — 라이브 어댑터 없이 조인 로직 실증. 쿠팡 데이터 무변경(읽기만).
    items = [{"account": "고가네", "seller_product_id": "1", "external_vendor_sku": "B001", "title": "A"}]
    smap = {"B001": "https://brand.myshopify.com/products/a"}
    out = CR.run_inventory_join(fetch_items_fn=lambda: items, sourcing_map=smap)
    assert out["ok"] and out["report"]["매칭"] == 1 and out["report"]["소스분포"] == {"shopify_d2c": 1}


# ── 파일럿 인입 오케스트레이션 (등록 직전 정지) ─────────────────────────────────
def _row(url, title="상품"):
    return CR.JoinRow("고가네", "1", "B1", title, url, CR.classify_source(url))


def test_pilot_ingest_stops_before_register_and_applies_all_gates():
    from src.collectors.product_key import normalize_product_key as key
    rows = [
        _row("https://s.myshopify.com/products/clean", "깨끗한 원목 식탁"),   # 정상
        _row("https://s.myshopify.com/products/perfume", "샤넬 향수"),        # 취급금지
        _row("https://s.myshopify.com/products/dup", "중복상품"),            # 기존 채널 존재
    ]
    collected = {"https://s.myshopify.com/products/clean":
                 {"title": "깨끗한 원목 식탁", "price": "10000", "currency": "KRW",
                  "images": ["a", "b", "c", "d"]}}   # 4장 → 2장 캡 검증

    def collect_fn(url):
        return collected.get(url)

    out = CR.run_pilot_ingest(
        rows, channel="woocommerce_multishop", collect_fn=collect_fn,
        prevalidate_fn=lambda d: {"ok": True},
        existing_source_keys={key("https://s.myshopify.com/products/dup")},
    )
    # ★ 절대 등록 안 함.
    assert out["registered"] is False and "등록 직전 정지" in out["note"]
    assert all(r["registered"] is False for r in out["rows"])
    s = out["summary"]
    assert s["skipped_forbidden"] == 1 and s["skipped_duplicate"] == 1 and s["ingested"] == 1
    ing = [r for r in out["rows"] if r["action"] == "ingested-prevalidated"][0]
    assert ing["images"] == 2                     # 이미지 2장 캡
    assert ing["price"]["ok"] and ing["price"]["sale_price_krw"] == 14400   # 원가기준 재계산
    assert ing["prevalidate_ok"] is True


def test_pilot_ingest_honest_collect_failure_and_foreign_cost():
    rows = [_row("https://s.myshopify.com/products/fail", "실패상품"),
            _row("https://s.myshopify.com/products/usd", "외화상품")]

    def collect_fn(url):
        if url.endswith("/fail"):
            return None                            # 수집 실패
        return {"title": "외화상품", "price": "50", "currency": "USD", "images": ["x"]}

    out = CR.run_pilot_ingest(rows, channel="woocommerce_multishop", collect_fn=collect_fn,
                              prevalidate_fn=lambda d: {"ok": False})
    assert out["summary"]["failed_collect"] == 1          # 정직 실패(가짜 성공 0)
    usd = [r for r in out["rows"] if r["action"] == "ingested-prevalidated"][0]
    assert usd["price"]["ok"] is False and "원가 미상" in usd["price"]["reason"]   # 외화=fx 미상, 가짜 환산 0
