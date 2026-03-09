"""
src/scrapers/sheet_importer.py
정규화된 카탈로그 데이터를 Google Sheets에 적재하는 모듈.
기존 utils/sheets.py의 open_sheet()를 재사용.
"""

import hashlib
import logging
import os
import re

from ..utils.sheets import open_sheet
from .listly_client import ListlyLoader

logger = logging.getLogger(__name__)

# 카탈로그 시트 헤더 (catalog.sample.csv 기준)
CATALOG_HEADERS = [
    'sku', 'title_ko', 'title_en', 'title_ja', 'title_fr',
    'src_url', 'buy_currency', 'buy_price', 'source_country',
    'images', 'stock', 'tags', 'vendor', 'status',
]

# ──────────────────────────────────────────────────────────────────────────────
# 벤더 모듈 임포트 (Step 1-3에서 생성 예정 — ImportError 시 graceful 폴백)
# ──────────────────────────────────────────────────────────────────────────────
try:
    from ..vendors.porter import normalize as porter_normalize  # type: ignore[import]
    _PORTER_NORMALIZE = porter_normalize
except ImportError:
    _PORTER_NORMALIZE = None

try:
    from ..vendors.memo_paris import normalize as memo_normalize  # type: ignore[import]
    _MEMO_NORMALIZE = memo_normalize
except ImportError:
    _MEMO_NORMALIZE = None


def _parse_price(price_str: str) -> tuple:
    """
    가격 문자열에서 (통화코드, 숫자) 추출.
    예: '¥30,800' → ('JPY', '30800')
        '€250.00' → ('EUR', '250.00')
        '$49.99'  → ('USD', '49.99')
    """
    price_str = price_str.strip()
    if price_str.startswith('¥'):
        currency = 'JPY'
    elif price_str.startswith('€'):
        currency = 'EUR'
    elif price_str.startswith('$'):
        currency = 'USD'
    elif price_str.endswith('円'):
        currency = 'JPY'
    else:
        currency = 'KRW'
    # 숫자만 추출
    numeric = re.sub(r'[^\d.]', '', price_str)
    return currency, numeric


def _make_sku(vendor_name: str, url: str, product_name: str) -> str:
    """URL 또는 상품명 기반으로 고유 SKU 생성."""
    source = url.strip() if url.strip() else product_name.strip()
    digest = hashlib.sha256(source.encode('utf-8')).hexdigest()[:8].upper()
    prefix = vendor_name.upper()[:4]
    return f'{prefix}-{digest}'


def _normalize_porter(row: dict) -> dict:
    """Porter 원시 행 → 카탈로그 표준 형식으로 정규화."""
    url = row.get('url', '').strip()
    product_name = row.get('product_name', '').strip()
    price_raw = row.get('price', '').strip()
    currency, buy_price = _parse_price(price_raw)
    image_url = row.get('image_url', '').strip()
    category = row.get('category', '').strip()

    sku = _make_sku('porter', url, product_name)

    return {
        'sku': sku,
        'title_ko': '',
        'title_en': '',
        'title_ja': product_name,
        'title_fr': '',
        'src_url': url,
        'buy_currency': currency,
        'buy_price': buy_price,
        'source_country': 'JP',
        'images': image_url,
        'stock': 0,
        'tags': category,
        'vendor': 'porter',
        'status': 'active',
    }


def _normalize_memo_paris(row: dict) -> dict:
    """Memo Paris 원시 행 → 카탈로그 표준 형식으로 정규화."""
    url = row.get('url', '').strip()
    product_name = row.get('product_name', '').strip()
    price_raw = row.get('price', '').strip()
    currency, buy_price = _parse_price(price_raw)
    image_url = row.get('image_url', '').strip()
    collection = row.get('collection', '').strip()
    size = row.get('size', '').strip()
    tags_parts = [t for t in [collection, size] if t]
    tags = ','.join(tags_parts)

    sku = _make_sku('memo', url, product_name)

    return {
        'sku': sku,
        'title_ko': '',
        'title_en': product_name,
        'title_ja': '',
        'title_fr': product_name,
        'src_url': url,
        'buy_currency': currency,
        'buy_price': buy_price,
        'source_country': 'FR',
        'images': image_url,
        'stock': 0,
        'tags': tags,
        'vendor': 'memo_paris',
        'status': 'active',
    }


def get_vendor_normalizer(vendor_name: str):
    """
    벤더 이름으로 정규화 함수 반환.
    Step 1-3 벤더 모듈이 있으면 우선 사용, 없으면 내장 폴백 사용.
    """
    if vendor_name == 'porter':
        return _PORTER_NORMALIZE if _PORTER_NORMALIZE else _normalize_porter
    elif vendor_name == 'memo_paris':
        return _MEMO_NORMALIZE if _MEMO_NORMALIZE else _normalize_memo_paris
    else:
        raise ValueError(f'지원하지 않는 벤더: {vendor_name}. 지원 목록: porter, memo_paris')


class SheetImporter:
    """정규화된 카탈로그 데이터를 Google Sheets에 적재하는 클래스."""

    def __init__(self, sheet_id: str, worksheet_name: str = 'catalog'):
        """Google Sheets 연결 초기화 (기존 utils/sheets.py의 open_sheet 활용)."""
        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name
        self._ws = open_sheet(sheet_id, worksheet_name)
        logger.info('Google Sheets 연결 완료: %s / %s', sheet_id, worksheet_name)

    def get_existing_skus(self) -> set:
        """현재 시트에 있는 SKU 목록 조회 (중복 방지)."""
        records = self._ws.get_all_records()
        skus = {str(r.get('sku', '')).strip() for r in records if r.get('sku')}
        logger.info('기존 SKU %d개 조회 완료', len(skus))
        return skus

    def _row_to_list(self, row: dict) -> list:
        """딕셔너리 행을 시트 헤더 순서대로 리스트로 변환."""
        return [str(row.get(h, '')) for h in CATALOG_HEADERS]

    def append_rows(self, rows: list) -> int:
        """신규 행 추가 (기존 SKU와 중복되지 않는 것만). 추가된 행 수 반환."""
        existing = self.get_existing_skus()
        to_add = [r for r in rows if str(r.get('sku', '')).strip() not in existing]
        if not to_add:
            logger.info('추가할 신규 행 없음')
            return 0
        values = [self._row_to_list(r) for r in to_add]
        self._ws.append_rows(values, value_input_option='USER_ENTERED')
        logger.info('%d행 추가 완료', len(to_add))
        return len(to_add)

    def update_rows(self, rows: list) -> int:
        """기존 SKU의 데이터 업데이트 (가격, 재고 등). 업데이트된 행 수 반환."""
        all_records = self._ws.get_all_records()
        # SKU → 행 번호(1-indexed, 헤더 행=1)
        sku_to_row = {
            str(r.get('sku', '')).strip(): idx + 2
            for idx, r in enumerate(all_records)
            if r.get('sku')
        }

        updated = 0
        for row in rows:
            sku = str(row.get('sku', '')).strip()
            if sku not in sku_to_row:
                continue
            row_num = sku_to_row[sku]
            # 가격·재고·이미지만 업데이트
            update_fields = {
                'buy_price': row.get('buy_price', ''),
                'buy_currency': row.get('buy_currency', ''),
                'stock': row.get('stock', 0),
                'images': row.get('images', ''),
            }
            for field, value in update_fields.items():
                if field in CATALOG_HEADERS:
                    col = CATALOG_HEADERS.index(field) + 1
                    self._ws.update_cell(row_num, col, str(value))
            updated += 1
            logger.debug('SKU %s 업데이트 완료 (행 %d)', sku, row_num)

        logger.info('%d행 업데이트 완료', updated)
        return updated

    def upsert_rows(self, rows: list) -> dict:
        """신규는 추가, 기존은 업데이트. {'added': n, 'updated': m} 반환."""
        existing = self.get_existing_skus()
        new_rows = [r for r in rows if str(r.get('sku', '')).strip() not in existing]
        existing_rows = [r for r in rows if str(r.get('sku', '')).strip() in existing]

        added = 0
        updated = 0

        if new_rows:
            values = [self._row_to_list(r) for r in new_rows]
            self._ws.append_rows(values, value_input_option='USER_ENTERED')
            added = len(new_rows)
            logger.info('%d행 신규 추가', added)

        if existing_rows:
            updated = self.update_rows(existing_rows)

        return {'added': added, 'updated': updated}

    def import_from_file(self, file_path: str, vendor_name: str) -> dict:
        """
        파일 → 로드 → 벤더 정규화 → 시트 적재 원스톱 메서드.

        Args:
            file_path: Listly 내보내기 파일 경로 (CSV/JSON)
            vendor_name: 벤더 이름 ('porter' 또는 'memo_paris')

        Returns:
            {'added': n, 'updated': m, 'skipped': k, 'errors': [...]}
        """
        loader = ListlyLoader()
        errors = []

        # 1. 파일 로드
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == '.json':
                raw_rows = loader.load_json(file_path)
            else:
                raw_rows = loader.load_csv(file_path)
        except (FileNotFoundError, ValueError) as e:
            logger.error('파일 로드 실패: %s', e)
            return {'added': 0, 'updated': 0, 'skipped': 0, 'errors': [str(e)]}

        # 2. 빈 행 제거
        raw_rows = loader.clean_raw_data(raw_rows)
        total = len(raw_rows)

        # 3. 벤더 정규화
        normalizer = get_vendor_normalizer(vendor_name)
        normalized = []
        skipped = 0
        for i, row in enumerate(raw_rows):
            try:
                normalized.append(normalizer(row))
            except Exception as e:
                skipped += 1
                msg = f'행 {i} 정규화 오류: {e}'
                errors.append(msg)
                logger.warning(msg)

        # 4. 시트 적재 (upsert)
        result = self.upsert_rows(normalized)
        result['skipped'] = skipped + (total - len(raw_rows))
        result['errors'] = errors

        logger.info(
            '적재 완료: 추가=%d, 업데이트=%d, 스킵=%d, 오류=%d',
            result['added'], result['updated'], result['skipped'], len(errors),
        )
        return result
