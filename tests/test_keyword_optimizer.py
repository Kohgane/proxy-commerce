"""tests/test_keyword_optimizer.py — 키워드 입찰 최적화 테스트 (Phase 144)."""
from __future__ import annotations

import pytest


class TestGetKeywordMetrics:
    def test_returns_metrics_list(self):
        from src.ads.keyword_optimizer import get_keyword_metrics
        result = get_keyword_metrics(["유니클로", "나이키"])
        assert len(result) == 2

    def test_unknown_keyword_has_defaults(self):
        from src.ads.keyword_optimizer import get_keyword_metrics
        result = get_keyword_metrics(["알수없는키워드XYZ"])
        assert len(result) == 1
        m = result[0]
        assert m.avg_cpc_krw > 0
        assert 0 <= m.competition <= 1

    def test_known_keyword_matches_db(self):
        from src.ads.keyword_optimizer import get_keyword_metrics
        result = get_keyword_metrics(["유니클로"])
        m = result[0]
        assert m.monthly_search == 85000
        assert m.avg_cpc_krw == 320

    def test_to_dict_fields(self):
        from src.ads.keyword_optimizer import get_keyword_metrics
        result = get_keyword_metrics(["나이키"])
        d = result[0].to_dict()
        assert "keyword" in d
        assert "monthly_search" in d
        assert "avg_cpc_krw" in d
        assert "roas" in d
        assert "match_score" in d


class TestMatchKeywordsToProduct:
    def test_returns_sorted_by_match_score(self):
        from src.ads.keyword_optimizer import match_keywords_to_product
        kws = ["유니클로", "나이키", "에어포스", "에코백"]
        result = match_keywords_to_product("나이키 에어포스 240", kws)
        scores = [m.match_score for m in result]
        assert scores == sorted(scores, reverse=True), "매칭 점수 내림차순 정렬 실패"

    def test_high_overlap_keyword_gets_high_score(self):
        from src.ads.keyword_optimizer import match_keywords_to_product
        result = match_keywords_to_product("유니클로 플리스 자켓", ["유니클로"])
        m = result[0]
        assert m.match_score > 0, "유니클로 ↔ 유니클로 플리스 자켓 매칭 점수=0"


class TestRecommendBids:
    def test_recommended_bid_within_bounds(self):
        from src.ads.keyword_optimizer import get_keyword_metrics, recommend_bids
        metrics = get_keyword_metrics(["유니클로", "나이키"])
        bids = recommend_bids(metrics, target_cpa_krw=5000)
        for b in bids:
            avg_cpc = b["avg_cpc_krw"]
            rec_bid = b["recommended_bid_krw"]
            assert rec_bid >= 50, "최소 입찰가 50원 미만"
            assert rec_bid >= avg_cpc * 0.7 - 1, f"입찰가 {rec_bid} < avg_cpc*0.7 {avg_cpc*0.7}"
            assert rec_bid <= avg_cpc * 1.3 + 1, f"입찰가 {rec_bid} > avg_cpc*1.3 {avg_cpc*1.3}"

    def test_returns_list_of_dicts(self):
        from src.ads.keyword_optimizer import get_keyword_metrics, recommend_bids
        metrics = get_keyword_metrics(["에코백"])
        bids = recommend_bids(metrics)
        assert len(bids) == 1
        assert "keyword" in bids[0]
        assert "recommended_bid_krw" in bids[0]


class TestSuggestNegativeKeywords:
    def test_zero_revenue_keyword_is_negative(self):
        from src.ads.keyword_optimizer import suggest_negative_keywords
        data = [
            {"keyword": "브랜드명 짝퉁", "cost_krw": 5000.0, "revenue_krw": 0.0},
            {"keyword": "유니클로", "cost_krw": 3000.0, "revenue_krw": 15000.0},
        ]
        negatives = suggest_negative_keywords(data)
        assert "브랜드명 짝퉁" in negatives
        assert "유니클로" not in negatives

    def test_very_low_roas_is_negative(self):
        from src.ads.keyword_optimizer import suggest_negative_keywords
        data = [
            {"keyword": "저효율 키워드", "cost_krw": 10000.0, "revenue_krw": 100.0},  # ROAS=0.01
        ]
        negatives = suggest_negative_keywords(data)
        assert "저효율 키워드" in negatives

    def test_empty_keyword_ignored(self):
        from src.ads.keyword_optimizer import suggest_negative_keywords
        data = [{"keyword": "", "cost_krw": 1000.0, "revenue_krw": 0.0}]
        negatives = suggest_negative_keywords(data)
        assert "" not in negatives

    def test_no_cost_not_negative(self):
        from src.ads.keyword_optimizer import suggest_negative_keywords
        data = [{"keyword": "아직 시작 안 함", "cost_krw": 0.0, "revenue_krw": 0.0}]
        negatives = suggest_negative_keywords(data)
        assert "아직 시작 안 함" not in negatives


class TestKeywordOptimizerStats:
    def test_stats_returns_dict(self):
        from src.ads.keyword_optimizer import keyword_optimizer_stats
        s = keyword_optimizer_stats()
        assert isinstance(s, dict)
        assert "provider" in s
        assert "target_roas" in s
        assert "db_keywords" in s
        assert s["db_keywords"] > 0
