"""벤더 사이트에서 상품 재고 상태를 확인하는 모듈."""

import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import requests

logger = logging.getLogger(__name__)

STOCK_CHECK_DELAY = float(os.getenv('STOCK_CHECK_DELAY', '2'))
INVENTORY_CHECK_TIMEOUT = int(os.getenv('INVENTORY_CHECK_TIMEOUT', '15'))


class StockChecker:
    """벤더 사이트에서 재고 상태를 확인하는 클래스."""

    STOCK_IN_STOCK = 'in_stock'
    STOCK_LOW_STOCK = 'low_stock'
    STOCK_OUT_OF_STOCK = 'out_of_stock'
    STOCK_UNKNOWN = 'unknown'

    # 벤더별 HTML 패턴 (config.example.yml과 동기화)
    _PATTERNS = {
        'porter': {
            'in_stock': ['カートに入れる', 'add to cart'],
            'out_of_stock': ['売り切れ', 'sold out'],
        },
        'memo_paris': {
            'in_stock': ['add to bag', 'add to cart', 'ajouter au panier'],
            'out_of_stock': ['out of stock', 'sold out', 'rupture de stock'],
        },
    }

    def __init__(self):
        """벤더별 재고 확인 전략을 초기화."""
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        })

    # ── public API ──────────────────────────────────────────

    def check_single(self, sku: str, src_url: str, vendor: str) -> dict:
        """단일 상품의 재고 상태 확인.

        Args:
            sku: 상품 SKU
            src_url: 벤더 상품 URL
            vendor: 벤더명 ('porter', 'memo_paris')

        Returns:
            {
                'sku': str,
                'status': 'in_stock'|'low_stock'|'out_of_stock'|'unknown',
                'quantity': int|None,
                'price_changed': bool,
                'current_price': Decimal|None,
                'checked_at': str,
                'vendor': str,
            }
        """
        vendor_lower = vendor.lower()
        try:
            if vendor_lower == 'porter':
                return self._check_porter(sku, src_url)
            elif vendor_lower in ('memo_paris', 'memoparis'):
                return self._check_memo_paris(sku, src_url)
            else:
                logger.warning("Unknown vendor '%s' for SKU %s — returning unknown", vendor, sku)
                return self._unknown_result(sku, vendor)
        except Exception as exc:
            logger.warning("Stock check failed for SKU %s (%s): %s", sku, vendor, exc)
            return self._unknown_result(sku, vendor)

    def check_batch(self, products: list) -> list:
        """여러 상품의 재고를 배치 확인.

        products: [{'sku': '...', 'src_url': '...', 'vendor': '...'}, ...]
        Returns: [check_single 결과, ...]
        """
        results = []
        # 벤더별로 그룹핑
        by_vendor: dict = {}
        for p in products:
            v = p.get('vendor', '').lower()
            by_vendor.setdefault(v, []).append(p)

        for vendor, items in by_vendor.items():
            logger.info("Checking %d products for vendor '%s'", len(items), vendor)
            for i, item in enumerate(items):
                result = self.check_single(item['sku'], item['src_url'], item['vendor'])
                results.append(result)
                logger.debug("[%d/%d] %s → %s", i + 1, len(items), item['sku'], result['status'])
                if i < len(items) - 1:
                    time.sleep(STOCK_CHECK_DELAY)

        return results

    # ── vendor-specific ─────────────────────────────────────

    def _check_porter(self, sku: str, src_url: str) -> dict:
        """포터 사이트 재고 확인."""
        html = self._fetch_html(src_url)
        if html is None:
            return self._unknown_result(sku, 'porter')

        html_lower = html.lower()
        status = self._detect_status(html_lower, html, 'porter')
        price = self._extract_price_jpy(html)

        return {
            'sku': sku,
            'status': status,
            'quantity': None,
            'price_changed': False,
            'current_price': price,
            'checked_at': _now_iso(),
            'vendor': 'porter',
        }

    def _check_memo_paris(self, sku: str, src_url: str) -> dict:
        """메모파리 사이트 재고 확인."""
        html = self._fetch_html(src_url)
        if html is None:
            return self._unknown_result(sku, 'memo_paris')

        html_lower = html.lower()
        status = self._detect_status(html_lower, html, 'memo_paris')
        price = self._extract_price_eur(html)

        return {
            'sku': sku,
            'status': status,
            'quantity': None,
            'price_changed': False,
            'current_price': price,
            'checked_at': _now_iso(),
            'vendor': 'memo_paris',
        }

    # ── helpers ─────────────────────────────────────────────

    def _detect_status(self, html_lower: str, html_original: str, vendor: str) -> str:
        """HTML에서 재고 상태를 감지한다."""
        patterns = self._PATTERNS.get(vendor, {})

        for phrase in patterns.get('out_of_stock', []):
            if phrase.lower() in html_lower:
                return self.STOCK_OUT_OF_STOCK

        for phrase in patterns.get('in_stock', []):
            if phrase.lower() in html_lower:
                return self.STOCK_IN_STOCK

        return self.STOCK_UNKNOWN

    def _fetch_html(self, url: str) -> str | None:
        """URL에서 HTML을 가져온다. 실패 시 None."""
        try:
            resp = self._session.get(url, timeout=INVENTORY_CHECK_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.warning("HTTP fetch failed for %s: %s", url, exc)
            return None

    def _extract_price_jpy(self, html: str) -> Decimal | None:
        """HTML에서 JPY 가격을 추출한다."""
        import re
        # ¥12,345 또는 12,345円 패턴
        patterns = [
            r'[¥￥]\s*([\d,]+)',
            r'([\d,]+)\s*円',
            r'"price"\s*:\s*"?([\d,]+)"?',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                try:
                    return Decimal(m.group(1).replace(',', ''))
                except InvalidOperation:
                    pass
        return None

    def _extract_price_eur(self, html: str) -> Decimal | None:
        """HTML에서 EUR 가격을 추출한다."""
        import re
        # €120.00 또는 120,00 € 패턴 (US: 1,234.56 / European: 1.234,56)
        patterns = [
            r'€\s*([\d\s,\.]+)',
            r'([\d\s,\.]+)\s*€',
            r'"price"\s*:\s*"?([\d\.]+)"?',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                raw = m.group(1).strip()
                try:
                    # Try to detect format: if comma precedes exactly 2 digits at end → European decimal
                    # e.g. "120,00" → 120.00, "1.234,56" → 1234.56
                    if ',' in raw and raw.index(',') < len(raw) - 3:
                        # Thousand separator is comma (US style: 1,234.56)
                        cleaned = raw.replace(',', '')
                        return Decimal(cleaned)
                    elif ',' in raw:
                        # Decimal separator is comma (European: 120,00 or 1.234,56)
                        cleaned = raw.replace('.', '').replace(',', '.')
                        return Decimal(cleaned)
                    else:
                        return Decimal(raw.replace(',', ''))
                except InvalidOperation:
                    pass
        return None

    @staticmethod
    def _unknown_result(sku: str, vendor: str) -> dict:
        return {
            'sku': sku,
            'status': StockChecker.STOCK_UNKNOWN,
            'quantity': None,
            'price_changed': False,
            'current_price': None,
            'checked_at': _now_iso(),
            'vendor': vendor,
        }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
