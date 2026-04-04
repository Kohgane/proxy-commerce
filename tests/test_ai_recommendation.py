"""tests/test_ai_recommendation.py — Phase 94: AI 기반 상품 추천 시스템 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.ai_recommendation import (
    AIRecommendationEngine,
    AdvancedCollaborativeFilter,
    AdvancedContentBasedFilter,
    PersonalizationEngine,
    AITrendingAnalyzer,
    CrossSellEngine,
    FeedbackLoop,
    AutoRecommender,
    UserEvent,
    EventType,
    RecommendationResult,
    UserProfile,
    ProductVector,
    PriceTier,
)


# ---------------------------------------------------------------------------
# TestRecommendationModel
# ---------------------------------------------------------------------------

class TestRecommendationModel:
    def test_user_event_to_dict(self):
        event = UserEvent(
            user_id="u1",
            event_type=EventType.PURCHASE,
            product_id="p1",
        )
        d = event.to_dict()
        assert d["user_id"] == "u1"
        assert d["event_type"] == "purchase"
        assert d["product_id"] == "p1"
        assert "timestamp" in d

    def test_recommendation_result_to_dict(self):
        r = RecommendationResult(product_id="p1", score=0.95, strategy="ensemble", reason="test")
        d = r.to_dict()
        assert d["product_id"] == "p1"
        assert d["score"] == 0.95
        assert d["strategy"] == "ensemble"

    def test_user_profile_defaults(self):
        p = UserProfile(user_id="u1")
        assert p.category_preferences == {}
        assert p.purchase_history == []
        assert p.segment == "general"

    def test_product_vector_to_dict(self):
        pv = ProductVector(
            product_id="p1",
            category="electronics",
            brand="Samsung",
            price_tier=PriceTier.HIGH,
            tags=["phone", "android"],
        )
        d = pv.to_dict()
        assert d["product_id"] == "p1"
        assert d["price_tier"] == "high"

    def test_event_types(self):
        assert EventType.VIEW.value == "view"
        assert EventType.PURCHASE.value == "purchase"
        assert EventType.CART.value == "cart"
        assert EventType.WISHLIST.value == "wishlist"
        assert EventType.SEARCH.value == "search"

    def test_price_tiers(self):
        assert PriceTier.LOW.value == "low"
        assert PriceTier.MID.value == "mid"
        assert PriceTier.HIGH.value == "high"
        assert PriceTier.PREMIUM.value == "premium"


# ---------------------------------------------------------------------------
# TestAdvancedCollaborativeFilter
# ---------------------------------------------------------------------------

class TestAdvancedCollaborativeFilter:
    def test_cold_start_empty(self):
        cf = AdvancedCollaborativeFilter()
        results = cf.recommend("new_user")
        assert results == []

    def test_cold_start_with_popular(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 5.0)
        cf.add_interaction("u2", "p1", 4.0)
        cf.add_interaction("u2", "p2", 3.0)
        # new_user는 콜드 스타트 → 인기 상품
        results = cf.recommend("new_user")
        assert len(results) > 0
        assert results[0].strategy == "cold_start_popular"

    def test_user_similarity_no_common(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 5.0)
        cf.add_interaction("u2", "p2", 4.0)
        sim = cf.user_similarity("u1", "u2")
        assert sim == 0.0

    def test_user_similarity_identical(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 5.0)
        cf.add_interaction("u2", "p1", 5.0)
        sim = cf.user_similarity("u1", "u2")
        assert abs(sim - 1.0) < 0.01

    def test_user_similarity_partial(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 4.0)
        cf.add_interaction("u1", "p2", 3.0)
        cf.add_interaction("u2", "p1", 4.0)
        cf.add_interaction("u2", "p3", 2.0)
        sim = cf.user_similarity("u1", "u2")
        assert 0 < sim < 1.0

    def test_recommend_user_based(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 5.0)
        cf.add_interaction("u2", "p1", 5.0)
        cf.add_interaction("u2", "p2", 4.0)
        results = cf.recommend("u1")
        pids = [r.product_id for r in results]
        assert "p2" in pids
        assert "p1" not in pids

    def test_recommend_returns_recommendation_result(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 5.0)
        cf.add_interaction("u2", "p1", 5.0)
        cf.add_interaction("u2", "p2", 4.0)
        results = cf.recommend("u1")
        assert all(isinstance(r, RecommendationResult) for r in results)

    def test_item_similarity(self):
        cf = AdvancedCollaborativeFilter()
        # u1, u2 둘 다 p1, p2 구매
        cf.add_interaction("u1", "p1", 5.0)
        cf.add_interaction("u1", "p2", 5.0)
        cf.add_interaction("u2", "p1", 4.0)
        cf.add_interaction("u2", "p2", 4.0)
        sim = cf.item_similarity("p1", "p2")
        assert sim > 0

    def test_recommend_item_based(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 5.0)
        cf.add_interaction("u1", "p2", 4.0)
        cf.add_interaction("u2", "p1", 4.0)
        cf.add_interaction("u2", "p2", 3.0)
        results = cf.recommend_item_based("p1")
        assert any(r.product_id == "p2" for r in results)

    def test_add_event(self):
        cf = AdvancedCollaborativeFilter()
        event = UserEvent(user_id="u1", event_type=EventType.PURCHASE, product_id="p1")
        cf.add_event(event)
        # 구매 이벤트는 가중치 5.0
        assert cf._user_matrix["u1"]["p1"] == 5.0

    def test_event_weight_accumulation(self):
        cf = AdvancedCollaborativeFilter()
        view = UserEvent(user_id="u1", event_type=EventType.VIEW, product_id="p1")
        purchase = UserEvent(user_id="u1", event_type=EventType.PURCHASE, product_id="p1")
        cf.add_event(view)     # 1.0
        cf.add_event(purchase) # 5.0
        assert cf._user_matrix["u1"]["p1"] == 6.0

    def test_popular_products(self):
        cf = AdvancedCollaborativeFilter()
        cf.add_interaction("u1", "p1", 10.0)
        cf.add_interaction("u2", "p1", 8.0)
        cf.add_interaction("u1", "p2", 2.0)
        results = cf.get_popular_products(top_n=2)
        assert results[0].product_id == "p1"


# ---------------------------------------------------------------------------
# TestAdvancedContentBasedFilter
# ---------------------------------------------------------------------------

class TestAdvancedContentBasedFilter:
    def _make_cbf(self):
        cbf = AdvancedContentBasedFilter()
        cbf.add_product_dict("p1", category="electronics", brand="Samsung",
                             price=100000, tags=["phone", "android"])
        cbf.add_product_dict("p2", category="electronics", brand="Samsung",
                             price=90000, tags=["phone", "android", "5g"])
        cbf.add_product_dict("p3", category="clothing", brand="Nike",
                             price=50000, tags=["shirt"])
        return cbf

    def test_similar_returns_list(self):
        cbf = self._make_cbf()
        results = cbf.similar("p1")
        assert isinstance(results, list)

    def test_similar_same_category_scores_higher(self):
        cbf = self._make_cbf()
        results = cbf.similar("p1")
        scores = {r.product_id: r.score for r in results}
        assert scores["p2"] > scores.get("p3", 0)

    def test_similar_unknown_product(self):
        cbf = AdvancedContentBasedFilter()
        assert cbf.similar("unknown") == []

    def test_attribute_score_category_match(self):
        cbf = AdvancedContentBasedFilter()
        p1 = ProductVector("p1", "electronics", "Apple", PriceTier.HIGH, ["phone"])
        p2 = ProductVector("p2", "electronics", "Apple", PriceTier.HIGH, ["phone"])
        score = cbf.attribute_score(p1, p2)
        # category 3.0 + brand 2.0 + price_tier 1.5 + tags 1.0 = 7.5
        assert score == 7.5

    def test_attribute_score_no_match(self):
        cbf = AdvancedContentBasedFilter()
        p1 = ProductVector("p1", "electronics", "Apple", PriceTier.HIGH, ["phone"])
        p2 = ProductVector("p2", "clothing", "Nike", PriceTier.LOW, ["shirt"])
        score = cbf.attribute_score(p1, p2)
        assert score == 0.0

    def test_tag_jaccard(self):
        cbf = AdvancedContentBasedFilter()
        p1 = ProductVector("p1", "electronics", tags=["a", "b", "c"])
        p2 = ProductVector("p2", "electronics", tags=["a", "b", "d"])
        score = cbf.attribute_score(p1, p2)
        # category 3.0 + price_tier (both MID) 1.5 + tags: jaccard = 2/4 = 0.5 * 1.0 = 0.5 → total 5.0
        assert abs(score - 5.0) < 0.01

    def test_tfidf_similar_descriptions(self):
        cbf = AdvancedContentBasedFilter()
        cbf.add_product_dict("p1", category="electronics", description="wireless bluetooth headphone noise cancelling")
        cbf.add_product_dict("p2", category="electronics", description="wireless bluetooth speaker noise cancelling")
        cbf.add_product_dict("p3", category="clothing", description="summer dress cotton lightweight")
        score_12 = cbf._tfidf_score("p1", "p2")
        score_13 = cbf._tfidf_score("p1", "p3")
        assert score_12 > score_13

    def test_recommend_for_user(self):
        cbf = self._make_cbf()
        results = cbf.recommend_for_user(["p1"], top_n=5)
        assert isinstance(results, list)
        assert all(r.product_id != "p1" for r in results)

    def test_price_tier_mapping(self):
        from src.ai_recommendation.content_based_filter import _price_to_tier
        assert _price_to_tier(5000) == PriceTier.LOW
        assert _price_to_tier(30000) == PriceTier.MID
        assert _price_to_tier(100000) == PriceTier.HIGH
        assert _price_to_tier(300000) == PriceTier.PREMIUM


# ---------------------------------------------------------------------------
# TestPersonalizationEngine
# ---------------------------------------------------------------------------

class TestPersonalizationEngine:
    def _make_pe(self):
        pe = PersonalizationEngine()
        pe.register_product("p1", category="electronics", brand="Samsung", price_tier="high")
        pe.register_product("p2", category="electronics", brand="Apple", price_tier="premium")
        pe.register_product("p3", category="clothing", brand="Nike", price_tier="mid")
        return pe

    def test_record_event_updates_profile(self):
        pe = self._make_pe()
        event = UserEvent(user_id="u1", event_type=EventType.PURCHASE, product_id="p1")
        pe.record_event(event)
        profile = pe.get_profile("u1")
        assert "electronics" in profile.category_preferences
        assert profile.category_preferences["electronics"] == 5.0

    def test_multiple_events_accumulate(self):
        pe = self._make_pe()
        pe.record_event(UserEvent("u1", EventType.VIEW, "p1"))
        pe.record_event(UserEvent("u1", EventType.PURCHASE, "p1"))
        profile = pe.get_profile("u1")
        # view: 1.0 + purchase: 5.0 = 6.0
        assert profile.category_preferences.get("electronics", 0) == 6.0

    def test_purchase_history_updated(self):
        pe = self._make_pe()
        pe.record_event(UserEvent("u1", EventType.PURCHASE, "p1"))
        profile = pe.get_profile("u1")
        assert "p1" in profile.purchase_history

    def test_wishlist_updated(self):
        pe = self._make_pe()
        pe.record_event(UserEvent("u1", EventType.WISHLIST, "p2"))
        profile = pe.get_profile("u1")
        assert "p2" in profile.wishlist

    def test_taste_vector_normalized(self):
        pe = self._make_pe()
        pe.record_event(UserEvent("u1", EventType.PURCHASE, "p1"))
        pe.record_event(UserEvent("u1", EventType.VIEW, "p3"))
        vector = pe.get_taste_vector("u1")
        assert "categories" in vector
        # 정규화: 합이 1.0
        cat_sum = sum(vector["categories"].values())
        assert abs(cat_sum - 1.0) < 0.01

    def test_set_segment(self):
        pe = PersonalizationEngine()
        pe.set_segment("u1", "vip")
        profile = pe.get_profile("u1")
        assert profile.segment == "vip"

    def test_strategy_weights_vip(self):
        pe = PersonalizationEngine()
        pe.set_segment("u1", "vip")
        weights = pe.get_strategy_weights("u1")
        assert "collaborative" in weights
        assert weights["trending"] < weights["collaborative"]

    def test_strategy_weights_new(self):
        pe = PersonalizationEngine()
        pe.set_segment("u1", "new")
        weights = pe.get_strategy_weights("u1")
        assert weights["trending"] > weights["collaborative"]

    def test_session_context(self):
        pe = self._make_pe()
        pe.record_event(UserEvent("u1", EventType.VIEW, "p1",
                                   timestamp=datetime.utcnow()))
        pe.record_event(UserEvent("u1", EventType.VIEW, "p2",
                                   timestamp=datetime.utcnow() - timedelta(hours=1)))
        ctx = pe.get_session_context("u1", window_minutes=90)
        assert "p1" in ctx
        assert "p2" in ctx

    def test_session_context_expired(self):
        pe = self._make_pe()
        old_ts = datetime.utcnow() - timedelta(hours=2)
        pe.record_event(UserEvent("u1", EventType.VIEW, "p1", timestamp=old_ts))
        ctx = pe.get_session_context("u1", window_minutes=30)
        assert "p1" not in ctx

    def test_score_products(self):
        pe = self._make_pe()
        pe.record_event(UserEvent("u1", EventType.PURCHASE, "p1"))
        results = pe.score_products("u1", ["p2", "p3"], top_n=5)
        # p2는 electronics (같은 카테고리) → 점수 있어야
        assert any(r.product_id == "p2" for r in results)


# ---------------------------------------------------------------------------
# TestAITrendingAnalyzer
# ---------------------------------------------------------------------------

class TestAITrendingAnalyzer:
    def test_empty_trending(self):
        ta = AITrendingAnalyzer()
        results = ta.get_trending(top_n=5)
        assert results == []

    def test_trending_sorted_by_score(self):
        ta = AITrendingAnalyzer()
        now = datetime.utcnow()
        ta.record("p1", event_type="purchase", timestamp=now)
        ta.record("p2", event_type="view", timestamp=now)
        results = ta.get_trending(top_n=2)
        assert results[0].product_id == "p1"  # purchase weight > view

    def test_time_decay(self):
        ta = AITrendingAnalyzer(decay_hours=1.0)
        old_ts = datetime.utcnow() - timedelta(hours=5)
        now_ts = datetime.utcnow()
        ta.record("p_old", event_type="purchase", timestamp=old_ts)
        ta.record("p_new", event_type="purchase", timestamp=now_ts)
        now = datetime.utcnow()
        score_old = ta.trending_score("p_old", now=now)
        score_new = ta.trending_score("p_new", now=now)
        assert score_new > score_old

    def test_trending_by_category(self):
        ta = AITrendingAnalyzer()
        now = datetime.utcnow()
        ta.record("p1", event_type="purchase", category="electronics", timestamp=now)
        ta.record("p2", event_type="view", category="clothing", timestamp=now)
        results_elec = ta.get_trending(top_n=5, category="electronics")
        pids = [r.product_id for r in results_elec]
        assert "p1" in pids
        assert "p2" not in pids

    def test_surging_detection(self):
        ta = AITrendingAnalyzer()
        now = datetime.utcnow()
        # p1: 최근에만 이벤트 (급상승)
        for _ in range(5):
            ta.record("p1", event_type="purchase", timestamp=now - timedelta(hours=1))
        # p2: 이전 기간에 이벤트
        for _ in range(5):
            ta.record("p2", event_type="purchase", timestamp=now - timedelta(hours=40))

        results = ta.get_surging(top_n=5, window_hours=24.0, compare_window_hours=48.0, now=now)
        pids = [r.product_id for r in results]
        assert "p1" in pids

    def test_seasonal_returns_results(self):
        ta = AITrendingAnalyzer()
        now = datetime.utcnow()
        ta.record("p1", event_type="purchase", category="electronics", timestamp=now)
        results = ta.get_seasonal(top_n=5, now=now)
        assert isinstance(results, list)

    def test_trending_by_category_dict(self):
        ta = AITrendingAnalyzer()
        now = datetime.utcnow()
        ta.record("p1", category="electronics", timestamp=now)
        ta.record("p2", category="clothing", timestamp=now)
        result = ta.get_trending_by_category(top_n=3, now=now)
        assert "electronics" in result
        assert "clothing" in result

    def test_trending_score_zero_for_unknown(self):
        ta = AITrendingAnalyzer()
        score = ta.trending_score("unknown")
        assert score == 0.0


# ---------------------------------------------------------------------------
# TestCrossSellEngine
# ---------------------------------------------------------------------------

class TestCrossSellEngine:
    def _make_cse(self):
        cse = CrossSellEngine()
        cse.register_product("p1", "electronics", 100000, "high")
        cse.register_product("p2", "electronics", 120000, "high")
        cse.register_product("p3", "electronics", 200000, "premium")
        cse.register_product("p4", "clothing", 50000, "mid")
        # 트랜잭션 추가
        cse.add_transaction("t1", ["p1", "p2"])
        cse.add_transaction("t2", ["p1", "p2", "p4"])
        cse.add_transaction("t3", ["p1", "p3"])
        cse.add_transaction("t4", ["p2", "p4"])
        return cse

    def test_association_rules(self):
        cse = self._make_cse()
        rules = cse.get_association_rules("p1")
        assert len(rules) > 0
        assert all("product_id" in r and "confidence" in r and "lift" in r for r in rules)

    def test_association_rules_empty_transactions(self):
        cse = CrossSellEngine()
        rules = cse.get_association_rules("p1")
        assert rules == []

    def test_cross_sell(self):
        cse = CrossSellEngine()
        cse.register_product("p1", "electronics", 100000, "high")
        cse.register_product("p2", "electronics", 120000, "high")
        cse.register_product("p3", "accessories", 20000, "low")
        # t1, t2: p1+p2 together (support_pair=2/3, confidence=2/2=1.0, support(p2)=2/3, lift=1.5)
        cse.add_transaction("t1", ["p1", "p2"])
        cse.add_transaction("t2", ["p1", "p2"])
        cse.add_transaction("t3", ["p1", "p3"])
        results = cse.cross_sell(["p1"], top_n=5)
        assert isinstance(results, list)
        pids = [r.product_id for r in results]
        assert "p2" in pids

    def test_cross_sell_excludes_input(self):
        cse = self._make_cse()
        results = cse.cross_sell(["p1", "p2"], top_n=5)
        pids = [r.product_id for r in results]
        assert "p1" not in pids
        assert "p2" not in pids

    def test_upsell(self):
        cse = self._make_cse()
        results = cse.upsell("p1", top_n=3)
        assert isinstance(results, list)
        # p3는 같은 카테고리 + 더 비쌈
        pids = [r.product_id for r in results]
        assert "p3" in pids

    def test_upsell_unknown_product(self):
        cse = CrossSellEngine()
        results = cse.upsell("unknown")
        assert results == []

    def test_bundle_recommend(self):
        cse = CrossSellEngine()
        cse.register_bundle("b1", ["p1", "p2", "p3"])
        results = cse.bundle_recommend("p1", top_n=5)
        pids = [r.product_id for r in results]
        assert "p2" in pids or "p3" in pids

    def test_compute_support(self):
        cse = self._make_cse()
        # p1은 t1, t2, t3 → 3/4 = 0.75
        support = cse._compute_support(frozenset(["p1"]))
        assert abs(support - 0.75) < 0.01

    def test_association_rules_sorted_by_lift(self):
        cse = self._make_cse()
        rules = cse.get_association_rules("p1", min_confidence=0.0, min_lift=0.0)
        if len(rules) >= 2:
            assert rules[0]["lift"] >= rules[1]["lift"]


# ---------------------------------------------------------------------------
# TestFeedbackLoop
# ---------------------------------------------------------------------------

class TestFeedbackLoop:
    def test_record_impression(self):
        fl = FeedbackLoop()
        fl.record_impression("r1", "u1", "p1", "ensemble")
        assert fl._stats["ensemble"]["impressions"] == 1

    def test_record_click(self):
        fl = FeedbackLoop()
        fl.record_impression("r1", "u1", "p1", "ensemble")
        fl.record_click("r1")
        assert fl._stats["ensemble"]["clicks"] == 1

    def test_record_purchase(self):
        fl = FeedbackLoop()
        fl.record_impression("r1", "u1", "p1", "ensemble")
        fl.record_click("r1")
        fl.record_purchase("r1")
        assert fl._stats["ensemble"]["purchases"] == 1

    def test_ctr(self):
        fl = FeedbackLoop()
        fl.record_impression("r1", "u1", "p1", "ensemble")
        fl.record_impression("r2", "u2", "p2", "ensemble")
        fl.record_click("r1")
        assert fl.ctr("ensemble") == 0.5

    def test_cvr(self):
        fl = FeedbackLoop()
        fl.record_impression("r1", "u1", "p1", "ensemble")
        fl.record_click("r1")
        fl.record_purchase("r1")
        assert fl.cvr("ensemble") == 1.0

    def test_ctr_no_impressions(self):
        fl = FeedbackLoop()
        assert fl.ctr("ensemble") == 0.0

    def test_cvr_no_clicks(self):
        fl = FeedbackLoop()
        assert fl.cvr("ensemble") == 0.0

    def test_get_metrics(self):
        fl = FeedbackLoop()
        fl.record_impression("r1", "u1", "p1", "trending")
        metrics = fl.get_metrics()
        assert "trending" in metrics
        assert "impressions" in metrics["trending"]

    def test_auto_adjust_weights_no_data(self):
        fl = FeedbackLoop()
        weights = fl.auto_adjust_weights()
        assert isinstance(weights, dict)
        assert len(weights) > 0

    def test_auto_adjust_weights_with_data(self):
        fl = FeedbackLoop()
        # collaborative가 높은 성과
        for i in range(10):
            fl.record_impression(f"r{i}", "u1", f"p{i}", "collaborative_user")
            fl.record_click(f"r{i}")
            fl.record_purchase(f"r{i}")
        # trending은 낮은 성과
        for i in range(10, 20):
            fl.record_impression(f"r{i}", "u2", f"p{i}", "trending")
        weights = fl.auto_adjust_weights()
        assert isinstance(weights, dict)

    def test_set_strategy_weight(self):
        fl = FeedbackLoop()
        fl.set_strategy_weight("ensemble", 0.5)
        assert fl._strategy_weights["ensemble"] == 0.5

    def test_precision_equals_cvr(self):
        fl = FeedbackLoop()
        fl.record_impression("r1", "u1", "p1", "ensemble")
        fl.record_click("r1")
        assert fl.precision("ensemble") == fl.cvr("ensemble")


# ---------------------------------------------------------------------------
# TestAIRecommendationEngine
# ---------------------------------------------------------------------------

class TestAIRecommendationEngine:
    def _make_engine(self):
        engine = AIRecommendationEngine()
        # 상품 등록
        for pid, cat, brand, price in [
            ("p1", "electronics", "Samsung", 100000),
            ("p2", "electronics", "Apple", 150000),
            ("p3", "clothing", "Nike", 50000),
            ("p4", "electronics", "Samsung", 90000),
        ]:
            engine.content_based.add_product_dict(pid, category=cat, brand=brand, price=price)
            engine.personalization.register_product(pid, category=cat, brand=brand,
                                                     price_tier="high" if price >= 100000 else "mid")
            engine.cross_sell.register_product(pid, cat, price)
        # 이벤트 기록
        engine.record_event(UserEvent("u1", EventType.PURCHASE, "p1"))
        engine.record_event(UserEvent("u1", EventType.VIEW, "p2"))
        engine.record_event(UserEvent("u2", EventType.PURCHASE, "p1"))
        engine.record_event(UserEvent("u2", EventType.PURCHASE, "p4"))
        return engine

    def test_recommend_ensemble(self):
        engine = self._make_engine()
        results = engine.recommend("u1", top_n=5, strategy="ensemble")
        assert isinstance(results, list)
        assert all(isinstance(r, RecommendationResult) for r in results)

    def test_recommend_collaborative(self):
        engine = self._make_engine()
        results = engine.recommend("u1", top_n=5, strategy="collaborative")
        assert isinstance(results, list)

    def test_recommend_content(self):
        engine = self._make_engine()
        results = engine.recommend("u1", top_n=5, strategy="content")
        assert isinstance(results, list)

    def test_recommend_trending(self):
        engine = self._make_engine()
        results = engine.recommend("u1", top_n=5, strategy="trending")
        assert isinstance(results, list)

    def test_caching(self):
        engine = self._make_engine()
        r1 = engine.recommend("u1", top_n=5, strategy="ensemble", use_cache=True)
        r2 = engine.recommend("u1", top_n=5, strategy="ensemble", use_cache=True)
        # 캐시 히트 → 동일한 결과
        assert [r.product_id for r in r1] == [r.product_id for r in r2]

    def test_cache_invalidation(self):
        engine = self._make_engine()
        engine.recommend("u1", top_n=5, use_cache=True)
        assert len(engine._cache) > 0
        engine.invalidate_cache("u1")
        assert len(engine._cache) == 0

    def test_invalidate_all_cache(self):
        engine = self._make_engine()
        engine.recommend("u1", use_cache=True)
        engine.recommend("u2", use_cache=True)
        engine.invalidate_cache()
        assert len(engine._cache) == 0

    def test_get_cross_sell(self):
        engine = self._make_engine()
        engine.cross_sell.add_transaction("t1", ["p1", "p2"])
        engine.cross_sell.add_transaction("t2", ["p1", "p3"])
        results = engine.get_cross_sell(["p1"], top_n=5)
        assert isinstance(results, list)

    def test_get_trending(self):
        engine = self._make_engine()
        results = engine.get_trending(top_n=5)
        assert isinstance(results, list)

    def test_get_trending_by_category(self):
        engine = self._make_engine()
        results = engine.get_trending(top_n=5, category="electronics")
        assert isinstance(results, list)

    def test_ab_experiment(self):
        engine = AIRecommendationEngine()
        engine.register_ab_experiment("exp1", active=True)
        strategy = engine.get_ab_strategy("u1", "exp1")
        assert strategy in ["ensemble", "collaborative", "content", "trending"]

    def test_ab_experiment_inactive(self):
        engine = AIRecommendationEngine()
        engine.register_ab_experiment("exp1", active=False)
        strategy = engine.get_ab_strategy("u1", "exp1")
        assert strategy == "ensemble"


# ---------------------------------------------------------------------------
# TestAutoRecommender
# ---------------------------------------------------------------------------

class TestAutoRecommender:
    def test_record_purchase(self):
        ar = AutoRecommender()
        ar.record_purchase("u1", "p1")
        assert len(ar._purchase_history["u1"]) == 1

    def test_repurchase_date_single_purchase(self):
        ar = AutoRecommender()
        ar.record_purchase("u1", "p1")
        # 단일 구매 → None 반환
        result = ar.estimate_repurchase_date("u1")
        assert result is None

    def test_repurchase_date_multiple_purchases(self):
        ar = AutoRecommender()
        now = datetime.utcnow()
        ar.record_purchase("u1", "p1", timestamp=now - timedelta(days=30))
        ar.record_purchase("u1", "p2", timestamp=now)
        result = ar.estimate_repurchase_date("u1")
        assert result is not None
        # 30일 주기 → 다음 구매는 now + 30일 근처
        expected = now + timedelta(days=30)
        diff = abs((result - expected).total_seconds())
        assert diff < 86400  # 1일 오차 허용

    def test_churn_risk_detection(self):
        ar = AutoRecommender()
        now = datetime.utcnow()
        ar.record_activity("u1", timestamp=now - timedelta(days=40))
        ar.record_activity("u2", timestamp=now - timedelta(days=10))
        churns = ar.get_churn_risk_users(inactivity_days=30, now=now)
        assert "u1" in churns
        assert "u2" not in churns

    def test_churn_prevention_recommendations(self):
        ar = AutoRecommender()
        results = ar.get_churn_prevention_recommendations("u1", top_n=5)
        assert isinstance(results, list)

    def test_repurchase_recommendations_not_due(self):
        ar = AutoRecommender()
        now = datetime.utcnow()
        # 30일 주기인데 아직 15일밖에 안 됨
        ar.record_purchase("u1", "p1", timestamp=now - timedelta(days=30))
        ar.record_purchase("u1", "p2", timestamp=now - timedelta(days=15))
        results = ar.get_repurchase_recommendations("u1", now=now)
        assert results == []

    def test_generate_daily_recommendations(self):
        ar = AutoRecommender()
        result = ar.generate_daily_recommendations(["u1", "u2"], top_n=5)
        assert "u1" in result
        assert "u2" in result
        assert isinstance(result["u1"], list)

    def test_new_product_alerts(self):
        ar = AutoRecommender()
        now = datetime.utcnow()
        ar.register_new_product("new_p1", timestamp=now - timedelta(days=1))
        ar._engine.personalization.register_product("new_p1", category="electronics")
        ar._engine.personalization.record_event(
            UserEvent("u1", EventType.PURCHASE, "new_p1")
        )
        results = ar.get_new_product_alerts("u1", top_n=5, now=now)
        assert isinstance(results, list)

    def test_new_product_alerts_empty_when_no_new(self):
        ar = AutoRecommender()
        results = ar.get_new_product_alerts("u1", top_n=5)
        assert results == []


# ---------------------------------------------------------------------------
# TestAPIBlueprint (Flask 통합 테스트)
# ---------------------------------------------------------------------------

class TestAPIBlueprint:
    def _make_app(self):
        from flask import Flask
        from src.api.ai_recommendation_api import ai_recommendation_bp
        app = Flask(__name__)
        app.register_blueprint(ai_recommendation_bp)
        return app

    def test_status_endpoint(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_personalized_recommend(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/u1?strategy=ensemble&top_n=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "recommendations" in data
        assert data["user_id"] == "u1"

    def test_trending_endpoint(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/trending?top_n=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "recommendations" in data

    def test_trending_by_category(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/trending/electronics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] == "electronics"

    def test_record_event_valid(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.post(
            "/api/v1/ai-recommend/event",
            json={"user_id": "u1", "event_type": "view", "product_id": "p1"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "recorded"

    def test_record_event_missing_fields(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.post(
            "/api/v1/ai-recommend/event",
            json={"user_id": "u1"},
        )
        assert resp.status_code == 400

    def test_record_event_invalid_type(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.post(
            "/api/v1/ai-recommend/event",
            json={"user_id": "u1", "event_type": "invalid", "product_id": "p1"},
        )
        assert resp.status_code == 400

    def test_metrics_endpoint(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "metrics" in data
        assert "strategy_weights" in data

    def test_feedback_impression(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.post(
            "/api/v1/ai-recommend/feedback",
            json={"action": "impression", "rec_id": "rec1",
                  "user_id": "u1", "product_id": "p1", "strategy": "ensemble"},
        )
        assert resp.status_code == 201

    def test_feedback_click(self):
        app = self._make_app()
        client = app.test_client()
        client.post("/api/v1/ai-recommend/feedback",
                    json={"action": "impression", "rec_id": "rec1",
                          "user_id": "u1", "product_id": "p1", "strategy": "ensemble"})
        resp = client.post(
            "/api/v1/ai-recommend/feedback",
            json={"action": "click", "rec_id": "rec1"},
        )
        assert resp.status_code == 201

    def test_feedback_invalid_action(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.post(
            "/api/v1/ai-recommend/feedback",
            json={"action": "invalid_action"},
        )
        assert resp.status_code == 400

    def test_cross_sell_endpoint(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/u1/cross-sell?product_ids=p1,p2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "recommendations" in data

    def test_cross_sell_missing_product_ids(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/u1/cross-sell")
        assert resp.status_code == 400

    def test_repurchase_endpoint(self):
        app = self._make_app()
        client = app.test_client()
        resp = client.get("/api/v1/ai-recommend/u1/repurchase?top_n=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "user_id" in data
        assert "recommendations" in data


# ---------------------------------------------------------------------------
# TestBotCommands
# ---------------------------------------------------------------------------

class TestBotCommands:
    def test_cmd_ai_recommend_no_user(self):
        from src.bot.commands import cmd_ai_recommend
        result = cmd_ai_recommend('')
        assert '사용법' in result

    def test_cmd_ai_recommend_with_user(self):
        from src.bot.commands import cmd_ai_recommend
        result = cmd_ai_recommend('u1')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_trending_no_category(self):
        from src.bot.commands import cmd_trending
        result = cmd_trending()
        assert isinstance(result, str)

    def test_cmd_trending_with_category(self):
        from src.bot.commands import cmd_trending
        result = cmd_trending('electronics')
        assert isinstance(result, str)

    def test_cmd_cross_sell_no_product(self):
        from src.bot.commands import cmd_cross_sell
        result = cmd_cross_sell('')
        assert '사용법' in result

    def test_cmd_cross_sell_with_product(self):
        from src.bot.commands import cmd_cross_sell
        result = cmd_cross_sell('p1')
        assert isinstance(result, str)

    def test_cmd_recommend_metrics(self):
        from src.bot.commands import cmd_recommend_metrics
        result = cmd_recommend_metrics()
        assert isinstance(result, str)
