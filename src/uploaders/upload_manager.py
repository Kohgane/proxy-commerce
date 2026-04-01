"""업로드 관리자 — 수집된 상품을 각 마켓플레이스에 업로드하고 이력을 관리한다."""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class UploadManager:
    """마켓플레이스 업로드 통합 관리자."""

    SUPPORTED_MARKETS = ('coupang', 'naver')

    def __init__(self):
        """UploadManager 초기화."""
        self.sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
        self.upload_worksheet_name = os.getenv('UPLOAD_WORKSHEET', 'upload_history')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_to_market(self, skus: list, market: str, dry_run: bool = False) -> dict:
        """지정한 SKU 목록을 마켓플레이스에 업로드한다.

        1. CollectionManager에서 상품 데이터 조회
        2. uploader.prepare_product()으로 형식 변환
        3. 업로드 (dry_run=True이면 스킵)
        4. 업로드 이력을 Sheets에 기록
        5. 결과 반환

        Args:
            skus:    업로드할 SKU 목록
            market:  대상 마켓플레이스 ('coupang', 'naver')
            dry_run: True이면 실제 업로드 없이 결과만 반환

        Returns:
            {'total': N, 'success': M, 'failed': K, 'results': [...]}
        """
        result = {'total': len(skus), 'success': 0, 'failed': 0, 'results': []}
        if not skus:
            return result
        try:
            uploader = self._get_uploader(market)
        except ValueError as exc:
            logger.error('upload_to_market: %s', exc)
            result['failed'] = len(skus)
            result['results'] = [{'success': False, 'error': str(exc), 'sku': sku} for sku in skus]
            return result

        collected_map = self._fetch_products_by_sku(skus)

        for sku in skus:
            collected = collected_map.get(sku)
            if not collected:
                logger.warning('upload_to_market: product not found for sku=%s', sku)
                result['failed'] += 1
                result['results'].append({'success': False, 'error': 'Product not found', 'sku': sku})
                continue
            try:
                prepared = uploader.prepare_product(collected)
                if dry_run:
                    item_result = {'success': True, 'dry_run': True, 'sku': sku, 'prepared': prepared}
                    result['success'] += 1
                else:
                    item_result = uploader.upload_product(prepared)
                    item_result['sku'] = sku
                    if item_result.get('success'):
                        result['success'] += 1
                        self._record_upload(sku, market, item_result)
                    else:
                        result['failed'] += 1
                result['results'].append(item_result)
            except Exception as exc:
                logger.error('upload_to_market: error for sku=%s: %s', sku, exc)
                result['failed'] += 1
                result['results'].append({'success': False, 'error': str(exc), 'sku': sku})

        return result

    def upload_all_pending(self, market: str, dry_run: bool = False) -> dict:
        """아직 마켓에 업로드되지 않은 수집 상품을 모두 업로드한다.

        Args:
            market:  대상 마켓플레이스
            dry_run: True이면 실제 업로드 없이 결과만 반환
        """
        pending_skus = self._get_pending_skus(market)
        if not pending_skus:
            logger.info('upload_all_pending: no pending products for market=%s', market)
            return {'total': 0, 'success': 0, 'failed': 0, 'results': []}
        logger.info('upload_all_pending: found %d pending SKUs for market=%s', len(pending_skus), market)
        return self.upload_to_market(pending_skus, market, dry_run=dry_run)

    def sync_prices(self, market: str, dry_run: bool = False) -> dict:
        """이미 업로드된 상품의 가격을 재계산하여 업데이트한다.

        Args:
            market:  대상 마켓플레이스
            dry_run: True이면 실제 업데이트 없이 결과만 반환
        """
        result = {'total': 0, 'success': 0, 'failed': 0, 'results': []}
        try:
            uploader = self._get_uploader(market)
            history = self.get_upload_history({'market': market, 'status': 'success'})
            result['total'] = len(history)
            for record in history:
                sku = record.get('sku', '')
                product_id = record.get('product_id', '')
                if not product_id:
                    result['failed'] += 1
                    continue
                try:
                    collected_map = self._fetch_products_by_sku([sku])
                    collected = collected_map.get(sku)
                    if not collected:
                        result['failed'] += 1
                        continue
                    prepared = uploader.prepare_product(collected)
                    price_update = {'salePrice': prepared.get('price', 0)}
                    if dry_run:
                        result['success'] += 1
                        result['results'].append({'success': True, 'dry_run': True, 'sku': sku, 'new_price': prepared.get('price')})
                        continue
                    update_result = uploader.update_product(product_id, price_update)
                    if update_result.get('success'):
                        result['success'] += 1
                    else:
                        result['failed'] += 1
                    result['results'].append({'sku': sku, **update_result})
                except Exception as exc:
                    logger.error('sync_prices: error for sku=%s: %s', sku, exc)
                    result['failed'] += 1
        except Exception as exc:
            logger.error('sync_prices failed: %s', exc)
        return result

    def get_upload_history(self, filters: dict = None) -> list:
        """Sheets upload_history 시트에서 업로드 이력을 조회한다."""
        try:
            ws = self._get_upload_worksheet()
            rows = ws.get_all_records()
            if not filters:
                return rows
            result = []
            for row in rows:
                match = True
                for key, val in filters.items():
                    if str(row.get(key, '')) != str(val):
                        match = False
                        break
                if match:
                    result.append(row)
            return result
        except Exception as exc:
            logger.error('get_upload_history failed: %s', exc)
            return []

    def generate_report(self) -> dict:
        """마켓별 업로드 현황 리포트를 생성한다."""
        try:
            history = self.get_upload_history()
            report = {'total': len(history), 'by_market': {}, 'by_status': {}}
            for record in history:
                market = record.get('market', 'unknown')
                status = record.get('status', 'unknown')
                report['by_market'][market] = report['by_market'].get(market, 0) + 1
                report['by_status'][status] = report['by_status'].get(status, 0) + 1
            return report
        except Exception as exc:
            logger.error('generate_report failed: %s', exc)
            return {'total': 0, 'by_market': {}, 'by_status': {}}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_uploader(self, market: str):
        """마켓플레이스에 맞는 업로더 인스턴스를 반환한다."""
        if market == 'coupang':
            from src.uploaders.coupang_uploader import CoupangUploader
            return CoupangUploader()
        if market == 'naver':
            from src.uploaders.naver_uploader import NaverSmartStoreUploader
            return NaverSmartStoreUploader()
        raise ValueError(f'Unsupported market: {market}. Use one of {self.SUPPORTED_MARKETS}')

    def _fetch_products_by_sku(self, skus: list) -> dict:
        """CollectionManager에서 SKU 목록에 해당하는 상품을 조회한다.

        Returns:
            {sku: product_dict, ...}
        """
        result = {}
        try:
            from src.collectors.collection_manager import CollectionManager
            mgr = CollectionManager()
            all_products = mgr.get_collected()
            for product in all_products:
                sku = product.get('sku', '')
                if sku in skus:
                    result[sku] = product
        except Exception as exc:
            logger.error('_fetch_products_by_sku failed: %s', exc)
        return result

    def _get_pending_skus(self, market: str) -> list:
        """아직 해당 마켓에 업로드되지 않은 SKU 목록을 반환한다."""
        try:
            from src.collectors.collection_manager import CollectionManager
            mgr = CollectionManager()
            all_products = mgr.get_collected()
            uploaded_skus = {r.get('sku', '') for r in self.get_upload_history({'market': market})}
            return [
                p.get('sku', '') for p in all_products
                if p.get('sku') and p.get('sku') not in uploaded_skus
            ]
        except Exception as exc:
            logger.error('_get_pending_skus failed: %s', exc)
            return []

    def _record_upload(self, sku: str, market: str, upload_result: dict) -> None:
        """업로드 성공 이력을 Sheets에 기록한다."""
        try:
            ws = self._get_upload_worksheet()
            row = [
                sku,
                market,
                upload_result.get('product_id', ''),
                upload_result.get('url', ''),
                'success',
                datetime.now(timezone.utc).isoformat(),
            ]
            ws.append_row(row)
        except Exception as exc:
            logger.warning('_record_upload failed for sku=%s: %s', sku, exc)

    def _get_upload_worksheet(self):
        """Google Sheets upload_history 워크시트를 반환한다."""
        from src.utils.sheets import open_sheet
        return open_sheet(self.sheet_id, self.upload_worksheet_name)
