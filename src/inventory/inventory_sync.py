"""카탈로그 ↔ 스토어 재고 동기화 엔진."""

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

from .stock_checker import StockChecker
from .stock_alerts import StockAlertManager
from ..utils.sheets import open_sheet

logger = logging.getLogger(__name__)

SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '')
WORKSHEET = os.getenv('WORKSHEET', 'catalog')
LOW_STOCK_THRESHOLD = int(os.getenv('LOW_STOCK_THRESHOLD', '3'))
PRICE_CHANGE_THRESHOLD_PCT = float(os.getenv('PRICE_CHANGE_THRESHOLD_PCT', '5.0'))


class InventorySync:
    """카탈로그 ↔ 스토어 재고 동기화 엔진."""

    def __init__(self, sheet_id: str = None, worksheet: str = None):
        self._sheet_id = sheet_id or SHEET_ID
        self._worksheet = worksheet or WORKSHEET
        self.checker = StockChecker()
        self.alert_manager = StockAlertManager()
        self._last_result: dict = {}

    # ── public API ──────────────────────────────────────────

    def full_sync(self, dry_run: bool = False, vendor_filter: str = None) -> dict:
        """전체 재고 동기화 실행.

        1) Google Sheets 카탈로그에서 active 상품 목록 가져옴
        2) StockChecker로 벤더 사이트 재고 확인
        3) 변경사항 감지 (품절/재입고/가격변동)
        4) Google Sheets 카탈로그 업데이트
        5) Shopify/WooCommerce 재고 업데이트
        6) 변경 알림 발송

        Args:
            dry_run: True면 실제 업데이트 없이 변경사항만 리포트
            vendor_filter: 특정 벤더만 처리 ('porter', 'memo_paris', None=전체)

        Returns:
            {
                'total_checked': int,
                'changes': list,
                'shopify_updated': int,
                'woo_updated': int,
                'sheets_updated': int,
                'errors': list,
                'dry_run': bool,
            }
        """
        result = {
            'total_checked': 0,
            'changes': [],
            'shopify_updated': 0,
            'woo_updated': 0,
            'sheets_updated': 0,
            'errors': [],
            'dry_run': dry_run,
        }

        # 1) 카탈로그 로드
        try:
            rows = self._get_active_rows(vendor_filter)
        except Exception as exc:
            logger.error("Failed to load catalog: %s", exc)
            result['errors'].append(f"catalog_load: {exc}")
            self._last_result = result
            return result

        if not rows:
            logger.info("No active catalog rows found")
            self._last_result = result
            return result

        # 2) 재고 확인
        check_inputs = [
            {'sku': r['sku'], 'src_url': r.get('src_url', ''), 'vendor': r.get('vendor', '')}
            for r in rows
        ]
        checked = self.checker.check_batch(check_inputs)
        result['total_checked'] = len(checked)

        # 3) 변경사항 감지
        catalog_map = {r['sku']: r for r in rows}
        out_of_stock_items = []
        restock_items = []
        price_change_items = []

        for item in checked:
            sku = item['sku']
            catalog_row = catalog_map.get(sku, {})
            prev_status = str(catalog_row.get('stock_status', 'unknown')).strip().lower()
            prev_qty = int(catalog_row.get('stock', 0) or 0)
            new_status = item['status']
            new_qty = item.get('quantity')

            change = self._detect_change(
                sku, prev_status, prev_qty, new_status, new_qty,
                item.get('current_price'), catalog_row
            )
            if change:
                result['changes'].append(change)
                # 알림 분류
                if change['change'] == 'out_of_stock':
                    out_of_stock_items.append({
                        'sku': sku,
                        'title': catalog_row.get('title_ko') or catalog_row.get('title_en', ''),
                        'vendor': item['vendor'],
                    })
                elif change['change'] == 'restock':
                    restock_items.append({
                        'sku': sku,
                        'title': catalog_row.get('title_ko') or catalog_row.get('title_en', ''),
                        'quantity': new_qty,
                        'vendor': item['vendor'],
                    })
                elif change['change'] == 'price_changed':
                    price_change_items.append({
                        'sku': sku,
                        'title': catalog_row.get('title_ko') or catalog_row.get('title_en', ''),
                        'old_price': change.get('old_price', ''),
                        'new_price': change.get('new_price', ''),
                        'currency': catalog_row.get('buy_currency', ''),
                    })

            # 4+5) 실제 업데이트
            if not dry_run and change:
                qty_to_set = 0 if new_status == StockChecker.STOCK_OUT_OF_STOCK else (new_qty or prev_qty)
                stock_status_str = _map_stock_status(new_status)

                if self.update_catalog_stock(
                    sku, stock_status_str, quantity=qty_to_set,
                    price=str(item['current_price']) if item.get('current_price') else None
                ):
                    result['sheets_updated'] += 1

                if self.update_shopify_stock(sku, qty_to_set):
                    result['shopify_updated'] += 1

                woo_status = 'instock' if qty_to_set > 0 else 'outofstock'
                if self.update_woo_stock(sku, qty_to_set, woo_status):
                    result['woo_updated'] += 1

        # 6) 알림 발송
        if not dry_run:
            if out_of_stock_items:
                self.alert_manager.notify_out_of_stock(out_of_stock_items)
            if restock_items:
                self.alert_manager.notify_restock(restock_items)
            if price_change_items:
                self.alert_manager.notify_price_change(price_change_items)
            self.alert_manager.send_sync_summary(result)

        self._last_result = result
        logger.info(
            "full_sync complete: checked=%d changes=%d dry_run=%s",
            result['total_checked'], len(result['changes']), dry_run
        )
        return result

    def sync_single(self, sku: str, dry_run: bool = False) -> dict:
        """단일 상품 재고 동기화."""
        try:
            rows = self._get_active_rows()
        except Exception as exc:
            return {'sku': sku, 'error': str(exc), 'dry_run': dry_run}

        row = next((r for r in rows if r.get('sku') == sku), None)
        if not row:
            return {'sku': sku, 'error': 'SKU not found in catalog', 'dry_run': dry_run}

        checked = self.checker.check_single(sku, row.get('src_url', ''), row.get('vendor', ''))
        prev_status = str(row.get('stock_status', 'unknown')).strip().lower()
        prev_qty = int(row.get('stock', 0) or 0)

        change = self._detect_change(
            sku, prev_status, prev_qty, checked['status'], checked.get('quantity'),
            checked.get('current_price'), row
        )

        result = {
            'sku': sku,
            'checked': checked,
            'change': change,
            'dry_run': dry_run,
        }

        if not dry_run and change:
            qty_to_set = 0 if checked['status'] == StockChecker.STOCK_OUT_OF_STOCK else (
                checked.get('quantity') or prev_qty
            )
            self.update_catalog_stock(
                sku, _map_stock_status(checked['status']), quantity=qty_to_set,
                price=str(checked['current_price']) if checked.get('current_price') else None
            )
            self.update_shopify_stock(sku, qty_to_set)
            self.update_woo_stock(sku, qty_to_set, 'instock' if qty_to_set > 0 else 'outofstock')

        return result

    def update_catalog_stock(
        self, sku: str, stock_status: str,
        quantity: int = None, price: str = None
    ) -> bool:
        """Google Sheets 카탈로그의 재고 정보 업데이트."""
        try:
            ws = open_sheet(self._sheet_id, self._worksheet)
            rows = ws.get_all_records()
            for i, row in enumerate(rows):
                if str(row.get('sku', '')).strip() == sku:
                    row_num = i + 2  # 헤더 포함 1-indexed
                    headers = ws.row_values(1)
                    now_iso = datetime.now(tz=timezone.utc).isoformat()

                    _update_cell(ws, row_num, headers, 'stock_status', stock_status)
                    _update_cell(ws, row_num, headers, 'last_stock_check', now_iso)

                    if quantity is not None:
                        _update_cell(ws, row_num, headers, 'stock', str(quantity))

                    if price:
                        old_price = str(row.get('buy_price', ''))
                        _update_cell(ws, row_num, headers, 'buy_price', price)
                        # 가격 이력 기록
                        history = str(row.get('price_history', ''))
                        new_entry = f"{now_iso}:{old_price}->{price}"
                        updated_history = f"{history};{new_entry}".lstrip(';')
                        _update_cell(ws, row_num, headers, 'price_history', updated_history)

                    logger.info("Catalog updated: SKU=%s status=%s qty=%s", sku, stock_status, quantity)
                    return True

            logger.warning("SKU %s not found in catalog sheet", sku)
            return False
        except Exception as exc:
            logger.error("update_catalog_stock failed for %s: %s", sku, exc)
            return False

    def update_shopify_stock(self, sku: str, quantity: int) -> bool:
        """Shopify 상품 재고 업데이트."""
        try:
            if not (os.getenv('SHOPIFY_ACCESS_TOKEN') and os.getenv('SHOPIFY_SHOP')):
                logger.debug("Shopify credentials missing — skipping stock update for %s", sku)
                return False

            from ..vendors.shopify_client import graphql_query, _find_by_sku

            product = _find_by_sku(sku)
            if not product:
                logger.warning("Shopify: SKU %s not found", sku)
                return False

            # Shopify Inventory API: inventorySetOnHandQuantities
            location_id = os.getenv('SHOPIFY_LOCATION_ID', '')
            if not location_id:
                logger.debug("SHOPIFY_LOCATION_ID not set — using REST fallback for %s", sku)
                return self._shopify_stock_via_variant(sku, quantity)

            mutation = """
            mutation setOnHand($input: InventorySetOnHandQuantitiesInput!) {
              inventorySetOnHandQuantities(input: $input) {
                userErrors { field message }
                inventoryAdjustmentGroup { id }
              }
            }
            """
            # Get inventory item ID first
            variant_query = """
            query variantBySku($query: String!) {
              productVariants(first: 1, query: $query) {
                edges {
                  node {
                    inventoryItem { id legacyResourceId }
                  }
                }
              }
            }
            """
            safe_sku = sku.replace('"', '').replace("'", '').strip()
            vdata = graphql_query(variant_query, variables={'query': f'sku:{safe_sku}'})
            edges = vdata.get('productVariants', {}).get('edges', [])
            if not edges:
                logger.warning("Shopify: variant not found for SKU %s", sku)
                return False

            inv_item_id = edges[0]['node']['inventoryItem']['id']
            gql_location_id = f"gid://shopify/Location/{location_id}"

            variables = {
                'input': {
                    'reason': 'correction',
                    'setQuantities': [
                        {'inventoryItemId': inv_item_id, 'locationId': gql_location_id, 'quantity': quantity}
                    ],
                }
            }
            data = graphql_query(mutation, variables=variables)
            errors = data.get('inventorySetOnHandQuantities', {}).get('userErrors', [])
            if errors:
                logger.error("Shopify inventory update errors: %s", errors)
                return False

            logger.info("Shopify stock updated: SKU=%s qty=%d", sku, quantity)
            return True

        except Exception as exc:
            logger.error("update_shopify_stock failed for %s: %s", sku, exc)
            return False

    def _shopify_stock_via_variant(self, sku: str, quantity: int) -> bool:
        """Shopify REST API로 variant 재고 업데이트 (location_id 없을 때 폴백)."""
        try:
            from ..vendors.shopify_client import _find_by_sku, _request_with_retry
            API = f"https://{os.getenv('SHOPIFY_SHOP')}/admin/api/{os.getenv('SHOPIFY_API_VERSION', '2024-07')}"
            product = _find_by_sku(sku)
            if not product:
                return False
            pid = product['id']
            r = _request_with_retry('GET', f"{API}/products/{pid}.json")
            variants = r.json().get('product', {}).get('variants', [])
            for v in variants:
                if v.get('sku') == sku:
                    vid = v['id']
                    _request_with_retry('PUT', f"{API}/variants/{vid}.json",
                                        json={'variant': {'id': vid, 'inventory_quantity': quantity}})
                    return True
            return False
        except Exception as exc:
            logger.error("Shopify REST stock update failed for %s: %s", sku, exc)
            return False

    def update_woo_stock(self, sku: str, quantity: int, stock_status: str = 'instock') -> bool:
        """WooCommerce 상품 재고 업데이트."""
        try:
            if not (os.getenv('WOO_CK') and os.getenv('WOO_CS') and os.getenv('WOO_BASE_URL')):
                logger.debug("WooCommerce credentials missing — skipping stock update for %s", sku)
                return False

            from ..vendors.woocommerce_client import _find_by_sku, _request_with_retry
            from urllib.parse import urljoin
            WOO_API_VERSION = os.getenv('WOO_API_VERSION', 'wc/v3')
            BASE = os.getenv('WOO_BASE_URL', '')

            product = _find_by_sku(sku)
            if not product:
                logger.warning("WooCommerce: SKU %s not found", sku)
                return False

            pid = product['id']
            url = urljoin(BASE, f"/wp-json/{WOO_API_VERSION}/products/{pid}")
            _request_with_retry('PUT', url, json={
                'stock_quantity': quantity,
                'stock_status': stock_status,
                'manage_stock': True,
            })
            logger.info("WooCommerce stock updated: SKU=%s qty=%d status=%s", sku, quantity, stock_status)
            return True

        except Exception as exc:
            logger.error("update_woo_stock failed for %s: %s", sku, exc)
            return False

    def get_sync_report(self) -> dict:
        """마지막 동기화 결과 리포트."""
        return dict(self._last_result)

    # ── internal helpers ─────────────────────────────────────

    def _get_active_rows(self, vendor_filter: str = None) -> list:
        """Google Sheets에서 active 상품 목록 조회."""
        ws = open_sheet(self._sheet_id, self._worksheet)
        rows = ws.get_all_records()
        active = [
            r for r in rows
            if str(r.get('status', '')).strip().lower() == 'active'
            and r.get('src_url')
        ]
        if vendor_filter:
            active = [r for r in active if str(r.get('vendor', '')).lower() == vendor_filter.lower()]
        return active

    def _detect_change(
        self, sku: str, prev_status: str, prev_qty: int,
        new_status: str, new_qty, current_price, catalog_row: dict
    ) -> dict | None:
        """이전 상태와 새 상태를 비교해 변경사항 dict를 반환. 변경 없으면 None."""
        from .stock_checker import StockChecker

        # 품절 감지
        if (new_status == StockChecker.STOCK_OUT_OF_STOCK
                and prev_status not in ('out_of_stock',)):
            return {'sku': sku, 'change': 'out_of_stock', 'previous': prev_status}

        # 재입고 감지
        if (new_status in (StockChecker.STOCK_IN_STOCK, StockChecker.STOCK_LOW_STOCK)
                and prev_status == 'out_of_stock'):
            return {'sku': sku, 'change': 'restock', 'previous': prev_status,
                    'quantity': new_qty}

        # 가격 변동 감지
        if current_price is not None:
            try:
                old_price_str = str(catalog_row.get('buy_price', '') or '')
                if old_price_str:
                    old = Decimal(old_price_str.replace(',', ''))
                    if old > 0:
                        pct = abs((current_price - old) / old * 100)
                        if pct >= Decimal(str(PRICE_CHANGE_THRESHOLD_PCT)):
                            return {
                                'sku': sku,
                                'change': 'price_changed',
                                'old_price': str(old),
                                'new_price': str(current_price),
                            }
            except Exception:
                pass

        return None


# ── helpers ──────────────────────────────────────────────────

def _map_stock_status(checker_status: str) -> str:
    """StockChecker 상수 → Sheets 컬럼 값."""
    mapping = {
        'in_stock': 'in_stock',
        'low_stock': 'low_stock',
        'out_of_stock': 'out_of_stock',
        'unknown': 'unknown',
    }
    return mapping.get(checker_status, 'unknown')


def _update_cell(ws, row_num: int, headers: list, col_name: str, value: str):
    """시트에서 col_name 컬럼을 찾아 해당 셀을 업데이트."""
    if col_name not in headers:
        logger.debug("Column '%s' not found in sheet — skipping", col_name)
        return
    col_idx = headers.index(col_name) + 1  # 1-indexed
    ws.update_cell(row_num, col_idx, value)
