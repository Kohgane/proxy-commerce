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
    # 쿠팡 blacklist는 오너 자산 — 주입식(하드코딩 아님).
    assert CR.is_forbidden("어떤상품 특정금지어X", blacklist=["특정금지어X"]) == "blacklist:특정금지어X"
    assert CR.is_forbidden("어떤상품 특정금지어X") is None   # 미주입이면 통과(발명 0)


def test_lodge_skillet_excluded_korean_and_english():
    # 검수 반려 실증(B00063RWUM 롯지 스킬렛 미탐 수리): 한글표기(롯지)·영문(lodge) 둘 다 잡아야.
    bl = ["롯지", "lodge", "bose", "ping"]
    assert CR.is_forbidden("롯지 스킬렛 무쇠 팬", blacklist=bl) == "blacklist:롯지"       # 한글 부분일치
    assert CR.is_forbidden("롯지스킬렛10인치", blacklist=bl) == "blacklist:롯지"          # 연접도 잡음
    assert CR.is_forbidden("Lodge Cast Iron Skillet", blacklist=bl) == "blacklist:lodge"  # 영문 단어경계
    row = CR.build_review_row({"sid": 1, "asin": "B00063RWUM", "name_ko": "롯지 스킬렛 무쇠 팬", "krw": 30000},
                              blacklist=bl)
    assert row["excluded"] is True and row["forbidden"] == "blacklist:롯지"


def test_korean_partial_match_allow_exception_bossmeer():
    # 보스미어 오탐 수리: 보스(bose)가 보스미어(별개 브랜드)를 삼키면 안 됨. 정탐(보스 단독)은 유지.
    bl = ["보스", "bose", "나이키"]
    assert CR.is_forbidden("보스미어 워머 디퓨저", blacklist=bl) is None          # 예외 브랜드 → 무시(정탐 보호)
    assert CR.is_forbidden("보스 블루투스 스피커", blacklist=bl) == "blacklist:보스"  # 보스 단독 → 진짜 히트
    assert CR.is_forbidden("보스 스피커 보스미어 세트", blacklist=bl) == "blacklist:보스"  # 예외 밖에도 있으면 히트
    # 연접 정탐은 계속 잡힘(예외 아님).
    assert CR.is_forbidden("나이키운동화", blacklist=bl) == "blacklist:나이키"


def test_felco_size_tail_not_suspect():
    # FELCO nit: 사이즈 꼬리(S/M/L·XL)는 절단 아님. 진짜 단편(W)은 계속 의심.
    for ok in ("펠코 전정가위 L", "티셔츠 사이즈 M", "장갑 XL"):
        assert CR.clean_title_ko(ok)["truncated_suspect"] is False, ok
    assert CR.clean_title_ko("Rain Wand – 16 Inch Aluminum W")["truncated_suspect"] is True


def test_word_boundary_prevents_short_token_false_positives():
    # 오탐 방지(오너 승인 단어경계): shopping의 ping, dislodge의 lodge, hose의 ...는 안 걸린다.
    assert CR.is_forbidden("shopping bag 대용량", blacklist=["ping"]) is None
    assert CR.is_forbidden("dislodge tool set", blacklist=["lodge"]) is None
    assert CR.is_forbidden("bathrobe 목욕가운", blacklist=["bose"]) is None
    # 진짜 단어면 잡는다.
    assert CR.is_forbidden("Ping G430 드라이버", blacklist=["ping"]) == "blacklist:ping"
    assert CR.is_forbidden("BOSE 무선 이어폰", blacklist=["bose"]) == "blacklist:bose"


def test_clean_title_ko_strips_junk_and_flags_truncation():
    # 별점·프로모괄호·일문·중복어 제거.
    r = CR.clean_title_ko("【送料無料】나이키 나이키 운동화 ★★★★☆ (평점 4.5)")
    assert "★" not in r["title"] and "送料無料" not in r["title"] and "【" not in r["title"]
    assert r["title"].count("나이키") == 1        # 인접 중복어 축약
    assert r["changed"] is True
    # 절단 의심(말줄임표) → 조용히 자르지 않고 플래그.
    t = CR.clean_title_ko("초경량 캠핑 접이식 의자 대형 사이즈…")
    assert t["truncated"] is True
    # 일문 가나 제거.
    assert "ノ" not in CR.clean_title_ko("원목 선반 ラック 3단")["title"]


def test_clean_title_ko_english_rating_junk_removed():
    # #검수1 실데이터: FELCO(B00511984W) 별점 잡문 미제거 → 제거.
    r = CR.clean_title_ko("FELCO F-2 Classic Manual Hand Pruner 4.8 out of 5 stars, rating details")
    assert "out of 5 stars" not in r["title"] and "rating details" not in r["title"].lower()
    assert r["changed"] is True


@pytest.mark.parametrize("title", [
    "Insulated Stai", "PEN CLI", "Wireless Mouse w updat", "Fabric Scisso",
    "Leather Patente", "Rain Wand – 16 Inch Aluminum W",
])
def test_clean_title_ko_mid_truncation_flagged(title):
    # #검수2 실데이터: 중간 절단이 전량 false negative였다 → truncated 또는 truncated_suspect로 정직 표기.
    r = CR.clean_title_ko(title)
    assert r["truncated"] or r["truncated_suspect"], (title, r)


def test_clean_title_ko_complete_english_tail_not_falsely_flagged():
    # 완결 영문 꼬리는 절단으로 오탐하지 않는다(화이트리스트).
    assert not CR.clean_title_ko("Stainless Steel Kitchen Scissors")["truncated_suspect"]
    assert not CR.clean_title_ko("접이식 원목 3단 선반")["truncated_suspect"]   # 한글 꼬리 무판정


def test_clean_title_ko_place_tail_removed_and_cjk_flagged():
    # #검수3a 지명 잡문(US 주 코드) 꼬리 제거.
    r = CR.clean_title_ko("Denver Glass Stained Glass – Denver, CO Map")
    assert "Denver, CO" not in r["title"] and "Map" not in r["title"].split("–")[-1]
    # #검수3b CJK 한자는 삭제하지 않고 잔존 플래그만(브랜드/제품 소실 방지 — 번역 소관).
    r2 = CR.clean_title_ko("세일러 万年筆")
    assert "万年筆" in r2["title"] and r2["cjk_residual"] is True


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
              "MARKET_RELAY_TOKEN", "MARKET_API_RELAY_URL", "MARKET_API_RELAY_KEY", "MARKET_RELAY_MARKETS",
              "SOURCING_MAP_PATH", "COUPANG_BLACKLIST85", "COUPANG_BLACKLIST85_PATH",
              "COUPANG_GOGANE_ACCESS", "COUPANG_GOGANE_SECRET", "COUPANG_GOGANE_VENDOR",
              "COUPANG_GOGANE_ACCESS_KEY", "COUPANG_GOGANE_SECRET_KEY", "COUPANG_GOGANE_VENDOR_ID",
              "COUPANG_WOOJOO_ACCESS", "COUPANG_WOOJOO_SECRET", "COUPANG_WOOJOO_VENDOR",
              "COUPANG_WOOJOO_ACCESS_KEY", "COUPANG_WOOJOO_SECRET_KEY", "COUPANG_WOOJOO_VENDOR_ID"]:
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


def test_prefixed_woojoo_canonical_suffix_ready(monkeypatch):
    # v88-C 결함 회귀 가드: 오너가 코드베이스 표준 접미(_ACCESS_KEY/_SECRET_KEY/_VENDOR_ID)로 넣어도 감지.
    _clear_coupang(monkeypatch)
    for k in ("ACCESS_KEY", "SECRET_KEY", "VENDOR_ID"):
        monkeypatch.setenv(f"COUPANG_WOOJOO_{k}", "z")
    st = CR.access_status()
    assert st["coupang_accounts"]["우주대행"] is True, "표준 접미 자격 미감지 → live=false 재발"


def test_relay_ready_detects_both_conventions(monkeypatch):
    _clear_coupang(monkeypatch)
    assert CR.relay_ready() == {"ready": False, "mode": None}
    # mkt.php(현행): MARKET_API_RELAY_URL
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example/mkt.php")
    rr = CR.relay_ready()
    assert rr["ready"] is True and "mkt.php" in rr["mode"]
    # 구 /relay: MARKET_RELAY_URL + TOKEN 동시
    monkeypatch.delenv("MARKET_API_RELAY_URL", raising=False)
    monkeypatch.setenv("MARKET_RELAY_URL", "https://relay.example")
    assert CR.relay_ready()["ready"] is False        # TOKEN 없으면 미완
    monkeypatch.setenv("MARKET_RELAY_TOKEN", "t")
    assert CR.relay_ready()["ready"] is True


def test_load_blacklist85_env_json_csv_and_empty(monkeypatch):
    _clear_coupang(monkeypatch)
    monkeypatch.setattr(CR.Path, "is_file", lambda self: False)   # 파일 폴백 차단(순수 env 검증)
    # 미설정 → 0건(정직).
    assert CR.load_blacklist85()["count"] == 0
    # JSON 배열.
    monkeypatch.setenv("COUPANG_BLACKLIST85", '["샤넬", "루이비통", "롤렉스"]')
    r = CR.load_blacklist85()
    assert r["count"] == 3 and "샤넬" in r["terms"] and r["source"].startswith("env")
    # 개행/쉼표 구분.
    monkeypatch.setenv("COUPANG_BLACKLIST85", "샤넬, 루이비통\n롤렉스\n")
    assert CR.load_blacklist85()["count"] == 3


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
