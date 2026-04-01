"""tests/test_price_tracker.py — 경쟁사 가격 추적 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(autouse=True)
def enable_competitor(monkeypatch):
    monkeypatch.setenv('COMPETITOR_TRACKING_ENABLED', '1')
    monkeypatch.setenv('COMPETITOR_SHEET_NAME', 'competitors')
    monkeypatch.setenv('GOOGLE_SHEET_ID', 'fake-sheet-id')


SAMPLE_ROWS = [
    {
        'our_sku': 'SKU-A',
        'competitor_name': 'CompA',
        'competitor_url': 'https://compa.com/product',
        'competitor_price': 90000,
        'competitor_currency': 'KRW',
        'last_checked': '2026-03-01T00:00:00',
        'price_diff_pct': 11.0,  # 우리(100000) vs 경쟁(90000): (100000-90000)/90000*100 ≈ 11.1%
    },
    {
        'our_sku': 'SKU-B',
        'competitor_name': 'CompB',
        'competitor_url': '',
        'competitor_price': 120000,
        'competitor_currency': 'KRW',
        'last_checked': '2026-03-01T00:00:00',
        'price_diff_pct': -16.67,  # 우리(100000) vs 경쟁(120000): (100000-120000)/120000*100 ≈ -16.7%
    },
]


class TestGetPriceComparison:
    def test_returns_our_sku(self):
        """get_price_comparison은 our_sku를 반환해야 한다."""
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        with patch.object(tracker, '_get_all_rows', return_value=SAMPLE_ROWS[:1]):
            with patch.object(tracker, '_get_our_price_krw', return_value=100000.0):
                result = tracker.get_price_comparison('SKU-A')
        assert result['our_sku'] == 'SKU-A'

    def test_returns_competitors_list(self):
        """경쟁사 목록이 반환되어야 한다."""
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        with patch.object(tracker, '_get_all_rows', return_value=SAMPLE_ROWS[:1]):
            with patch.object(tracker, '_get_our_price_krw', return_value=100000.0):
                result = tracker.get_price_comparison('SKU-A')
        assert 'competitors' in result
        assert len(result['competitors']) == 1

    def test_best_competitor_price(self):
        """최저 경쟁사 가격이 포함되어야 한다."""
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        with patch.object(tracker, '_get_all_rows', return_value=SAMPLE_ROWS[:1]):
            with patch.object(tracker, '_get_our_price_krw', return_value=100000.0):
                result = tracker.get_price_comparison('SKU-A')
        assert result['best_competitor_price_krw'] == 90000

    def test_empty_sku_returns_no_competitors(self):
        """데이터 없는 SKU는 빈 목록을 반환해야 한다."""
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        with patch.object(tracker, '_get_all_rows', return_value=SAMPLE_ROWS):
            with patch.object(tracker, '_get_our_price_krw', return_value=0.0):
                result = tracker.get_price_comparison('SKU-NONEXISTENT')
        assert result['competitors'] == []


class TestGetOverpricedItems:
    def test_returns_overpriced(self):
        """경쟁사보다 비싼 상품이 반환되어야 한다."""
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        with patch.object(tracker, '_get_all_rows', return_value=SAMPLE_ROWS):
            with patch.object(tracker, '_convert_to_krw', side_effect=lambda p, c: float(p)):
                result = tracker.get_overpriced_items(threshold_pct=10)
        skus = [r['our_sku'] for r in result]
        assert 'SKU-A' in skus

    def test_threshold_filters_borderline(self):
        """임계값 미만은 제외되어야 한다."""
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        low_diff_row = {**SAMPLE_ROWS[0], 'price_diff_pct': 5.0}
        with patch.object(tracker, '_get_all_rows', return_value=[low_diff_row]):
            with patch.object(tracker, '_convert_to_krw', side_effect=lambda p, c: float(p)):
                result = tracker.get_overpriced_items(threshold_pct=10)
        assert result == []


class TestGetUnderpricedItems:
    def test_returns_underpriced(self):
        """경쟁사보다 저렴한 상품이 반환되어야 한다."""
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        with patch.object(tracker, '_get_all_rows', return_value=SAMPLE_ROWS):
            with patch.object(tracker, '_convert_to_krw', side_effect=lambda p, c: float(p)):
                result = tracker.get_underpriced_items(threshold_pct=10)
        skus = [r['our_sku'] for r in result]
        assert 'SKU-B' in skus


class TestTrackPrice:
    def test_track_disabled_returns_false(self, monkeypatch):
        """비활성화 시 False를 반환해야 한다."""
        monkeypatch.setenv('COMPETITOR_TRACKING_ENABLED', '0')
        # 모듈 재로드 없이 패치로 테스트
        from src.competitor import price_tracker
        original = price_tracker._ENABLED
        price_tracker._ENABLED = False
        try:
            tracker = price_tracker.CompetitorPriceTracker()
            result = tracker.track_price('SKU-A', 'CompA', 90000, 'KRW')
            assert result is False
        finally:
            price_tracker._ENABLED = original

    def test_convert_usd_to_krw(self):
        """USD → KRW 변환이 올바르게 이루어져야 한다."""
        import os
        os.environ['FX_USDKRW'] = '1380'
        from src.competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        # FX provider 없이 환경변수 폴백 사용
        with patch('src.competitor.price_tracker.CompetitorPriceTracker._convert_to_krw',
                   wraps=tracker._convert_to_krw):
            try:
                from src.fx.provider import FXProvider
                with patch.object(FXProvider, 'get_rates',
                                  return_value={'USDKRW': '1380'}):
                    krw = tracker._convert_to_krw(100, 'USD')
            except Exception:
                # FX provider 없는 경우 폴백
                krw = tracker._convert_to_krw(100, 'USD')
        assert krw == pytest.approx(138000, rel=0.01)
