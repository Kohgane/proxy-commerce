"""src/competitor/market_analyzer.py — 시장 분석.

카테고리별 평균 가격대, 포지셔닝, 트렌드 분석.
분석 결과는 Google Sheets에 기록된다.
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_SHEET_NAME = os.getenv('COMPETITOR_SHEET_NAME', 'competitors')
_ANALYSIS_SHEET = 'competitor_analysis'


class MarketAnalyzer:
    """시장 가격 분석기."""

    def __init__(self):
        self._comp_sheet = None
        self._analysis_sheet = None

    def _get_comp_sheet(self):
        """경쟁사 데이터 워크시트."""
        if self._comp_sheet is None:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            self._comp_sheet = open_sheet(sheet_id, _SHEET_NAME)
        return self._comp_sheet

    def _get_analysis_sheet(self):
        """분석 결과 워크시트."""
        if self._analysis_sheet is None:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            self._analysis_sheet = open_sheet(sheet_id, _ANALYSIS_SHEET)
        return self._analysis_sheet

    def _get_competitor_rows(self) -> list:
        try:
            ws = self._get_comp_sheet()
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("경쟁사 데이터 조회 실패: %s", exc)
            return []

    def _get_catalog_rows(self) -> list:
        try:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            catalog_sheet = os.getenv('CATALOG_SHEET_NAME', 'catalog')
            ws = open_sheet(sheet_id, catalog_sheet)
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("카탈로그 데이터 조회 실패: %s", exc)
            return []

    def _convert_to_krw(self, price: float, currency: str) -> float:
        """환율 적용 KRW 변환."""
        try:
            from ..fx.provider import FXProvider
            rates = FXProvider().get_rates()
        except Exception:
            rates = {}
        currency = currency.upper()
        if currency == 'KRW':
            return price
        elif currency == 'USD':
            return price * float(rates.get('USDKRW', os.getenv('FX_USDKRW', '1380')))
        elif currency == 'JPY':
            return price * float(rates.get('JPYKRW', os.getenv('FX_JPYKRW', '9.5')))
        elif currency == 'EUR':
            return price * float(rates.get('EURKRW', os.getenv('FX_EURKRW', '1500')))
        return price

    def analyze_category(self, category: str) -> dict:
        """카테고리별 평균 가격대 및 포지셔닝 분석.

        Args:
            category: 카테고리 이름

        Returns:
            dict with avg_price, our_position (premium/mid-range/budget), trend
        """
        catalog = self._get_catalog_rows()
        comp_rows = self._get_competitor_rows()

        # 카테고리 상품 필터링
        cat_skus = {
            str(r.get('sku')): float(r.get('price_krw') or r.get('sell_price_krw') or 0)
            for r in catalog
            if str(r.get('category', '')).lower() == category.lower()
        }

        if not cat_skus:
            return {
                'category': category,
                'avg_price': 0.0,
                'our_avg_price': 0.0,
                'our_position': 'unknown',
                'trend': 'stable',
                'sku_count': 0,
            }

        our_prices = [p for p in cat_skus.values() if p > 0]
        our_avg = sum(our_prices) / len(our_prices) if our_prices else 0.0

        # 경쟁사 가격 수집
        comp_prices = []
        for row in comp_rows:
            if str(row.get('our_sku')) in cat_skus:
                p = float(row.get('competitor_price') or 0)
                c = str(row.get('competitor_currency', 'KRW'))
                if p > 0:
                    comp_prices.append(self._convert_to_krw(p, c))

        all_prices = our_prices + comp_prices
        avg_price = sum(all_prices) / len(all_prices) if all_prices else our_avg

        # 포지셔닝 결정 (avg 대비 ±20%)
        if avg_price > 0:
            ratio = our_avg / avg_price
            if ratio >= 1.2:
                position = 'premium'
            elif ratio <= 0.8:
                position = 'budget'
            else:
                position = 'mid-range'
        else:
            position = 'unknown'

        # 간단한 트렌드 계산 (가격 분산 기반 추세 판단)
        trend = self._detect_trend(comp_prices)

        return {
            'category': category,
            'avg_price': round(avg_price),
            'our_avg_price': round(our_avg),
            'our_position': position,
            'trend': trend,
            'sku_count': len(cat_skus),
        }

    def _detect_trend(self, prices: list) -> str:
        """가격 데이터로 간단한 트렌드 감지.

        prices가 증가 추세면 'rising', 감소 추세면 'falling', 아니면 'stable'.
        """
        if len(prices) < 3:
            return 'stable'
        first_half = prices[:len(prices) // 2]
        second_half = prices[len(prices) // 2:]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        if avg_first == 0:
            return 'stable'
        change = (avg_second - avg_first) / avg_first * 100
        if change > 5:
            return 'rising'
        elif change < -5:
            return 'falling'
        return 'stable'

    def get_pricing_opportunities(self) -> list:
        """가격 조정 제안 리스트 반환.

        경쟁사보다 높은 가격인 상품에 대해 가격 인하 제안,
        경쟁사보다 낮은 가격인 상품에 대해 가격 인상 제안.
        """
        comp_rows = self._get_competitor_rows()
        catalog = self._get_catalog_rows()
        catalog_map = {
            str(r.get('sku')): float(r.get('price_krw') or r.get('sell_price_krw') or 0)
            for r in catalog
        }

        opportunities = []
        processed = set()

        for row in comp_rows:
            sku = str(row.get('our_sku', ''))
            if not sku or sku in processed:
                continue
            processed.add(sku)

            diff_pct = float(row.get('price_diff_pct') or 0)
            our_price = catalog_map.get(sku, 0)

            if diff_pct > 10:
                # 우리가 더 비쌈 → 가격 인하 제안
                opportunities.append({
                    'our_sku': sku,
                    'type': 'price_decrease',
                    'price_diff_pct': diff_pct,
                    'our_price_krw': round(our_price),
                    'competitor_name': row.get('competitor_name', ''),
                    'recommendation': f"가격 인하 고려: 경쟁사 대비 {diff_pct:.1f}% 높음",
                })
            elif diff_pct < -10:
                # 우리가 더 저렴 → 가격 인상 제안 (마진 개선)
                opportunities.append({
                    'our_sku': sku,
                    'type': 'price_increase',
                    'price_diff_pct': diff_pct,
                    'our_price_krw': round(our_price),
                    'competitor_name': row.get('competitor_name', ''),
                    'recommendation': f"가격 인상 가능: 경쟁사 대비 {abs(diff_pct):.1f}% 낮음",
                })

        return sorted(opportunities, key=lambda x: abs(x['price_diff_pct']), reverse=True)

    def save_analysis_result(self, result: dict) -> bool:
        """분석 결과를 Google Sheets에 기록한다."""
        try:
            ws = self._get_analysis_sheet()
            headers = ['category', 'avg_price', 'our_avg_price', 'our_position', 'trend',
                       'sku_count', 'analyzed_at']
            rows = ws.get_all_values()
            if not rows or rows[0] != headers:
                ws.clear()
                ws.append_row(headers)

            ws.append_row([
                result.get('category', ''),
                result.get('avg_price', 0),
                result.get('our_avg_price', 0),
                result.get('our_position', ''),
                result.get('trend', ''),
                result.get('sku_count', 0),
                datetime.utcnow().isoformat(),
            ])
            return True
        except Exception as exc:
            logger.error("분석 결과 저장 실패: %s", exc)
            return False
