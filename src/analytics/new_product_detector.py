"""Phase 7: 벤더 신상품 자동 감지 모듈.

벤더(Porter, Memo Paris) 카탈로그를 스캔하여 현재 Google Sheets 카탈로그에
없는 신상품을 감지하고, 예상 마진 기준으로 정렬하여 등록 제안을 생성한다.
"""

import logging
import os

logger = logging.getLogger(__name__)


class NewProductDetector:
    """벤더 신상품 자동 감지 + 카탈로그 등록 제안.

    환경변수:
      NEW_PRODUCT_CHECK_ENABLED   — 활성화 여부 (기본 1)
      NEW_PRODUCT_MIN_MARGIN_PCT  — 최소 예상 마진율 % (기본 15)
      NEW_PRODUCTS_WORKSHEET      — Sheets 워크시트명 (기본 new_product_suggestions)
    """

    def __init__(self, sheet_id: str = None, worksheet: str = None):
        """초기화.

        Args:
            sheet_id: Google Sheet ID.
            worksheet: 카탈로그 워크시트명.
        """
        self._sheet_id = sheet_id or os.getenv('GOOGLE_SHEET_ID', '')
        self._worksheet = worksheet or os.getenv('WORKSHEET', 'catalog')
        self._min_margin = float(os.getenv('NEW_PRODUCT_MIN_MARGIN_PCT', '15'))

    # ── 공개 API ─────────────────────────────────────────────

    def get_catalog_skus(self) -> set:
        """현재 카탈로그의 SKU 집합 반환.

        Returns:
            {'PTR-TNK-001', 'MMP-EDP-002', ...}
        """
        if not self._sheet_id:
            return set()
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._worksheet)
            records = ws.get_all_records()
            return {str(r.get('sku', '')) for r in records if r.get('sku')}
        except Exception as exc:
            logger.error("Failed to load catalog SKUs: %s", exc)
            return set()

    def scan_vendor_products(self, vendor_name: str) -> list:
        """벤더의 현재 상품 목록 스캔.

        벤더 fetch_catalog() 또는 fetch_all() 메서드를 호출하여
        normalize_row()로 정규화된 상품 목록을 반환한다.

        Args:
            vendor_name: 'porter' 또는 'memo_paris'.

        Returns:
            list of normalized product dicts ([] if vendor unavailable)
        """
        try:
            from ..vendors import get_vendor
            vendor = get_vendor(vendor_name)
        except (ImportError, ValueError) as exc:
            logger.error("Vendor not found: %s — %s", vendor_name, exc)
            return []

        try:
            if hasattr(vendor, 'fetch_catalog'):
                raw_products = vendor.fetch_catalog()
            elif hasattr(vendor, 'fetch_all'):
                raw_products = vendor.fetch_all()
            else:
                logger.debug("Vendor %s has no fetch_catalog/fetch_all method", vendor_name)
                return []
        except Exception as exc:
            logger.warning("Failed to fetch from vendor %s: %s", vendor_name, exc)
            return []

        result = []
        for raw in raw_products:
            try:
                normalized = vendor.normalize_row(raw)
                result.append(normalized)
            except Exception as exc:
                logger.debug("Failed to normalize row for vendor %s: %s", vendor_name, exc)
        return result

    def detect_new_products(self) -> list:
        """벤더 신상품 감지 + 예상 마진 기준 우선순위 정렬.

        현재 카탈로그에 없는 SKU를 신상품으로 판별하고
        예상 마진 계산 후 내림차순으로 정렬한다.

        Returns:
            list of new product dicts with 'estimated_margin_pct' key,
            sorted by estimated_margin_pct descending
        """
        catalog_skus = self.get_catalog_skus()
        all_new = []

        for vendor_name in ['porter', 'memo_paris']:
            products = self.scan_vendor_products(vendor_name)
            for p in products:
                sku = str(p.get('sku', '') or '')
                if not sku or sku in catalog_skus:
                    continue
                margin = self._estimate_margin(p)
                p['estimated_margin_pct'] = margin
                all_new.append(p)

        all_new.sort(key=lambda x: x.get('estimated_margin_pct', 0), reverse=True)
        return all_new

    def send_alerts(self, new_products: list):
        """신상품 감지 텔레그램 알림 발송.

        Args:
            new_products: detect_new_products() 반환값.
        """
        if not new_products:
            logger.info("No new products to alert")
            return

        preview = new_products[:5]
        lines = [
            f"🆕 [신상품 감지] {len(new_products)}개 신상품 발견!",
            "",
        ]
        for p in preview:
            title = (
                p.get('title_en') or p.get('title_ja')
                or p.get('title_fr') or '(무제)'
            )
            lines.append(
                f"  • {p['sku']} [{p.get('vendor', '')}] {title}"
            )
            lines.append(
                f"    예상마진: {p.get('estimated_margin_pct', 0):.1f}% | "
                f"구매가: {p.get('buy_price', 0)} {p.get('buy_currency', '')}"
            )

        msg = "\n".join(lines)

        if os.getenv('TELEGRAM_ENABLED', '1') == '1':
            try:
                from ..utils.telegram import send_tele
                send_tele(msg)
                logger.info("New product alert sent via Telegram (%d products)", len(new_products))
            except Exception as exc:
                logger.warning("Telegram send failed: %s", exc)

    def run(self) -> dict:
        """메인 진입점: 신상품 감지 + Sheets 기록 + 텔레그램 알림.

        최소 마진(NEW_PRODUCT_MIN_MARGIN_PCT) 미달 상품은 제안에서 제외한다.

        Returns:
            {'total_detected': int, 'qualified': int, 'new_products': list}
            or {'skipped': True} if disabled.
        """
        enabled = os.getenv('NEW_PRODUCT_CHECK_ENABLED', '1') == '1'
        if not enabled:
            logger.info("NEW_PRODUCT_CHECK_ENABLED=0, skipping")
            return {'skipped': True}

        new_products = self.detect_new_products()
        qualified = [p for p in new_products if p.get('estimated_margin_pct', 0) >= self._min_margin]

        self._write_suggestions_to_sheets(qualified)
        self.send_alerts(qualified)

        return {
            'total_detected': len(new_products),
            'qualified': len(qualified),
            'new_products': qualified,
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    def _estimate_margin(self, product: dict) -> float:
        """상품의 예상 판매 마진율 계산.

        src/price.py의 calc_price()를 활용하여 현재 환율 기준 예상 마진을 계산한다.
        """
        try:
            from ..price import calc_price, _build_fx_rates
            buy_price = float(product.get('buy_price', 0) or 0)
            buy_currency = str(product.get('buy_currency', 'JPY') or 'JPY')
            margin_pct = float(os.getenv('TARGET_MARGIN_PCT', '22'))
            if buy_price <= 0:
                return 0.0
            fx_rates = _build_fx_rates()
            sell_krw = calc_price(
                buy_price, buy_currency,
                None,  # fx_usdkrw: unused when fx_rates dict is provided
                margin_pct, 'KRW', fx_rates=fx_rates
            )
            fx_key = f"{buy_currency}KRW"
            cost_krw = buy_price * float(fx_rates.get(fx_key, 1))
            if float(sell_krw) > 0:
                return round((float(sell_krw) - cost_krw) / float(sell_krw) * 100, 1)
        except Exception as exc:
            logger.debug("Margin estimation failed: %s", exc)
        return 0.0

    def _write_suggestions_to_sheets(self, new_products: list):
        """신상품 제안을 Google Sheets new_product_suggestions 워크시트에 기록."""
        if not self._sheet_id or not new_products:
            return
        worksheet = os.getenv('NEW_PRODUCTS_WORKSHEET', 'new_product_suggestions')
        try:
            from ..utils.sheets import open_sheet
            from datetime import datetime, timezone
            ws = open_sheet(self._sheet_id, worksheet)
            headers = [
                'detected_at', 'sku', 'vendor', 'title_en',
                'buy_price', 'buy_currency', 'estimated_margin_pct', 'src_url',
            ]
            existing = ws.get_all_values()
            if not existing or existing[0] != headers:
                ws.clear()
                ws.append_row(headers)
            now_str = datetime.now(timezone.utc).isoformat()
            for p in new_products:
                ws.append_row([
                    now_str,
                    p.get('sku', ''),
                    p.get('vendor', ''),
                    p.get('title_en', '') or p.get('title_ja', '') or p.get('title_fr', ''),
                    p.get('buy_price', ''),
                    p.get('buy_currency', ''),
                    p.get('estimated_margin_pct', 0),
                    p.get('src_url', ''),
                ])
            logger.info("New product suggestions written to Sheets (%d rows)", len(new_products))
        except Exception as exc:
            logger.warning("Failed to write new product suggestions to Sheets: %s", exc)
