"""Phase 7: 자동 가격 조정 엔진.

환율 변동 시 카탈로그 SKU의 판매가를 자동 재계산하고
마진 보호 로직(MIN_MARGIN_PCT, MAX_PRICE_CHANGE_PCT)을 적용한다.
DRY_RUN 모드에서는 변경 내역만 리포트하고 실제 적용은 하지 않는다.
"""

import logging
import os

logger = logging.getLogger(__name__)


class AutoPricingEngine:
    """환율 변동 시 자동 가격 조정 엔진.

    환경변수:
      AUTO_PRICING_ENABLED  — 활성화 여부 (기본 1)
      AUTO_PRICING_MODE     — DRY_RUN | APPLY (기본 DRY_RUN)
      MIN_MARGIN_PCT        — 최소 마진율 % (기본 10)
      MAX_PRICE_CHANGE_PCT  — 최대 가격 변동폭 % (기본 8)
    """

    def __init__(self, sheet_id: str = None, worksheet: str = None):
        """초기화.

        Args:
            sheet_id: Google Sheet ID (기본 GOOGLE_SHEET_ID 환경변수).
            worksheet: 카탈로그 워크시트명 (기본 WORKSHEET 환경변수).
        """
        self._sheet_id = sheet_id or os.getenv('GOOGLE_SHEET_ID', '')
        self._worksheet = worksheet or os.getenv('WORKSHEET', 'catalog')
        self._min_margin = float(os.getenv('MIN_MARGIN_PCT', '10'))
        self._max_change = float(os.getenv('MAX_PRICE_CHANGE_PCT', '8'))
        self._dry_run = os.getenv('AUTO_PRICING_MODE', 'DRY_RUN') != 'APPLY'

    # ── 공개 API ─────────────────────────────────────────────

    def check_and_adjust(self) -> dict:
        """메인 진입점: 환율 체크 → 가격 계산 → 적용 → 알림.

        Returns:
            apply_result dict + 'report' 키
        """
        enabled = os.getenv('AUTO_PRICING_ENABLED', '1') == '1'
        if not enabled:
            logger.info("AUTO_PRICING_ENABLED=0, skipping")
            return {'skipped': True}

        price_changes = self.calculate_new_prices()
        apply_result = self.apply_price_changes(price_changes)
        report = self.generate_report(price_changes)

        if os.getenv('TELEGRAM_ENABLED', '1') == '1':
            try:
                from ..utils.telegram import send_tele
                send_tele(report)
            except Exception as exc:
                logger.warning("Telegram send failed: %s", exc)

        return {**apply_result, 'report': report}

    def calculate_new_prices(self) -> list:
        """현재 환율로 각 SKU의 새 판매가 계산.

        Returns:
            list of dicts:
              sku, buy_currency, fx_rate, cost_krw,
              old_price_krw, new_price_krw, change_pct,
              margin_current, margin_new, needs_update
        """
        fx = self._get_current_fx()
        rows = self._get_catalog_rows()
        results = []

        for row in rows:
            sku = str(row.get('sku', '') or '')
            if not sku:
                continue
            try:
                buy_price = float(row.get('buy_price', 0) or 0)
                buy_currency = str(row.get('buy_currency', 'JPY') or 'JPY').upper()
                old_price_krw = float(row.get('sell_price_krw', 0) or 0)
                margin_pct = float(row.get('margin_pct', 22) or 22)
            except (TypeError, ValueError):
                continue

            if buy_price <= 0 or old_price_krw <= 0:
                continue

            fx_key = f"{buy_currency}KRW"
            fx_rate = fx.get(fx_key, 1.0)
            cost_krw = buy_price * fx_rate

            # 현재 환율 기준 마진 (참고용)
            margin_current = (
                round((old_price_krw - cost_krw) / old_price_krw * 100, 1)
                if old_price_krw > 0 else 0.0
            )

            # 새 판매가: 현재 환율 + 기존 마진율 유지
            # (markup 방식: sell = cost × (1 + margin_pct/100), 즉 마진율은 cost 기준 마크업)
            new_price_krw = round(cost_krw * (1 + margin_pct / 100))

            # 마진 보호: 새 판매가 기준 마진이 MIN 이하이면 MIN 마진 보장
            # (profit/sell = min_margin → sell = cost / (1 - min_margin/100))
            provisional_margin = (
                (new_price_krw - cost_krw) / new_price_krw * 100
                if new_price_krw > 0 else 0.0
            )
            if provisional_margin < self._min_margin and self._min_margin < 100:
                new_price_krw = round(cost_krw / (1 - self._min_margin / 100))

            # 가격 변동폭 계산
            change_pct = (
                (new_price_krw - old_price_krw) / old_price_krw * 100
                if old_price_krw > 0 else 0.0
            )

            # 급격한 가격 변동 방지 (MAX_PRICE_CHANGE_PCT 상한선)
            if abs(change_pct) > self._max_change:
                if change_pct > 0:
                    new_price_krw = round(old_price_krw * (1 + self._max_change / 100))
                else:
                    new_price_krw = round(old_price_krw * (1 - self._max_change / 100))
                change_pct = (new_price_krw - old_price_krw) / old_price_krw * 100

            # 새 마진율 계산
            margin_new = (
                round((new_price_krw - cost_krw) / new_price_krw * 100, 1)
                if new_price_krw > 0 else 0.0
            )

            needs_update = abs(change_pct) >= 0.5  # 0.5% 이상 변동 시 업데이트

            results.append({
                'sku': sku,
                'buy_currency': buy_currency,
                'fx_rate': fx_rate,
                'cost_krw': round(cost_krw),
                'old_price_krw': round(old_price_krw),
                'new_price_krw': new_price_krw,
                'change_pct': round(change_pct, 2),
                'margin_current': margin_current,
                'margin_new': margin_new,
                'needs_update': needs_update,
            })

        return results

    def apply_price_changes(self, price_changes: list) -> dict:
        """가격 변경 실제 적용 (Sheets + Shopify + WooCommerce).

        DRY_RUN 모드에서는 실제 변경 없이 통계만 반환.

        Args:
            price_changes: calculate_new_prices() 반환값.

        Returns:
            {'dry_run': bool, 'total_checked': int, 'needs_update': int,
             'updated_sheets': int, 'updated_shopify': int, 'updated_woo': int, 'errors': list}
        """
        to_update = [p for p in price_changes if p['needs_update']]
        result = {
            'dry_run': self._dry_run,
            'total_checked': len(price_changes),
            'needs_update': len(to_update),
            'updated_sheets': 0,
            'updated_shopify': 0,
            'updated_woo': 0,
            'errors': [],
        }

        if self._dry_run:
            logger.info("DRY_RUN mode — skipping price updates (%d SKUs to update)", len(to_update))
            return result

        for item in to_update:
            sku = item['sku']
            new_price = item['new_price_krw']

            try:
                self._update_sheet_price(sku, new_price)
                result['updated_sheets'] += 1
            except Exception as exc:
                result['errors'].append(f"sheets:{sku}: {exc}")

            try:
                self._update_shopify_price(sku, new_price)
                result['updated_shopify'] += 1
            except Exception as exc:
                logger.debug("Shopify price update skipped for %s: %s", sku, exc)

            try:
                self._update_woo_price(sku, new_price)
                result['updated_woo'] += 1
            except Exception as exc:
                logger.debug("WooCommerce price update skipped for %s: %s", sku, exc)

        return result

    def generate_report(self, price_changes: list) -> str:
        """가격 변경 내역 텔레그램 리포트 문자열 생성.

        Args:
            price_changes: calculate_new_prices() 반환값.

        Returns:
            텔레그램 발송용 문자열
        """
        to_update = [p for p in price_changes if p['needs_update']]
        risk_skus = [p for p in price_changes if p['margin_new'] < self._min_margin]
        mode_label = "DRY RUN" if self._dry_run else "APPLIED"

        lines = [
            f"💰 [자동 가격 조정] {mode_label}",
            f"체크 SKU: {len(price_changes)}개 | 조정 필요: {len(to_update)}개",
            "",
        ]

        if to_update:
            lines.append("📋 가격 변경 내역 (상위 10개):")
            for item in to_update[:10]:
                direction = "↑" if item['change_pct'] > 0 else "↓"
                lines.append(
                    f"  • {item['sku']}: ₩{item['old_price_krw']:,} → ₩{item['new_price_krw']:,} "
                    f"({direction}{abs(item['change_pct']):.1f}%) 마진: {item['margin_new']:.1f}%"
                )

        if risk_skus:
            lines.append("")
            lines.append(f"⚠️ 마진 위험 SKU ({len(risk_skus)}개, 마진 < {self._min_margin}%):")
            for item in risk_skus[:5]:
                lines.append(f"  • {item['sku']}: 마진 {item['margin_new']:.1f}%")

        return "\n".join(lines)

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    def _get_current_fx(self) -> dict:
        """현재 환율 조회 (FXCache 우선, 환경변수 폴백).

        Returns:
            {'USDKRW': float, 'JPYKRW': float, 'EURKRW': float}
        """
        try:
            from ..fx.cache import FXCache
            cache = FXCache()
            rates = cache.get()
            if rates:
                return {
                    'USDKRW': float(rates.get('USDKRW', 1350)),
                    'JPYKRW': float(rates.get('JPYKRW', 9.0)),
                    'EURKRW': float(rates.get('EURKRW', 1470)),
                }
        except Exception as exc:
            logger.debug("FXCache not available: %s", exc)

        return {
            'USDKRW': float(os.getenv('FX_USDKRW', '1350')),
            'JPYKRW': float(os.getenv('FX_JPYKRW', '9.0')),
            'EURKRW': float(os.getenv('FX_EURKRW', '1470')),
        }

    def _get_catalog_rows(self) -> list:
        """Google Sheets 카탈로그에서 active 상품 로드."""
        if not self._sheet_id:
            logger.warning("GOOGLE_SHEET_ID not set — returning empty catalog")
            return []
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._worksheet)
            rows = ws.get_all_records()
            return [r for r in rows if str(r.get('status', '')).lower() == 'active']
        except Exception as exc:
            logger.error("Failed to load catalog: %s", exc)
            return []

    def _update_sheet_price(self, sku: str, new_price_krw: float):
        """Google Sheets 카탈로그의 sell_price_krw 업데이트."""
        if not self._sheet_id:
            return
        from ..utils.sheets import open_sheet
        ws = open_sheet(self._sheet_id, self._worksheet)
        headers = ws.row_values(1)
        if 'sell_price_krw' not in headers:
            return
        col = headers.index('sell_price_krw') + 1
        records = ws.get_all_records()
        for i, row in enumerate(records, start=2):
            if str(row.get('sku', '')) == sku:
                ws.update_cell(i, col, new_price_krw)
                break

    def _update_shopify_price(self, sku: str, new_price_krw: float):
        """Shopify 상품 가격 업데이트 (KRW → USD 환산)."""
        if not os.getenv('SHOPIFY_SHOP', ''):
            return
        try:
            from ..channels.shopify_global import ShopifyGlobalChannel
            channel = ShopifyGlobalChannel()
            fx = self._get_current_fx()
            usd_price = round(new_price_krw / fx.get('USDKRW', 1350), 2)
            channel.update_price_by_sku(sku, usd_price)
        except Exception as exc:
            logger.debug("Shopify update_price_by_sku not available: %s", exc)

    def _update_woo_price(self, sku: str, new_price_krw: float):
        """WooCommerce 상품 가격 업데이트 (KRW)."""
        if not os.getenv('WOO_BASE_URL', ''):
            return
        try:
            from ..channels.woo_domestic import WooDomesticChannel
            channel = WooDomesticChannel()
            channel.update_price_by_sku(sku, new_price_krw)
        except Exception as exc:
            logger.debug("WooCommerce update_price_by_sku not available: %s", exc)
