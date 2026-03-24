"""src/competitor/price_tracker.py — 경쟁사 가격 추적.

Google Sheets를 백엔드로 경쟁사 상품 가격을 기록·비교한다.

환경변수:
  COMPETITOR_TRACKING_ENABLED — 활성화 여부 (기본 "0")
  COMPETITOR_SHEET_NAME       — 워크시트 이름 (기본 "competitors")
  GOOGLE_SHEET_ID             — Google Sheets ID
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_ENABLED = os.getenv('COMPETITOR_TRACKING_ENABLED', '0') == '1'
_SHEET_NAME = os.getenv('COMPETITOR_SHEET_NAME', 'competitors')

# 컬럼 헤더 정의
HEADERS = [
    'our_sku', 'competitor_name', 'competitor_url',
    'competitor_price', 'competitor_currency',
    'last_checked', 'price_diff_pct',
]


class CompetitorPriceTracker:
    """경쟁사 가격 추적기."""

    def __init__(self):
        self._sheet = None

    def _get_sheet(self):
        """Google Sheets 워크시트를 반환한다 (지연 초기화)."""
        if self._sheet is None:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            self._sheet = open_sheet(sheet_id, _SHEET_NAME)
            self._ensure_headers()
        return self._sheet

    def _ensure_headers(self):
        """헤더 행이 없으면 생성한다."""
        ws = self._sheet
        rows = ws.get_all_values()
        if not rows or rows[0] != HEADERS:
            ws.clear()
            ws.append_row(HEADERS)

    def _get_all_rows(self) -> list:
        """모든 데이터 행을 딕셔너리 리스트로 반환한다."""
        try:
            ws = self._get_sheet()
            records = ws.get_all_records()
            return records
        except Exception as exc:
            logger.warning("경쟁사 데이터 조회 실패: %s", exc)
            return []

    def _convert_to_krw(self, price: float, currency: str) -> float:
        """환율을 적용하여 KRW로 변환한다."""
        try:
            from ..fx.provider import FXProvider
            rates = FXProvider().get_rates()
        except Exception:
            rates = {}

        currency = currency.upper()
        if currency == 'KRW':
            return price
        elif currency == 'USD':
            rate = float(rates.get('USDKRW', os.getenv('FX_USDKRW', '1380')))
            return price * rate
        elif currency == 'JPY':
            rate = float(rates.get('JPYKRW', os.getenv('FX_JPYKRW', '9.5')))
            return price * rate
        elif currency == 'EUR':
            rate = float(rates.get('EURKRW', os.getenv('FX_EURKRW', '1500')))
            return price * rate
        else:
            return price

    def _get_our_price_krw(self, our_sku: str) -> float:
        """Google Sheets 카탈로그에서 우리 상품 KRW 가격을 조회한다."""
        try:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            ws = open_sheet(sheet_id, os.getenv('CATALOG_SHEET_NAME', 'catalog'))
            records = ws.get_all_records()
            for row in records:
                if str(row.get('sku', '')) == str(our_sku):
                    price_krw = row.get('price_krw') or row.get('sell_price_krw') or 0
                    return float(price_krw)
        except Exception as exc:
            logger.debug("카탈로그 가격 조회 실패 (%s): %s", our_sku, exc)
        return 0.0

    def track_price(self, our_sku: str, competitor_name: str,
                    competitor_price: float, currency: str = 'KRW') -> bool:
        """경쟁사 가격을 기록한다.

        Args:
            our_sku: 우리 상품 SKU
            competitor_name: 경쟁사 이름
            competitor_price: 경쟁사 가격
            currency: 통화 코드 (기본 KRW)

        Returns:
            성공 여부
        """
        if not _ENABLED:
            logger.debug("경쟁사 추적 비활성화 — 기록 건너뜀")
            return False

        try:
            ws = self._get_sheet()
            records = ws.get_all_records()

            our_price_krw = self._get_our_price_krw(our_sku)
            comp_price_krw = self._convert_to_krw(competitor_price, currency)
            diff_pct = 0.0
            if our_price_krw > 0 and comp_price_krw > 0:
                diff_pct = round((our_price_krw - comp_price_krw) / comp_price_krw * 100, 2)

            now = datetime.utcnow().isoformat()

            # 기존 행 업데이트 또는 신규 추가
            for i, row in enumerate(records):
                if (str(row.get('our_sku')) == str(our_sku)
                        and str(row.get('competitor_name')) == str(competitor_name)):
                    row_num = i + 2  # 헤더 포함
                    ws.update(f'D{row_num}:G{row_num}', [[
                        competitor_price, currency.upper(), now, diff_pct,
                    ]])
                    return True

            ws.append_row([
                our_sku, competitor_name, '',
                competitor_price, currency.upper(), now, diff_pct,
            ])
            return True
        except Exception as exc:
            logger.error("경쟁사 가격 기록 실패: %s", exc)
            return False

    def get_price_comparison(self, our_sku: str) -> dict:
        """특정 SKU의 우리 가격 vs 경쟁사 가격 비교.

        Returns:
            dict with our_price_krw, competitors list, best_competitor_price_krw
        """
        rows = self._get_all_rows()
        our_price_krw = self._get_our_price_krw(our_sku)
        competitors = []

        for row in rows:
            if str(row.get('our_sku')) != str(our_sku):
                continue
            comp_price = float(row.get('competitor_price') or 0)
            currency = str(row.get('competitor_currency', 'KRW'))
            comp_price_krw = self._convert_to_krw(comp_price, currency)
            diff_pct = float(row.get('price_diff_pct') or 0)
            competitors.append({
                'competitor_name': row.get('competitor_name', ''),
                'competitor_url': row.get('competitor_url', ''),
                'competitor_price': comp_price,
                'competitor_currency': currency,
                'competitor_price_krw': round(comp_price_krw),
                'price_diff_pct': diff_pct,
                'last_checked': row.get('last_checked', ''),
            })

        best_price_krw = min(
            (c['competitor_price_krw'] for c in competitors), default=0
        )

        return {
            'our_sku': our_sku,
            'our_price_krw': round(our_price_krw),
            'competitors': competitors,
            'best_competitor_price_krw': round(best_price_krw),
        }

    def get_underpriced_items(self, threshold_pct: float = 10.0) -> list:
        """경쟁사보다 threshold_pct% 이상 저렴한 상품 (마진 개선 기회).

        price_diff_pct = (our_price - comp_price) / comp_price * 100
        저렴하다 = price_diff_pct < -threshold_pct
        """
        rows = self._get_all_rows()
        result = []
        seen = set()

        for row in rows:
            sku = str(row.get('our_sku', ''))
            diff = float(row.get('price_diff_pct') or 0)
            if diff < -threshold_pct and sku not in seen:
                seen.add(sku)
                result.append({
                    'our_sku': sku,
                    'competitor_name': row.get('competitor_name', ''),
                    'price_diff_pct': diff,
                    'competitor_price_krw': round(
                        self._convert_to_krw(
                            float(row.get('competitor_price') or 0),
                            str(row.get('competitor_currency', 'KRW')),
                        )
                    ),
                })

        return sorted(result, key=lambda x: x['price_diff_pct'])

    def get_overpriced_items(self, threshold_pct: float = 10.0) -> list:
        """경쟁사보다 threshold_pct% 이상 비싼 상품 (가격 경쟁력 문제).

        price_diff_pct > threshold_pct
        """
        rows = self._get_all_rows()
        result = []
        seen = set()

        for row in rows:
            sku = str(row.get('our_sku', ''))
            diff = float(row.get('price_diff_pct') or 0)
            if diff > threshold_pct and sku not in seen:
                seen.add(sku)
                result.append({
                    'our_sku': sku,
                    'competitor_name': row.get('competitor_name', ''),
                    'price_diff_pct': diff,
                    'competitor_price_krw': round(
                        self._convert_to_krw(
                            float(row.get('competitor_price') or 0),
                            str(row.get('competitor_currency', 'KRW')),
                        )
                    ),
                })

        return sorted(result, key=lambda x: x['price_diff_pct'], reverse=True)
