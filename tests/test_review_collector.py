"""tests/test_review_collector.py — 리뷰 수집 + 중복 감지 테스트."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


SAMPLE_REVIEW = {
    "order_id": "ORD-001",
    "product_sku": "PTR-TNK-001",
    "rating": 5,
    "text": "정말 좋은 제품입니다!",
    "platform": "shopify",
    "customer_email": "test@example.com",
}


class TestReviewCollector:
    def _make_collector(self, enabled=True):
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "1" if enabled else "0"}):
            from src.reviews.collector import ReviewCollector
            return ReviewCollector()

    def test_is_enabled_when_env_set(self):
        """환경변수가 설정되면 활성화 상태여야 한다."""
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "1"}):
            from src.reviews.collector import ReviewCollector
            c = ReviewCollector()
            assert c.is_enabled() is True

    def test_is_disabled_by_default(self):
        """기본값은 비활성화여야 한다."""
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "0"}):
            from src.reviews.collector import ReviewCollector
            c = ReviewCollector()
            assert c.is_enabled() is False

    def test_submit_review_disabled_raises(self):
        """비활성화 시 RuntimeError가 발생해야 한다."""
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "0"}):
            from src.reviews.collector import ReviewCollector
            c = ReviewCollector()
            try:
                c.submit_review(SAMPLE_REVIEW)
                assert False, "RuntimeError 미발생"
            except RuntimeError:
                pass

    def test_submit_review_missing_fields_raises(self):
        """필수 필드 누락 시 ValueError가 발생해야 한다."""
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "1"}):
            from src.reviews.collector import ReviewCollector
            c = ReviewCollector()
            with patch.object(c, '_load', return_value=[]):
                try:
                    c.submit_review({"text": "좋아요"})
                    assert False, "ValueError 미발생"
                except ValueError:
                    pass

    def test_submit_review_invalid_rating(self):
        """유효하지 않은 평점(6) 시 ValueError가 발생해야 한다."""
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "1"}):
            from src.reviews.collector import ReviewCollector
            c = ReviewCollector()
            bad_review = dict(SAMPLE_REVIEW, rating=6)
            with patch.object(c, '_load', return_value=[]):
                try:
                    c.submit_review(bad_review)
                    assert False, "ValueError 미발생"
                except ValueError:
                    pass

    def test_submit_review_success(self):
        """정상 리뷰 제출 시 review_id와 status가 포함되어야 한다."""
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "1"}):
            from src.reviews.collector import ReviewCollector
            c = ReviewCollector()
            with patch.object(c, '_load', return_value=[]):
                with patch.object(c, '_save', return_value=None):
                    result = c.submit_review(SAMPLE_REVIEW)
            assert "review_id" in result
            assert result["status"] == "pending"
            assert result["rating"] == 5

    def test_duplicate_detection(self):
        """같은 order_id + product_sku 조합은 중복으로 감지해야 한다."""
        with patch.dict(os.environ, {"REVIEW_COLLECTION_ENABLED": "1"}):
            from src.reviews.collector import ReviewCollector
            c = ReviewCollector()
            existing = [dict(SAMPLE_REVIEW, review_id="abc", status="pending")]
            with patch.object(c, '_load', return_value=existing):
                try:
                    c.submit_review(SAMPLE_REVIEW)
                    assert False, "ValueError 미발생"
                except ValueError as e:
                    assert "Duplicate" in str(e)

    def test_get_reviews_filter_rating(self):
        """rating 필터가 정상 동작해야 한다."""
        from src.reviews.collector import ReviewCollector
        c = ReviewCollector()
        reviews = [
            {"review_id": "1", "order_id": "A", "product_sku": "S1", "rating": 5, "status": "pending"},
            {"review_id": "2", "order_id": "B", "product_sku": "S2", "rating": 2, "status": "pending"},
        ]
        with patch.object(c, '_load', return_value=reviews):
            result = c.get_reviews(rating=5)
        assert len(result) == 1
        assert result[0]["rating"] == 5

    def test_get_reviews_filter_status(self):
        """status 필터가 정상 동작해야 한다."""
        from src.reviews.collector import ReviewCollector
        c = ReviewCollector()
        reviews = [
            {"review_id": "1", "rating": 5, "status": "approved"},
            {"review_id": "2", "rating": 3, "status": "pending"},
        ]
        with patch.object(c, '_load', return_value=reviews):
            result = c.get_reviews(status="approved")
        assert len(result) == 1
        assert result[0]["status"] == "approved"

    def test_update_status_valid(self):
        """유효한 상태로 업데이트 시 성공해야 한다."""
        from src.reviews.collector import ReviewCollector
        c = ReviewCollector()
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {"review_id": "abc", "status": "pending"}
        ]
        with patch('src.utils.sheets.open_sheet', return_value=mock_ws):
            result = c.update_status("abc", "approved")
        assert result is True

    def test_update_status_invalid_raises(self):
        """유효하지 않은 상태 시 ValueError가 발생해야 한다."""
        from src.reviews.collector import ReviewCollector
        c = ReviewCollector()
        try:
            c.update_status("abc", "unknown")
            assert False, "ValueError 미발생"
        except ValueError:
            pass
