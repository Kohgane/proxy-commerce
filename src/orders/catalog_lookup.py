"""Google Sheets 카탈로그에서 SKU로 상품을 조회하는 모듈."""

import os
import logging

logger = logging.getLogger(__name__)

# SKU 접두어 → 벤더 이름 매핑
SKU_PREFIX_VENDOR = {
    'PTR': 'porter',
    'MMP': 'memo_paris',
}


class CatalogLookup:
    """Google Sheets 카탈로그에서 SKU로 상품을 조회하는 클래스."""

    def __init__(self, sheet_id: str = None, worksheet: str = 'catalog'):
        """Google Sheets 연결. sheet_id 미지정 시 GOOGLE_SHEET_ID 환경변수 사용."""
        self._sheet_id = sheet_id or os.getenv('GOOGLE_SHEET_ID', '')
        self._worksheet = worksheet
        self._cache: list[dict] | None = None  # 시트 전체 행 캐시

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _load_records(self) -> list[dict]:
        """시트 전체 행을 로드. 이미 캐시되어 있으면 캐시 반환."""
        if self._cache is not None:
            return self._cache
        from ..utils.sheets import open_sheet
        ws = open_sheet(self._sheet_id, self._worksheet)
        self._cache = ws.get_all_records()
        logger.debug("CatalogLookup: loaded %d rows from sheet", len(self._cache))
        return self._cache

    # ── 공개 API ────────────────────────────────────────────

    def lookup_by_sku(self, sku: str) -> dict | None:
        """SKU로 카탈로그 행을 조회. 없으면 None 반환.

        반환 dict 키: sku, title_ko, title_en, src_url, buy_currency,
        buy_price, source_country, vendor, forwarder, …
        """
        if not sku:
            return None
        records = self._load_records()
        for row in records:
            if str(row.get('sku', '')).strip() == sku.strip():
                return row
        return None

    def lookup_batch(self, skus: list[str]) -> dict[str, dict]:
        """여러 SKU를 한 번에 조회. {sku: catalog_row} 딕셔너리 반환.

        시트 전체를 1회만 읽고 메모리에서 매칭 (API 호출 최소화).
        """
        result: dict[str, dict] = {}
        if not skus:
            return result
        records = self._load_records()
        wanted = {s.strip() for s in skus if s}
        for row in records:
            row_sku = str(row.get('sku', '')).strip()
            if row_sku in wanted:
                result[row_sku] = row
        return result

    def get_vendor_info(self, sku: str) -> dict:
        """SKU에서 벤더 정보를 추출.

        Returns:
            {
                'vendor_name': 'PORTER' or 'MEMO_PARIS',
                'source_country': 'JP' or 'FR',
                'buy_currency': 'JPY' or 'EUR',
                'forwarder': 'zenmarket' or '',
                'src_url': '원본 URL' (카탈로그에 있는 경우),
            }
        """
        row = self.lookup_by_sku(sku) or {}
        prefix = (sku or '').split('-')[0].upper()
        vendor_key = SKU_PREFIX_VENDOR.get(prefix, '')

        if vendor_key == 'porter':
            defaults = {
                'vendor_name': 'PORTER',
                'source_country': 'JP',
                'buy_currency': 'JPY',
                'forwarder': 'zenmarket',
            }
        elif vendor_key == 'memo_paris':
            defaults = {
                'vendor_name': 'MEMO_PARIS',
                'source_country': 'FR',
                'buy_currency': 'EUR',
                'forwarder': '',
            }
        else:
            defaults = {
                'vendor_name': str(row.get('vendor', '')).upper() or 'UNKNOWN',
                'source_country': str(row.get('source_country', '')),
                'buy_currency': str(row.get('buy_currency', '')),
                'forwarder': str(row.get('forwarder', '')),
            }

        return {
            **defaults,
            'src_url': str(row.get('src_url', '')),
        }
