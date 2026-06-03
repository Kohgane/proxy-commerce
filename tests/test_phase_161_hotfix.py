"""tests/test_phase_161_hotfix.py — Phase 161 hotfix 검증.

1. _build_sourcing_recommendations: keyword_context 인자 유/무 모두에서 정상 동작
2. sourcing_hub 뷰: keyword 쿼리 파라미터 유/무 모두에서 200 반환
3. 사이드바: "리서치/소싱" 그룹 제목이 한 번만 나타남
"""
from __future__ import annotations

import os
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("KEYWORD_OPT_PROVIDER", "mock")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "")


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret-161")
    import src.order_webhook as wh

    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="module")
def sidebar_html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "src", "seller_console", "templates", "_base.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. _build_sourcing_recommendations 시그니처 테스트
# ---------------------------------------------------------------------------


class TestBuildSourcingRecommendations:
    """keyword_context 인자 유/무 모두 예외 없이 리스트를 반환하는지 검증."""

    def test_with_keyword_context(self):
        """keyword_context 인자를 전달하면 정상적으로 추천 리스트를 반환한다."""
        from src.seller_console.views import _build_sourcing_recommendations

        context = {
            "risers": [
                {
                    "keyword": "요가복",
                    "search_volume": 50000,
                    "trend_pct": 12.5,
                    "avg_cpc_krw": 300,
                    "competition": 0.45,
                }
            ],
            "period_label": "일간",
            "period": "day",
        }
        result = _build_sourcing_recommendations(
            keyword="요가복",
            keyword_context=context,
            discovery_candidates=[],
            queue_candidates=[],
        )
        assert isinstance(result, list)
        # risers 항목이 추천에 포함돼야 한다
        assert any(r.get("title") == "요가복" for r in result)

    def test_without_keyword_context(self):
        """keyword_context 없이(기본값 None) 호출해도 예외 없이 빈 리스트를 반환한다."""
        from src.seller_console.views import _build_sourcing_recommendations

        result = _build_sourcing_recommendations(keyword="테스트상품")
        assert isinstance(result, list)

    def test_all_defaults(self):
        """모든 선택 인자를 생략해도 예외가 발생하지 않는다."""
        from src.seller_console.views import _build_sourcing_recommendations

        result = _build_sourcing_recommendations(keyword="")
        assert isinstance(result, list)

    def test_with_discovery_candidates(self):
        """discovery_candidates를 전달하면 Discovery 항목이 추천에 포함된다."""
        from src.seller_console.views import _build_sourcing_recommendations

        candidates = [{"domain": "brand-shop.com", "keyword": "브랜드", "status": "pending"}]
        result = _build_sourcing_recommendations(
            keyword="브랜드",
            discovery_candidates=candidates,
        )
        assert isinstance(result, list)
        assert any(r.get("title") == "brand-shop.com" for r in result)

    def test_max_12_results(self):
        """추천 결과는 최대 12개를 초과하지 않는다."""
        from src.seller_console.views import _build_sourcing_recommendations

        many_risers = [
            {
                "keyword": f"키워드{i}",
                "search_volume": 1000 + i,
                "trend_pct": float(i),
                "avg_cpc_krw": 100,
                "competition": 0.5,
            }
            for i in range(20)
        ]
        result = _build_sourcing_recommendations(
            keyword="",
            keyword_context={"risers": many_risers, "period_label": "일간", "period": "day"},
        )
        assert len(result) <= 12


# ---------------------------------------------------------------------------
# 2. sourcing_hub 뷰 스모크 테스트
# ---------------------------------------------------------------------------


class TestSourcingHubView:
    def test_sourcing_page_no_keyword_returns_200(self, client):
        """/seller/sourcing (keyword 없음) → 200."""
        resp = client.get("/seller/sourcing")
        assert resp.status_code == 200

    def test_sourcing_page_with_keyword_returns_200(self, client):
        """/seller/sourcing?keyword=해외직구 → 200."""
        resp = client.get("/seller/sourcing?keyword=%ED%95%B4%EC%99%B8%EC%A7%81%EA%B5%AC")
        assert resp.status_code == 200

    def test_sourcing_page_with_q_param_returns_200(self, client):
        """/seller/sourcing?q=나이키 → 200 (q 파라미터도 허용)."""
        resp = client.get("/seller/sourcing?q=%EB%82%98%EC%9D%B4%ED%82%A4")
        assert resp.status_code == 200

    def test_sourcing_page_contains_keyword_in_response(self, client):
        """keyword 전달 시 응답 HTML에 해당 키워드가 포함된다."""
        resp = client.get("/seller/sourcing?keyword=%EC%9A%94%EA%B0%80%EB%B3%B5")
        data = resp.get_data(as_text=True)
        assert "요가복" in data


# ---------------------------------------------------------------------------
# 3. 사이드바 중복 검증
# ---------------------------------------------------------------------------


class TestSidebarNoDuplicate:
    def test_research_sourcing_group_appears_once(self, sidebar_html):
        """'리서치/소싱' 그룹 제목이 사이드바에 정확히 한 번만 나타난다."""
        count = sidebar_html.count("리서치/소싱")
        assert count == 1, (
            f"'리서치/소싱' 그룹 제목이 {count}번 나타남 — 중복 제거 필요"
        )

    def test_keyword_trend_menu_appears_once(self, sidebar_html):
        """'키워드 트렌드' 메뉴(href)가 사이드바에 정확히 한 번만 나타난다."""
        count = sidebar_html.count('href="/seller/keywords"')
        assert count == 1, (
            f"'/seller/keywords' href가 {count}번 나타남 — 중복 제거 필요"
        )

    def test_ai_sourcing_hub_menu_appears_once(self, sidebar_html):
        """'AI 소싱 허브' 메뉴가 사이드바에 정확히 한 번만 나타난다."""
        count = sidebar_html.count("AI 소싱 허브")
        assert count == 1, (
            f"'AI 소싱 허브' 메뉴가 {count}번 나타남 — 중복 제거 필요"
        )

    def test_sourcing_watches_present(self, sidebar_html):
        """'소싱 watches' 메뉴가 사이드바에 존재한다."""
        assert "/seller/sourcing/watches" in sidebar_html

    def test_candidate_queue_present(self, sidebar_html):
        """'후보 큐' 메뉴가 사이드바에 존재한다."""
        assert "/seller/sourcing/candidates" in sidebar_html
