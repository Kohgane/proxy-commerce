"""tests/test_ai_sourcing_hub_v12.py — v12 가드: AI 소싱 허브 + 라벨/내비 + 분석 정직성."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- 네이버 쇼핑 클라이언트 정직성(날조 금지) ----
def test_naver_shopping_empty_without_keys(monkeypatch):
    for k in ("NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    from src.sourcing import naver_shopping
    assert naver_shopping.is_configured() is False
    assert naver_shopping.search_domestic_products("요가 레깅스") == []


def test_naver_shopping_empty_on_dry_run(monkeypatch):
    monkeypatch.setenv("NAVER_SEARCH_CLIENT_ID", "x")
    monkeypatch.setenv("NAVER_SEARCH_CLIENT_SECRET", "y")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.sourcing import naver_shopping
    assert naver_shopping.search_domestic_products("보틀") == []


# ---- 분석 패널: 계산 가능한 것만 실데이터, 나머지는 None('데이터 없음') ----
def test_analysis_panel_honest_no_fabrication():
    from src.seller_console.views import _build_sourcing_analysis
    products = [{"price": 10000}, {"price": 30000}]
    a = _build_sourcing_analysis(products, {"risers": []}, "보틀")
    by = {m["label"]: m for m in a["metrics"]}
    assert by["국내 판매 상품 수"]["value"] == "2개"
    assert by["국내 최저가"]["value"] == "₩10,000"
    assert by["국내 평균가"]["value"] == "₩20,000"
    # 계산 불가 지표는 반드시 None(가짜 수치 금지)
    assert by["해외직구 비율"]["value"] is None
    assert by["리뷰 지수"]["value"] is None


def test_analysis_empty_products_all_none():
    from src.seller_console.views import _build_sourcing_analysis
    a = _build_sourcing_analysis([], {"risers": []}, "x")
    assert {m["label"]: m["value"] for m in a["metrics"]}["국내 판매 상품 수"] is None


# ---- 소싱처 검색 딥링크 ----
def test_sourcing_search_links():
    from src.seller_console.views import _sourcing_search_links
    links = _sourcing_search_links("요가 레깅스")
    names = {l["name"] for l in links}
    assert {"타오바오", "1688", "알리익스프레스", "테무", "아마존"} <= names
    assert all(l["url"].startswith("http") for l in links)


# ---- 허브 렌더(키워드 시 섹션 노출, 키 없으면 정직 안내) ----
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    for k in ("NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_hub_renders_unified_ai_and_honest_data(client):
    html = client.get("/seller/sourcing?keyword=요가레깅스").get_data(as_text=True)
    assert "AI 소싱·등록" in html
    assert "AI 상품 추천받기" in html
    assert "국내에서 팔리는 상품" in html
    assert "/seller/listing/ai-create" in html       # 두 AI 모드 연결
    # 네이버 키 없음 → 정직 안내(가짜 카드 금지)
    assert "데이터 없음" in html or "연결되지 않았" in html


# ---- 내비 라벨 가독성(리네임) ----
def test_nav_intuitive_labels():
    html = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    for label in ["AI 소싱·등록", "소싱 관심목록", "수집 대기목록", "이미지 처리 대기",
                  "금지어·단어 바꾸기", "가격 자동 규칙", "환율 반영 보기",
                  "마켓 연동(API 키 입력)", "통관고유부호(PCCC) 조회", "문의 통합함"]:
        assert label in html, f"직관 라벨 누락: {label}"
    # 모호한 옛 라벨 제거
    for old in ["소싱 watches", "후보 큐", "CS 통합 인박스", "마켓 연결(키 설정)"]:
        assert old not in html, f"모호한 옛 라벨 잔존: {old}"
