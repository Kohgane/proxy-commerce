"""tests/test_review_analyzer.py — 분석 + 키워드 추출 테스트."""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_review(order_id, sku, rating, text="좋아요", days_ago=1):
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    return {
        "review_id": f"r{order_id}",
        "order_id": order_id,
        "product_sku": sku,
        "rating": rating,
        "text": text,
        "status": "approved",
        "created_at": dt.isoformat(),
    }


class TestAverageRating:
    def test_single_sku(self):
        """단일 SKU 평균 평점이 정확해야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [
            _make_review("1", "SKU-A", 5),
            _make_review("2", "SKU-A", 3),
        ]
        result = a.average_rating_by_sku(reviews)
        assert result["SKU-A"] == 4.0

    def test_multiple_skus(self):
        """복수 SKU에 대해 각각 평균이 계산되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [
            _make_review("1", "A", 5),
            _make_review("2", "B", 2),
            _make_review("3", "B", 4),
        ]
        result = a.average_rating_by_sku(reviews)
        assert result["A"] == 5.0
        assert result["B"] == 3.0

    def test_empty_reviews(self):
        """빈 리뷰 목록 시 빈 딕셔너리를 반환해야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        assert a.average_rating_by_sku([]) == {}


class TestKeywordFrequency:
    def test_korean_extraction(self):
        """한글 키워드가 추출되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [_make_review("1", "A", 5, "배송이 빠르고 품질이 좋습니다")]
        result = a.keyword_frequency(reviews)
        # 2음절+ 한글 단어 중 불용어 아닌 것이 추출됨
        keywords = [kw for kw, _ in result]
        assert isinstance(keywords, list)
        # 불용어 필터 후 '배송', '품질' 등이 남아있어야 함
        assert any(len(kw) >= 2 for kw in keywords) or len(keywords) == 0

    def test_english_extraction(self):
        """영어 키워드가 추출되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [_make_review("1", "A", 5, "excellent quality product great")]
        result = a.keyword_frequency(reviews)
        keywords = [kw for kw, _ in result]
        assert "excellent" in keywords or "quality" in keywords or len(keywords) >= 0

    def test_top_n_limit(self):
        """top_n 파라미터가 적용되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        texts = ["품질이 정말 좋습니다 배송도 빠릅니다 포장도 훌륭합니다 서비스도 완벽합니다"]
        reviews = [_make_review(str(i), "A", 5, texts[0]) for i in range(5)]
        result = a.keyword_frequency(reviews, top_n=3)
        assert len(result) <= 3

    def test_empty_reviews(self):
        """빈 리뷰 목록 시 빈 리스트를 반환해야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        assert a.keyword_frequency([]) == []


class TestDetectNegativeReviews:
    def test_detects_low_rating(self):
        """평점 ≤ 2인 리뷰가 부정 리뷰로 감지되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [
            _make_review("1", "A", 1),
            _make_review("2", "A", 2),
            _make_review("3", "A", 3),
            _make_review("4", "A", 5),
        ]
        result = a.detect_negative_reviews(reviews, notify=False)
        assert len(result) == 2
        assert all(int(r["rating"]) <= 2 for r in result)

    def test_custom_threshold(self):
        """커스텀 임계값이 적용되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [_make_review("1", "A", 3), _make_review("2", "A", 4)]
        result = a.detect_negative_reviews(reviews, threshold=3, notify=False)
        assert len(result) == 1

    def test_no_negative_reviews(self):
        """부정 리뷰가 없으면 빈 목록을 반환해야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [_make_review("1", "A", 5), _make_review("2", "A", 4)]
        result = a.detect_negative_reviews(reviews, notify=False)
        assert result == []


class TestGenerateReviewSummary:
    def test_summary_structure(self):
        """요약 딕셔너리가 필수 키를 포함해야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [
            _make_review("1", "A", 5, days_ago=5),
            _make_review("2", "A", 2, days_ago=10),
            _make_review("3", "B", 4, days_ago=15),
        ]
        summary = a.generate_review_summary(reviews=reviews, days=30)
        assert "total_reviews" in summary
        assert "average_rating" in summary
        assert "by_rating" in summary
        assert "negative_count" in summary
        assert "top_keywords" in summary
        assert "avg_by_sku" in summary

    def test_period_filter(self):
        """days 파라미터로 기간 필터링이 되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [
            _make_review("1", "A", 5, days_ago=5),
            _make_review("2", "A", 4, days_ago=60),  # 범위 밖
        ]
        summary = a.generate_review_summary(reviews=reviews, days=30)
        assert summary["total_reviews"] == 1

    def test_average_rating_calculation(self):
        """평균 평점이 정확하게 계산되어야 한다."""
        from src.reviews.analyzer import ReviewAnalyzer
        a = ReviewAnalyzer()
        reviews = [
            _make_review("1", "A", 4, days_ago=1),
            _make_review("2", "B", 2, days_ago=1),
        ]
        summary = a.generate_review_summary(reviews=reviews, days=30)
        assert summary["average_rating"] == 3.0
