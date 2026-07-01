"""tests/test_phase_160_keyword_sourcing.py — Phase 160 단위 테스트.

키워드 트렌드 대시보드, AI 소싱 허브, My Sources, 수집 라우트 검증.
"""
from __future__ import annotations

import os
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    """테스트 환경 변수 설정."""
    monkeypatch.setenv("KEYWORD_OPT_PROVIDER", "mock")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "")  # Sheets 비활성화


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret-160")
    import src.order_webhook as wh

    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# keyword_optimizer — 트렌드 함수 테스트
# ---------------------------------------------------------------------------


class TestGetKeywordTrends:
    def test_returns_list(self):
        from src.ads.keyword_optimizer import get_keyword_trends

        result = get_keyword_trends(["유니클로"], period="month")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_all_periods_return_data(self):
        from src.ads.keyword_optimizer import get_keyword_trends

        for period in ("realtime", "day", "week", "month", "year"):
            result = get_keyword_trends(["나이키"], period=period)
            assert len(result) == 1, f"period={period} 결과 없음"
            assert result[0]["period"] == period

    def test_series_length_matches_period(self):
        from src.ads.keyword_optimizer import get_keyword_trends, _PERIOD_POINTS

        for period, expected_len in _PERIOD_POINTS.items():
            result = get_keyword_trends(["나이키"], period=period)
            series = result[0]["series"]
            assert len(series) == expected_len, f"period={period}: series 길이 불일치"

    def test_unknown_period_defaults_to_month(self):
        from src.ads.keyword_optimizer import get_keyword_trends, _PERIOD_POINTS

        result = get_keyword_trends(["유니클로"], period="bogus")
        assert result[0]["period"] == "month"
        assert len(result[0]["series"]) == _PERIOD_POINTS["month"]

    def test_trend_pct_is_float(self):
        from src.ads.keyword_optimizer import get_keyword_trends

        result = get_keyword_trends(["유니클로"], period="month")
        assert isinstance(result[0]["trend_pct"], float)

    def test_product_count_positive(self):
        from src.ads.keyword_optimizer import get_keyword_trends

        result = get_keyword_trends(["나이키"], period="month")
        assert result[0]["product_count"] >= 0

    def test_multiple_keywords(self):
        from src.ads.keyword_optimizer import get_keyword_trends

        result = get_keyword_trends(["유니클로", "나이키", "에코백"], period="week")
        assert len(result) == 3

    def test_unknown_keyword_fallback(self):
        from src.ads.keyword_optimizer import get_keyword_trends

        result = get_keyword_trends(["완전히알수없는키워드XYZ99"], period="day")
        assert len(result) == 1
        assert result[0]["monthly_search"] > 0


class TestGetRisingKeywords:
    def test_returns_list(self):
        from src.ads.keyword_optimizer import get_rising_keywords

        result = get_rising_keywords()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_limit_respected(self):
        from src.ads.keyword_optimizer import get_rising_keywords

        result = get_rising_keywords(limit=3)
        assert len(result) <= 3

    def test_has_required_fields(self):
        from src.ads.keyword_optimizer import get_rising_keywords

        result = get_rising_keywords()
        for r in result:
            assert "keyword" in r
            assert "change_pct" in r
            assert r["change_pct"] > 0


class TestGetRelatedKeywords:
    def test_returns_dict(self):
        from src.ads.keyword_optimizer import get_related_keywords

        result = get_related_keywords("유니클로")
        assert isinstance(result, dict)
        assert "related" in result
        assert "expanded" in result
        assert "longtail" in result

    def test_longtail_contains_keyword(self):
        from src.ads.keyword_optimizer import get_related_keywords

        result = get_related_keywords("나이키")
        for lt in result["longtail"]:
            assert "나이키" in lt

    def test_unknown_keyword_still_has_longtail(self):
        from src.ads.keyword_optimizer import get_related_keywords

        result = get_related_keywords("알수없는키워드")
        assert len(result["longtail"]) > 0


# ---------------------------------------------------------------------------
# MySourcesStore 테스트
# ---------------------------------------------------------------------------


class TestMySourcesStore:
    def test_add_and_list(self):
        from src.seller_console.my_sources_store import MySourcesStore, _MEM_STORE

        _MEM_STORE.clear()
        store = MySourcesStore()
        entry = store.add("brand.com", label="브랜드몰")
        assert entry.domain == "brand.com"
        assert entry.label == "브랜드몰"
        items = store.list()
        assert any(e.domain == "brand.com" for e in items)

    def test_duplicate_add_ignored(self):
        from src.seller_console.my_sources_store import MySourcesStore, _MEM_STORE

        _MEM_STORE.clear()
        store = MySourcesStore()
        store.add("dup.com")
        store.add("dup.com")  # 중복
        items = store.list()
        assert len([e for e in items if e.domain == "dup.com"]) == 1

    def test_remove(self):
        from src.seller_console.my_sources_store import MySourcesStore, _MEM_STORE

        _MEM_STORE.clear()
        store = MySourcesStore()
        store.add("remove.com")
        ok = store.remove("remove.com")
        assert ok is True
        items = store.list()
        assert not any(e.domain == "remove.com" for e in items)

    def test_remove_nonexistent_returns_false(self):
        from src.seller_console.my_sources_store import MySourcesStore, _MEM_STORE

        _MEM_STORE.clear()
        store = MySourcesStore()
        ok = store.remove("notexist.com")
        assert ok is False

    def test_normalize_url_to_domain(self):
        from src.seller_console.my_sources_store import MySourcesStore, _MEM_STORE

        _MEM_STORE.clear()
        store = MySourcesStore()
        entry = store.add("https://www.brand.com/products/1")
        assert entry.domain == "brand.com"

    def test_empty_domain_raises(self):
        from src.seller_console.my_sources_store import MySourcesStore

        with pytest.raises(ValueError):
            MySourcesStore().add("")

    def test_to_dict_has_keys(self):
        from src.seller_console.my_sources_store import SourceEntry

        e = SourceEntry(domain="test.com", label="테스트")
        d = e.to_dict()
        assert "domain" in d
        assert "label" in d
        assert "added_at" in d


# ---------------------------------------------------------------------------
# DiscoveryScout.add_candidate 테스트
# ---------------------------------------------------------------------------


class TestDiscoverySCoutAddCandidate:
    def test_add_candidate_no_sheet_returns_false(self):
        """GOOGLE_SHEET_ID 없으면 False 반환 (오류 없이)."""
        from src.discovery.scout import DiscoveryScout

        scout = DiscoveryScout()
        result = scout.add_candidate("newbrand.com", source_keyword="yoga")
        assert result is False  # SHEET_ID 미설정 → False

    def test_add_candidate_empty_domain_returns_false(self):
        from src.discovery.scout import DiscoveryScout

        scout = DiscoveryScout()
        result = scout.add_candidate("", source_keyword="test")
        assert result is False


# ---------------------------------------------------------------------------
# HTTP 라우트 테스트
# ---------------------------------------------------------------------------


class TestKeywordRoutes:
    def test_keywords_page_200(self, client):
        resp = client.get("/seller/keywords")
        assert resp.status_code == 200

    def test_keywords_page_with_query(self, client):
        resp = client.get("/seller/keywords?q=%EC%9C%A0%EB%8B%88%ED%81%B4%EB%A1%9C&period=month")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        assert "유니클로" in data

    def test_keywords_period_toggle(self, client):
        for period in ("realtime", "day", "week", "month", "year"):
            resp = client.get(f"/seller/keywords?q=%EB%82%98%EC%9D%B4%ED%82%A4&period={period}")
            assert resp.status_code == 200

    def test_keywords_search_api(self, client):
        resp = client.post(
            "/seller/keywords/search",
            json={"keywords": ["유니클로"], "period": "month"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["metrics"]) == 1

    def test_keywords_search_api_invalid_period(self, client):
        resp = client.post(
            "/seller/keywords/search",
            json={"keywords": ["나이키"], "period": "bogus"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["period"] == "month"


class TestSourcingRoutes:
    def test_sourcing_page_200(self, client):
        resp = client.get("/seller/sourcing")
        assert resp.status_code == 200

    def test_sourcing_page_with_keyword(self, client):
        resp = client.get("/seller/sourcing?keyword=%EC%9C%A0%EB%8B%88%ED%81%B4%EB%A1%9C")
        assert resp.status_code == 200

    def test_sourcing_recommend_api(self, client):
        resp = client.post(
            "/seller/sourcing/recommend",
            json={"keyword": "나이키"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) >= 1

    def test_sourcing_recommend_no_keyword(self, client):
        resp = client.post(
            "/seller/sourcing/recommend",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_my_sources_add_api(self, client):
        resp = client.post(
            "/seller/sourcing/my-sources/add",
            json={"domain": "test-route.com", "label": "테스트"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["domain"] == "test-route.com"

    def test_my_sources_add_empty_domain(self, client):
        resp = client.post(
            "/seller/sourcing/my-sources/add",
            json={"domain": ""},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_my_sources_list_api(self, client):
        resp = client.get("/seller/sourcing/my-sources?format=json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "sources" in data

    def test_my_sources_remove_api(self, client):
        # 먼저 추가
        client.post(
            "/seller/sourcing/my-sources/add",
            json={"domain": "toremove.com"},
            content_type="application/json",
        )
        resp = client.post(
            "/seller/sourcing/my-sources/remove",
            json={"domain": "toremove.com"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_sourcing_collect_get_redirects(self, client):
        resp = client.get("/seller/sourcing/collect?url=https%3A%2F%2Fbrand.com%2Fproduct%2F1")
        assert resp.status_code in (301, 302)

    def test_sourcing_collect_post_no_url(self, client):
        resp = client.post(
            "/seller/sourcing/collect",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400
