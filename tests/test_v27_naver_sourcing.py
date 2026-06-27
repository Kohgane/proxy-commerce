"""tests/test_v27_naver_sourcing.py — v27: 네이버 검색 API 소싱 분석 실데이터.

키 연결 시 실수치(검색 결과 수·상품 수·최저/평균가·판매처 수), 미연결 시 빈 상태(가짜 0 금지).
키는 env 전용. 검색광고(관심도/경쟁도)·해외직구·리뷰는 우리가 못 구하면 None('데이터 없음').
"""
from __future__ import annotations

import os

import pytest


def test_naver_search_env_only_and_empty_when_unset(monkeypatch):
    from src.sourcing import naver_shopping
    monkeypatch.delenv("NAVER_SEARCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_SEARCH_CLIENT_SECRET", raising=False)
    assert naver_shopping.is_configured() is False
    # 미설정 → 빈 결과(네트워크 호출 안 함, 가짜 데이터 0)
    res = naver_shopping.search_domestic("에코백", limit=12)
    assert res == {"items": [], "total": None}
    assert naver_shopping.search_domestic_products("에코백") == []


def test_analysis_empty_state_no_fake_numbers():
    from src.seller_console.views import _build_sourcing_analysis
    a = _build_sourcing_analysis([], None, "에코백", domestic_total=None)
    # 데이터 없으면 모든 수치 None(가짜 0 금지)
    assert all(m["value"] is None for m in a["metrics"])
    assert a["has_any"] is False


def test_analysis_real_values_when_data_present():
    from src.seller_console.views import _build_sourcing_analysis
    products = [
        {"price": 1000, "mall": "스토어A"},
        {"price": 3000, "mall": "스토어B"},
        {"price": 2000, "mall": "스토어A"},  # 같은 몰 → 고유 2곳
    ]
    a = _build_sourcing_analysis(products, None, "에코백", domestic_total=12345)
    vals = {m["label"]: m["value"] for m in a["metrics"]}
    assert vals["국내 검색 결과 수"] == "12,345개"
    assert vals["국내 판매 상품 수"] == "3개"
    assert vals["국내 최저가"] == "₩1,000"
    assert vals["국내 평균가"] == "₩2,000"
    assert vals["판매처(쇼핑몰) 수"] == "2곳"
    # 우리가 못 구하는 지표는 여전히 None(날조 금지)
    assert vals["해외직구 비율"] is None
    assert a["has_any"] is True


def test_sourcing_page_renders_without_keys(monkeypatch):
    monkeypatch.delenv("NAVER_SEARCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_SEARCH_CLIENT_SECRET", raising=False)
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        r = c.get("/seller/sourcing?keyword=에코백")
        assert r.status_code == 200
