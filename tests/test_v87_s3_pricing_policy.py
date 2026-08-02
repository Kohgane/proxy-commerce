"""tests/test_v87_s3_pricing_policy.py — v87-S3 가격 정책 설정.

핵심은 **이관 계약**이다: 마진·수수료·배송 기준이 코드 상수에서 셀러 정책(settings.policy jsonb)으로
옮겨갔는데, 정책을 저장한 적 없는 셀러의 계산 결과는 이관 전과 **완전히 같아야** 한다. 값이 조금이라도
달라지면 그건 기능이 아니라 회귀다(등록가가 소리 없이 바뀌면 돈이 샌다).

그 다음이 이 화면의 존재 이유 — 블랙박스 금지: 식을 화면에 적고, 정책을 만지면 샘플 1건의 판매가가
어떻게 변하는지 즉시 보인다.
"""
from __future__ import annotations

import pytest
from flask import Flask

from src.db import settings_pg
from src.pricing import calculator
from src.pricing.policy import (
    FORMULA_TEXT,
    compute_sell_price,
    default_policy,
    market_fee_pct,
    merge_policy,
    round_up,
    validate_policy,
)

WEB_UI = __import__("src.dashboard.web_ui", fromlist=["web_ui_bp"])


@pytest.fixture()
def app():
    """web_ui 블루프린트만 실은 격리 앱 — 공용 앱을 건드리면 다른 테스트를 오염시킨다(선례)."""
    a = Flask(__name__)
    a.secret_key = "test"
    a.register_blueprint(WEB_UI.web_ui_bp, url_prefix="/dashboard")
    return a


@pytest.fixture()
def client(app):
    settings_pg._reset_for_tests()
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "seller-1"
        s["user_role"] = "admin"
        s["email"] = "seller@example.com"
    return c


@pytest.fixture(autouse=True)
def _fixed_fx(monkeypatch):
    """환율 공급자를 물면 네트워크·시세에 따라 값이 흔들려 계약이 무의미해진다 → 고정."""
    monkeypatch.setattr(calculator, "_to_krw_rate", lambda cur: 1350.0 if (cur or "USD").upper() != "KRW" else 1.0)
    monkeypatch.setattr(WEB_UI, "_get_fx_rates", lambda: {"USDKRW": 1350.0, "JPYKRW": 9.2})


# ── 이관 계약 ────────────────────────────────────────────────────────────────

def test_default_policy_equals_legacy_constants():
    """디폴트 정책 = 이관 전 코드 상수. 여기가 갈라지면 '조용한 가격 변경'이 된다."""
    p = default_policy()
    assert p["margin"]["percent_margin"] == 30.0
    assert p["margin"]["ad_budget_pct"] == 5.0
    assert p["margin"]["min_margin_guard_pct"] == 15.0
    assert p["fees"]["card_pct"] == pytest.approx(3.3)          # 0.033
    assert p["customs"]["vat_pct"] == pytest.approx(10.0)       # 0.10
    assert p["shipping"]["intl_ship_per_kg_krw"] == 18000.0
    assert p["shipping"]["default_weight_kg"] == 0.5
    # 마켓 수수료 = 각 마켓 공표 수수료(현행 _market_fee와 같은 값).
    assert p["fees"]["market_pct"]["coupang"] == pytest.approx(10.8)
    assert p["fees"]["market_pct"]["smartstore"] == pytest.approx(5.85)
    assert p["fees"]["market_pct"]["11st"] == pytest.approx(12.0)
    assert p["fees"]["market_pct"]["gmarket"] == pytest.approx(12.0)


@pytest.mark.parametrize("market", ["coupang", "smartstore", "11st", "gmarket", "unknown"])
@pytest.mark.parametrize("category", ["의류", "전자", "식품", "뷰티", "기타"])
def test_no_policy_reproduces_legacy_numbers(market, category):
    """정책 미저장(policy=None) 결과가 이관 전 수식·상수 결과와 동일한지 **독립 재계산**으로 대조.

    기대값을 손으로 적지 않고 옛 공식을 여기서 다시 세워 비교한다 — 상수 하나만 흘러도 잡힌다.
    """
    got = calculator.calculate_listing_price(
        source_price=25.0, source_currency="USD", weight_kg=0.4,
        market=market, category=category)

    cost = 25.0 * 1350.0
    shipping = 0.4 * 18000.0
    customs = (cost + shipping) * calculator._customs_pct(category)
    landed = cost + shipping + customs
    total_landed = landed + landed * 0.10
    legacy_fee = calculator._market_fee(market)          # 이관 전 마켓 수수료 경로
    deduction = legacy_fee + 0.033 + (5.0 / 100.0)
    expected = total_landed * (1.0 + 30.0 / 100.0) / max(1.0 - deduction, 0.01)

    assert got.total_landed == pytest.approx(total_landed)
    assert got.market_fee_pct == pytest.approx(legacy_fee)
    assert got.payment_fee_pct == pytest.approx(0.033)
    assert got.calculated_price == pytest.approx(expected)


def test_saved_policy_actually_changes_listing_price():
    """정책을 바꾸면 등록가가 실제로 바뀐다(단일화가 실효인지 — 읽기만 하고 안 쓰면 무의미)."""
    base = calculator.calculate_listing_price(
        source_price=25.0, source_currency="USD", weight_kg=0.4,
        market="coupang", category="의류")
    bumped = calculator.calculate_listing_price(
        source_price=25.0, source_currency="USD", weight_kg=0.4,
        market="coupang", category="의류",
        policy={"margin": {"percent_margin": 45.0}, "fees": {"card_pct": 2.0}})
    assert bumped.calculated_price > base.calculated_price
    assert bumped.target_margin_pct == 45.0
    assert bumped.payment_fee_pct == pytest.approx(0.02)


# ── 정책 모델 ────────────────────────────────────────────────────────────────

def test_merge_keeps_defaults_for_absent_keys():
    """부분 저장 안전 — 안 건드린 항목이 0으로 무너지면 안 된다."""
    merged = merge_policy({"margin": {"percent_margin": 12.0}})
    assert merged["margin"]["percent_margin"] == 12.0
    assert merged["fees"]["card_pct"] == pytest.approx(3.3)
    assert merged["shipping"]["intl_ship_per_kg_krw"] == 18000.0


def test_unknown_market_falls_back_to_coupang():
    assert market_fee_pct(default_policy(), "no-such") == pytest.approx(10.8)


def test_round_up_units():
    assert round_up(88550.98, 100) == 88600
    assert round_up(88550.98, 10) == 88560


def test_validate_rejects_impossible_fee_sum():
    """수수료 합이 100%를 넘으면 판매가가 무한대로 튄다 → 저장 자체를 막는다."""
    errs = validate_policy(merge_policy({"margin": {"percent_margin": 95.0}}))
    assert errs and any("100%" in e for e in errs)


def test_validate_accepts_default():
    assert validate_policy(default_policy()) == []


def test_compute_sell_price_matches_declared_formula():
    """식이 장식이 아니라 **실제로 그 식대로** 계산되는지 손계산과 대조."""
    p = merge_policy({"margin": {"percent_margin": 30.0, "plus_margin_krw": 1000.0},
                      "fees": {"card_pct": 3.3, "market_pct": {"coupang": 10.8}},
                      "shipping": {"intl_ship_krw": {"US": 15000}},
                      "display": {"round_unit": 100, "discount_pct": 0}})
    r = compute_sell_price(p, source_price=25.0, fx_rate=1380.0, market="coupang", country="US")
    numerator = 25.0 * 1380.0 + 15000 + 1000.0
    denominator = 1 - 0.30 - 0.108 - 0.033
    assert r["ok"]
    # raw_price는 표시용으로 소수 2자리까지 반올림해 돌려준다 → 같은 자리수로 비교한다.
    assert r["raw_price"] == pytest.approx(round(numerator / denominator, 2), abs=0.005)
    assert r["sell_price"] == round_up(numerator / denominator, 100)
    assert r["formula"] == FORMULA_TEXT


def test_compute_reports_failure_instead_of_absurd_price():
    """분모가 0 이하면 숫자를 지어내지 않고 실패로 말한다(가짜 값 금지)."""
    r = compute_sell_price(merge_policy({"margin": {"percent_margin": 95.0}}),
                           source_price=10, fx_rate=1350, market="coupang", country="US")
    assert r["ok"] is False and r["sell_price"] is None


# ── 저장소: 낙관잠금 · 이력 ──────────────────────────────────────────────────

def test_optimistic_lock_blocks_stale_overwrite():
    """두 탭에서 동시에 저장할 때 뒤엣것이 앞엣것을 조용히 덮어쓰지 않는다."""
    settings_pg._reset_for_tests()
    settings_pg.save_policy("u1", {"margin": {"percent_margin": 10.0}}, 0, "첫 저장")
    with pytest.raises(settings_pg.ConflictError):
        settings_pg.save_policy("u1", {"margin": {"percent_margin": 99.0}}, 0, "낡은 버전")
    assert settings_pg.get_policy("u1")["policy"]["margin"]["percent_margin"] == 10.0


def test_history_keeps_five_most_recent():
    settings_pg._reset_for_tests()
    ver = 0
    for i in range(7):
        ver = settings_pg.save_policy("u1", {"margin": {"percent_margin": float(i)}}, ver, f"변경 {i}")["version"]
    hist = settings_pg.list_history("u1", 5)
    assert len(hist) == 5
    assert hist[0]["version"] == 7          # 최신이 먼저


def test_diff_summary_is_human_readable():
    s = settings_pg.diff_summary({"margin": {"percent_margin": 30.0}},
                                 {"margin": {"percent_margin": 40.0}})
    assert "margin.percent_margin" in s and "30.0" in s and "40.0" in s


# ── 화면 ─────────────────────────────────────────────────────────────────────

def test_no_new_nav_item():
    """화면 수 동결 — 정책은 환율·마진 탭 **안**의 서브섹션이지 새 메뉴가 아니다."""
    keys = [k for _, _, k in WEB_UI._NAV_ITEMS]
    assert keys == ["index", "products", "uploads", "orders", "fx"]


def test_fx_page_shows_formula_and_sections(client):
    """블랙박스 금지 — 식과 각 서브섹션이 화면에 실제로 있다."""
    r = client.get("/dashboard/fx")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert FORMULA_TEXT in html, "판매가 산출 식이 화면에 없다(블랙박스)"
    for label in ("가격 정책", "마진", "배송", "수수료", "표기", "통관", "등록 미리보기", "변경 이력"):
        assert label in html, label
    assert "base_version" in html, "낙관잠금 토큰이 폼에 없다"
    # 퍼센티 문구·색 복제 금지 — 남의 브랜드명이 화면에 새어 나오지 않는다.
    assert "퍼센티" not in html


def test_save_then_reflected_and_history(client):
    r = client.post("/dashboard/fx/policy", data={
        "base_version": "0", "percent_margin": "40", "card_pct": "3.3", "fee_coupang": "10.8"})
    assert r.status_code == 302 and "policy_saved=1" in r.headers["Location"]
    got = settings_pg.get_policy("seller-1")
    assert got["version"] == 1
    assert got["policy"]["margin"]["percent_margin"] == 40.0
    assert len(settings_pg.list_history("seller-1")) == 1


def test_save_conflict_is_reported_not_silent(client):
    client.post("/dashboard/fx/policy", data={"base_version": "0", "percent_margin": "40"})
    r = client.post("/dashboard/fx/policy", data={"base_version": "0", "percent_margin": "50"})
    assert r.status_code == 302
    assert "policy_error" in r.headers["Location"]
    assert settings_pg.get_policy("seller-1")["policy"]["margin"]["percent_margin"] == 40.0


def test_invalid_policy_is_rejected(client):
    r = client.post("/dashboard/fx/policy", data={
        "base_version": "0", "percent_margin": "95", "card_pct": "3.3", "fee_coupang": "10.8"})
    assert "policy_error" in r.headers["Location"]
    assert settings_pg.get_policy("seller-1")["version"] == 0, "검증 실패인데 저장됐다"


def test_preview_returns_before_and_after(client):
    """정책을 바꾸면 샘플 1건 판매가가 어떻게 달라지는지 즉시 보인다(퍼센티에 없는 것)."""
    client.post("/dashboard/fx/policy", data={
        "base_version": "0", "percent_margin": "30", "card_pct": "3.3", "fee_coupang": "10.8"})
    r = client.post("/dashboard/fx/policy/preview", data={
        "percent_margin": "45", "card_pct": "3.3", "fee_coupang": "10.8",
        "sample_price": "25", "sample_rate": "1380",
        "sample_market": "coupang", "sample_country": "US"})
    d = r.get_json()
    assert d["ok"] is True
    assert d["after"]["sell_price"] > d["before"]["sell_price"], d
    # 중간값까지 다 보여야 한다 — 숫자 하나만 던지면 블랙박스다.
    labels = [s["label"] for s in d["after"]["steps"]]
    assert any("매입가" in x for x in labels) and any("분모" in x for x in labels)


def test_preview_surfaces_validation_errors(client):
    r = client.post("/dashboard/fx/policy/preview", data={"percent_margin": "95"})
    d = r.get_json()
    assert d["ok"] is False and d["errors"]


def test_preview_uses_server_formula_only():
    """미리보기 식이 화면에서 재구현되면 두 식이 갈라져 거짓말을 한다 → JS는 서버만 호출한다."""
    js = WEB_UI._POLICY_PREVIEW_JS
    assert "/dashboard/fx/policy/preview" in js
    for token in ("percent_margin /", "1 - ", "denominator ="):
        assert token not in js, "미리보기 JS가 계산식을 직접 구현했다"


def test_listing_path_reads_seller_policy(app):
    """등록가 경로가 셀러 정책을 실제로 읽는다(세션 없으면 None → 디폴트, 무회귀)."""
    from src.ai_listing.price_suggester import _seller_pricing_policy

    settings_pg._reset_for_tests()
    assert _seller_pricing_policy() is None      # 요청 컨텍스트 밖 = 조용히 디폴트
    with app.test_request_context("/"):
        from flask import session as flask_session

        flask_session["user_id"] = "seller-1"
        settings_pg.save_policy("seller-1", {"margin": {"percent_margin": 42.0}}, 0, "테스트")
        pol = _seller_pricing_policy()
    assert pol and pol["margin"]["percent_margin"] == 42.0
