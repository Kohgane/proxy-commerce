"""상품 수집 관리자 — 수집 상품을 Google Sheets에 저장/관리."""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CollectionManager:
    """상품 수집 관리자.

    수집된 상품을 Google Sheets 카탈로그에 저장하고,
    수집 이력을 관리한다.
    """

    # Google Sheets 헤더 (COLLECTED_FIELDS 기반)
    SHEET_HEADERS = [
        'collector_id', 'source_url', 'title_original', 'title_ko', 'title_en',
        'description_original', 'description_ko', 'price_original', 'currency',
        'price_krw', 'sell_price_krw', 'sell_price_usd', 'category', 'category_code',
        'brand', 'rating', 'review_count', 'stock_status', 'weight_kg', 'dimensions',
        'options', 'tags', 'vendor', 'marketplace', 'country', 'sku',
        'status', 'collected_at',
    ]

    def __init__(self):
        """CollectionManager 초기화.

        Google Sheets 연결 (기존 src/utils/sheets.py 활용)
        수집 이력 시트: 'collected_products'
        """
        self.worksheet_name = os.environ.get('COLLECTED_WORKSHEET', 'collected_products')
        self.sheet_id = os.environ.get('GOOGLE_SHEET_ID', '')
        self._ws = None  # lazy-loaded

    def _get_worksheet(self):
        """Google Sheets 워크시트를 lazy-load한다."""
        if self._ws is not None:
            return self._ws
        try:
            from src.utils.sheets import open_sheet
            self._ws = open_sheet(self.sheet_id, self.worksheet_name)
        except Exception as exc:
            logger.error('Failed to open worksheet %s: %s', self.worksheet_name, exc)
            raise
        return self._ws

    def _read_all_rows(self) -> list:
        """시트의 모든 행을 읽어 딕셔너리 목록으로 반환한다."""
        try:
            ws = self._get_worksheet()
            rows = ws.get_all_records()
            return rows
        except Exception as exc:
            logger.error('Failed to read worksheet: %s', exc)
            return []

    def save_collected(self, products: list, dry_run: bool = False) -> dict:
        """수집된 상품들을 카탈로그에 저장한다.

        1. 중복 검사 (collector_id/source_url 기준)
        2. 신규 상품 → Sheets 'collected_products' 시트에 추가
        3. 기존 상품 → 가격/재고 변동 감지 후 업데이트
        4. dry_run=True면 변경 없이 결과만 반환

        Returns:
            {'total': N, 'new': N, 'updated': N, 'skipped': N, 'errors': N}
        """
        result = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        if not products:
            return result
        result['total'] = len(products)

        try:
            existing_rows = self._read_all_rows()
            # collector_id → row index 맵 (1-indexed, 헤더 포함)
            existing_map = {}
            for i, row in enumerate(existing_rows, start=2):
                cid = str(row.get('collector_id', ''))
                if cid:
                    existing_map[cid] = (i, row)

            new_rows = []
            updates = []
            for product in products:
                try:
                    cid = str(product.get('collector_id', ''))
                    if not cid:
                        result['errors'] += 1
                        continue
                    if cid in existing_map:
                        row_idx, old_row = existing_map[cid]
                        old_price = str(old_row.get('price_original', ''))
                        new_price = str(product.get('price_original', ''))
                        old_stock = str(old_row.get('stock_status', ''))
                        new_stock = str(product.get('stock_status', ''))
                        if old_price != new_price or old_stock != new_stock:
                            updates.append((row_idx, product))
                        else:
                            result['skipped'] += 1
                    else:
                        new_rows.append(product)
                except Exception as item_exc:
                    logger.error('save_collected: error processing product: %s', item_exc)
                    result['errors'] += 1

            if not dry_run:
                # 신규 상품 추가
                if new_rows:
                    ws = self._get_worksheet()
                    # 헤더가 없으면 추가
                    all_vals = ws.get_all_values()
                    if not all_vals:
                        ws.append_row(self.SHEET_HEADERS)
                    for row_data in new_rows:
                        ws.append_row(self._to_row(row_data))
                # 변경된 상품 업데이트
                for row_idx, product in updates:
                    ws = self._get_worksheet()
                    ws.update(f'A{row_idx}', [self._to_row(product)])

            result['new'] = len(new_rows)
            result['updated'] = len(updates)
        except Exception as exc:
            logger.error('save_collected failed: %s', exc)
            result['errors'] += result['total'] - result['new'] - result['updated'] - result['skipped']

        return result

    def get_collected(self, filters: dict = None) -> list:
        """저장된 수집 상품 목록을 조회한다.

        filters:
            marketplace: 'amazon_us', 'amazon_jp'
            category: 카테고리 코드
            status: 'pending', 'uploaded', 'archived'
            date_from, date_to (ISO 8601 문자열)
        """
        try:
            rows = self._read_all_rows()
            if not filters:
                return rows
            result = []
            for row in rows:
                if self._matches_filters(row, filters):
                    result.append(row)
            return result
        except Exception as exc:
            logger.error('get_collected failed: %s', exc)
            return []

    def mark_uploaded(self, skus: list, channel: str) -> int:
        """업로드 완료된 상품의 상태를 업데이트한다."""
        if not skus:
            return 0
        updated = 0
        try:
            ws = self._get_worksheet()
            rows = ws.get_all_records()
            # SKU 컬럼 인덱스
            headers = ws.row_values(1)
            sku_col = headers.index('sku') + 1 if 'sku' in headers else None
            status_col = headers.index('status') + 1 if 'status' in headers else None
            if sku_col is None:
                return 0
            for i, row in enumerate(rows, start=2):
                if str(row.get('sku', '')) in skus:
                    if status_col:
                        ws.update_cell(i, status_col, f'uploaded:{channel}')
                    updated += 1
        except Exception as exc:
            logger.error('mark_uploaded failed: %s', exc)
        return updated

    def get_price_changes(self) -> list:
        """가격이 변동된 상품 목록을 반환한다."""
        try:
            rows = self._read_all_rows()
            changes = []
            for row in rows:
                old_price = row.get('price_original_prev')
                new_price = row.get('price_original')
                if old_price and new_price and str(old_price) != str(new_price):
                    changes.append(row)
            return changes
        except Exception as exc:
            logger.error('get_price_changes failed: %s', exc)
            return []

    def generate_report(self) -> dict:
        """수집 현황 리포트를 생성한다."""
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total': 0,
            'by_marketplace': {},
            'by_status': {},
            'by_category': {},
        }
        try:
            rows = self._read_all_rows()
            report['total'] = len(rows)
            for row in rows:
                mp = str(row.get('vendor', 'unknown'))
                report['by_marketplace'][mp] = report['by_marketplace'].get(mp, 0) + 1
                status = str(row.get('status', 'pending'))
                report['by_status'][status] = report['by_status'].get(status, 0) + 1
                cat = str(row.get('category_code', 'GEN'))
                report['by_category'][cat] = report['by_category'].get(cat, 0) + 1
        except Exception as exc:
            logger.error('generate_report failed: %s', exc)
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _to_row(self, product: dict) -> list:
        """상품 딕셔너리를 시트 행(리스트)으로 변환한다."""
        row = []
        for field in self.SHEET_HEADERS:
            val = product.get(field, '')
            if isinstance(val, list):
                val = ','.join(str(v) for v in val)
            elif isinstance(val, dict):
                val = str(val)
            row.append(val if val is not None else '')
        return row

    def _matches_filters(self, row: dict, filters: dict) -> bool:
        """필터 조건에 맞는지 확인한다."""
        if 'marketplace' in filters:
            if str(row.get('vendor', '')) != filters['marketplace']:
                return False
        if 'category' in filters:
            if str(row.get('category_code', '')) != filters['category']:
                return False
        if 'status' in filters:
            if str(row.get('status', '')) != filters['status']:
                return False
        if 'date_from' in filters:
            collected_at = str(row.get('collected_at', ''))
            if collected_at < filters['date_from']:
                return False
        if 'date_to' in filters:
            collected_at = str(row.get('collected_at', ''))
            if collected_at > filters['date_to']:
                return False
        return True
