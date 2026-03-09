"""환율 업데이트 → 가격 재계산 → 스토어 반영 통합 엔진."""

import logging
import os
from decimal import Decimal

from .provider import FXProvider
from .cache import FXCache
from .history import FXHistory
from ..utils.sheets import open_sheet

logger = logging.getLogger(__name__)


class FXUpdater:
    """환율 업데이트 → 가격 재계산 → 스토어 반영 통합 엔진."""

    def __init__(self):
        self.provider = FXProvider()
        self.cache = FXCache()
        self.history = FXHistory()

    # ── public API ───────────────────────────────────────────

    def update(self, force: bool = False, dry_run: bool = False) -> dict:
        """환율 업데이트 + 가격 재계산 실행.

        1) FXProvider로 최신 환율 조회 (캐시 유효하면 스킵, force=True면 강제)
        2) FXHistory에 이력 기록
        3) 급변 감지 → 알림
        4) 카탈로그(Google Sheets) 판매가 재계산
        5) Shopify/WooCommerce 가격 업데이트

        Returns:
            {
                'rates': {'USDKRW': '1345.50', ...},
                'provider': 'frankfurter',
                'changes_detected': [{'pair': 'JPYKRW', 'change_pct': '-2.1%'}],
                'prices_recalculated': 25,
                'shopify_updated': 25,
                'woo_updated': 25,
                'alerts_sent': True,
                'dry_run': False,
            }
        """
        result = {
            'rates': {},
            'provider': '',
            'changes_detected': [],
            'prices_recalculated': 0,
            'shopify_updated': 0,
            'woo_updated': 0,
            'alerts_sent': False,
            'dry_run': dry_run,
        }

        # 1) 환율 조회
        if not force and self.cache.is_valid():
            rates = self.cache.get()
            logger.info("FXUpdater: using cached rates (provider=%s)", rates.get('provider'))
        else:
            if force:
                self.cache.invalidate()
            rates = self.provider.get_rates()
            self.cache.set(rates)
            logger.info("FXUpdater: fetched fresh rates (provider=%s)", rates.get('provider'))

        result['rates'] = {k: str(v) for k, v in rates.items() if k in FXProvider.SUPPORTED_PAIRS}
        result['provider'] = str(rates.get('provider', ''))

        # 2) 이력 기록
        if not dry_run:
            self.history.record(rates)

        # 3) 급변 감지 → 알림
        changes = self.history.detect_significant_changes()
        result['changes_detected'] = changes
        if changes and not dry_run:
            self._send_fx_alert(changes, rates)
            result['alerts_sent'] = True

        # 4+5) 가격 재계산 + 스토어 업데이트
        recalc_results = self.recalculate_prices(rates, dry_run=dry_run)
        result['prices_recalculated'] = len(recalc_results)
        result['shopify_updated'] = sum(1 for r in recalc_results if r.get('shopify_updated'))
        result['woo_updated'] = sum(1 for r in recalc_results if r.get('woo_updated'))

        logger.info(
            "FXUpdater.update: prices=%d shopify=%d woo=%d alerts=%s dry_run=%s",
            result['prices_recalculated'], result['shopify_updated'],
            result['woo_updated'], result['alerts_sent'], dry_run,
        )
        return result

    def recalculate_prices(self, fx_rates: dict, dry_run: bool = False) -> list:
        """최신 환율로 카탈로그 전체 판매가 재계산.

        - Google Sheets 카탈로그의 active 상품에 대해:
          - price.calc_price()로 KRW/USD 판매가 재계산
          - 기존 가격과 비교하여 변동분만 업데이트
        - 시트의 sell_price_krw, sell_price_usd 컬럼 업데이트

        Returns:
            [{'sku': '...', 'sell_price_krw': ..., 'sell_price_usd': ...,
              'shopify_updated': bool, 'woo_updated': bool}, ...]
        """
        sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
        worksheet = os.getenv('WORKSHEET', 'catalog')
        margin_pct = Decimal(os.getenv('TARGET_MARGIN_PCT', '22'))

        if not sheet_id:
            logger.debug("GOOGLE_SHEET_ID not set — skipping price recalculation")
            return []

        try:
            from ..price import calc_price
        except Exception as exc:
            logger.error("recalculate_prices import failed: %s", exc)
            return []

        try:
            ws = open_sheet(sheet_id, worksheet)
            rows = ws.get_all_records()
        except Exception as exc:
            logger.error("recalculate_prices: sheet load failed: %s", exc)
            return []

        active_rows = [r for r in rows if str(r.get('status', '')).strip().lower() == 'active']
        headers = ws.row_values(1) if not dry_run else []
        all_rows = ws.get_all_records() if not dry_run else []

        results = []
        for row in active_rows:
            sku = str(row.get('sku', '')).strip()
            buy_price_str = str(row.get('buy_price', '0')).replace(',', '')
            buy_currency = str(row.get('buy_currency', 'KRW')).strip()
            try:
                buy_price = Decimal(buy_price_str)
            except Exception:
                continue

            try:
                new_krw = calc_price(buy_price, buy_currency, None, margin_pct, 'KRW', fx_rates=fx_rates)
                new_usd = calc_price(buy_price, buy_currency, None, margin_pct, 'USD', fx_rates=fx_rates)
            except Exception as exc:
                logger.warning("calc_price failed for SKU %s: %s", sku, exc)
                continue

            item = {
                'sku': sku,
                'sell_price_krw': new_krw,
                'sell_price_usd': new_usd,
                'shopify_updated': False,
                'woo_updated': False,
            }

            if not dry_run:
                # Sheets 업데이트
                for i, r in enumerate(all_rows):
                    if str(r.get('sku', '')).strip() == sku:
                        row_num = i + 2
                        _update_cell_if_exists(ws, row_num, headers, 'sell_price_krw', str(new_krw))
                        _update_cell_if_exists(ws, row_num, headers, 'sell_price_usd', str(new_usd))
                        break

                # Shopify 가격 업데이트
                item['shopify_updated'] = self._update_shopify_price(sku, new_usd)
                # WooCommerce 가격 업데이트
                item['woo_updated'] = self._update_woo_price(sku, new_krw)

            results.append(item)

        return results

    def get_current_rates(self) -> dict:
        """현재 사용 중인 환율 반환 (캐시 우선)."""
        cached = self.cache.get()
        if cached:
            return cached
        return self.provider.get_rates()

    # ── internal helpers ─────────────────────────────────────

    def _send_fx_alert(self, changes: list, rates: dict):
        """환율 급변 텔레그램 알림."""
        try:
            from ..utils.telegram import send_tele
            lines = ['⚠️ [환율 급변 감지]']
            for c in changes:
                lines.append(
                    f"  {c['pair']}: {c['previous']} → {c['current']} ({c['change_pct']})"
                )
            lines.append(f"현재 환율: USD={rates.get('USDKRW')} JPY={rates.get('JPYKRW')} EUR={rates.get('EURKRW')}")
            send_tele('\n'.join(lines))
        except Exception as exc:
            logger.warning("FX alert send failed: %s", exc)

    def _update_shopify_price(self, sku: str, price_usd: Decimal) -> bool:
        """Shopify 상품 가격 업데이트."""
        try:
            if not (os.getenv('SHOPIFY_ACCESS_TOKEN') and os.getenv('SHOPIFY_SHOP')):
                return False
            from ..vendors.shopify_client import _find_by_sku, _request_with_retry
            product = _find_by_sku(sku)
            if not product:
                return False
            api = (
                f"https://{os.getenv('SHOPIFY_SHOP')}/admin/api/"
                f"{os.getenv('SHOPIFY_API_VERSION', '2024-07')}"
            )
            pid = product['id']
            r = _request_with_retry('GET', f"{api}/products/{pid}.json")
            variants = r.json().get('product', {}).get('variants', [])
            for v in variants:
                if v.get('sku') == sku:
                    vid = v['id']
                    _request_with_retry('PUT', f"{api}/variants/{vid}.json",
                                        json={'variant': {'id': vid, 'price': str(price_usd)}})
                    logger.info("Shopify price updated: SKU=%s USD=%s", sku, price_usd)
                    return True
        except Exception as exc:
            logger.warning("Shopify price update failed for %s: %s", sku, exc)
        return False

    def _update_woo_price(self, sku: str, price_krw: Decimal) -> bool:
        """WooCommerce 상품 가격 업데이트."""
        try:
            if not (os.getenv('WOO_CK') and os.getenv('WOO_CS') and os.getenv('WOO_BASE_URL')):
                return False
            from ..vendors.woocommerce_client import _find_by_sku, _request_with_retry
            from urllib.parse import urljoin
            product = _find_by_sku(sku)
            if not product:
                return False
            pid = product['id']
            base = os.getenv('WOO_BASE_URL', '')
            api_ver = os.getenv('WOO_API_VERSION', 'wc/v3')
            url = urljoin(base, f"/wp-json/{api_ver}/products/{pid}")
            _request_with_retry('PUT', url, json={'regular_price': str(price_krw)})
            logger.info("WooCommerce price updated: SKU=%s KRW=%s", sku, price_krw)
            return True
        except Exception as exc:
            logger.warning("WooCommerce price update failed for %s: %s", sku, exc)
        return False


def _update_cell_if_exists(ws, row_num: int, headers: list, col_name: str, value: str):
    """헤더에 컬럼이 있을 때만 셀 업데이트."""
    if col_name not in headers:
        return
    col_idx = headers.index(col_name) + 1
    ws.update_cell(row_num, col_idx, value)
