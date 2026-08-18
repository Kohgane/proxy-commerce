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
def test_sourcing_map_absent_is_honest():
    sm = CR.load_sourcing_map("nonexistent-path-xyz.json")
    assert sm["available"] is False and sm["count"] == 0 and "lookup" in sm


def test_access_status_blocks_live_without_assets(monkeypatch):
    for v in ["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "MARKET_RELAY_URL",
              "SOURCING_MAP_PATH"]:
        monkeypatch.delenv(v, raising=False)
    st = CR.access_status()
    assert st["ready"] is False
    assert "sourcing_map.json" in st["missing"]
    assert st["coupang_accounts"] == {"고가네": False, "우주대행": False}
    assert st["owner_action"]


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
