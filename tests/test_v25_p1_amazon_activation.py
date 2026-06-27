"""tests/test_v25_p1_amazon_activation.py — v25 P1: 아마존 국가선택 확장 + 초보 활성화 퍼널."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_amazon_country_dropdown_expanded_with_currency(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    # 주요국 + v25 신규(싱가포르/멕시코/UAE/브라질)
    for name in ("미국 (.com)", "일본 (.co.jp)", "싱가포르 (.sg)", "멕시코 (.com.mx)",
                 "UAE (.ae)", "브라질 (.com.br)"):
        assert name in html, f"아마존 국가 {name} 누락"
    # 통화 표기 + 선택 기억 훅
    for cur in ("USD", "JPY", "SGD", "BRL", "AED"):
        assert cur in html
    assert "data-amazon-country" in html
    assert "kgp_amazon_country" in html       # 선택 기억(localStorage)


# ---- 활성화 퍼널(compute_onboarding_state) ----
def test_funnel_prepends_collect_when_collected_count_given():
    from src.seller_console.onboarding import compute_onboarding_state
    s = compute_onboarding_state(connected_markets=0, source_count=0, product_count=0,
                                 collected_count=0)
    assert s["total_steps"] == 4
    assert s["steps"][0]["key"] == "collect"
    assert s["steps"][0]["is_next"] is True       # 첫 할 일 = 수집
    # 마지막 = 첫 업로드(아하-모먼트)
    assert s["steps"][-1]["key"] == "product"
    assert "업로드" in s["steps"][-1]["title"]


def test_funnel_collect_done_next_is_market():
    from src.seller_console.onboarding import compute_onboarding_state
    s = compute_onboarding_state(connected_markets=0, source_count=0, product_count=0,
                                 collected_count=3)
    assert s["steps"][0]["completed"] is True
    nxt = next(st for st in s["steps"] if st["is_next"])
    assert nxt["key"] == "market"


def test_funnel_upload_is_aha_completes_all():
    from src.seller_console.onboarding import compute_onboarding_state
    s = compute_onboarding_state(connected_markets=1, source_count=1, product_count=1,
                                 collected_count=1)
    assert s["completed_steps"] == 4 and s["is_completed"] is True


def test_legacy_3step_unchanged_without_collected_count():
    # 하위호환: collected_count 미전달 시 기존 3단계 그대로(회귀 0)
    from src.seller_console.onboarding import compute_onboarding_state
    s = compute_onboarding_state(connected_markets=0, source_count=0, product_count=0)
    assert s["total_steps"] == 3
    assert s["steps"][0]["key"] == "market"
