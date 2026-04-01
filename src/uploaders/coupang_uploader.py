"""Coupang 상품 업로더."""

import hashlib
import hmac
import logging
import math
import os
import time
from datetime import datetime, timezone

import requests

from .base_uploader import BaseUploader

logger = logging.getLogger(__name__)


class CoupangUploader(BaseUploader):
    """Coupang Wing API를 통한 상품 업로더."""

    uploader_name = 'coupang'
    marketplace = 'coupang'

    CATEGORY_MAP = {
        'ELC': '76001',
        'HOM': '76002',
        'BTY': '76003',
        'HLT': '76004',
        'TOY': '76005',
        'SPT': '76006',
        'CLO': '76007',
        'BAG': '76008',
        'BBY': '76009',
        'PET': '76010',
        'FOD': '76011',
        'OFC': '76012',
        'DIG': '76001',
    }

    API_BASE = 'https://api-gateway.coupang.com'

    def __init__(self):
        """Coupang 업로더 초기화. 환경변수에서 API 키를 읽는다."""
        self.access_key = os.getenv('COUPANG_ACCESS_KEY', '')
        self.secret_key = os.getenv('COUPANG_SECRET_KEY', '')
        self.vendor_id = os.getenv('COUPANG_VENDOR_ID', '')
        if not self.access_key:
            logger.warning('COUPANG_ACCESS_KEY is not set')
        if not self.secret_key:
            logger.warning('COUPANG_SECRET_KEY is not set')
        if not self.vendor_id:
            logger.warning('COUPANG_VENDOR_ID is not set')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_product(self, product: dict) -> dict:
        """Coupang에 상품을 업로드한다.

        Returns:
            성공: {'success': True, 'product_id': '...', 'url': '...'}
            실패: {'success': False, 'error': '...'}
        """
        try:
            payload = self._build_product_payload(product)
            path = '/v2/providers/seller_api/apis/api/v1/marketplace/seller-products'
            result = self._api_request('POST', path, data=payload)
            if 'error' in result:
                return {'success': False, 'error': result['error'], 'sku': product.get('sku', '')}
            product_id = str(result.get('data', {}).get('sellerProductId', ''))
            url = f'https://www.coupang.com/vp/products/{product_id}' if product_id else ''
            return {'success': True, 'product_id': product_id, 'url': url, 'sku': product.get('sku', '')}
        except Exception as exc:
            logger.error('upload_product failed for sku=%s: %s', product.get('sku', ''), exc)
            return {'success': False, 'error': str(exc), 'sku': product.get('sku', '')}

    def update_product(self, product_id: str, updates: dict) -> dict:
        """Coupang 상품 정보를 업데이트한다."""
        try:
            path = f'/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{product_id}'
            result = self._api_request('PUT', path, data=updates)
            if 'error' in result:
                return {'success': False, 'error': result['error']}
            return {'success': True}
        except Exception as exc:
            logger.error('update_product failed for product_id=%s: %s', product_id, exc)
            return {'success': False, 'error': str(exc)}

    def delete_product(self, product_id: str) -> bool:
        """Coupang 상품을 삭제한다."""
        try:
            path = f'/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{product_id}'
            result = self._api_request('DELETE', path)
            return 'error' not in result
        except Exception as exc:
            logger.error('delete_product failed for product_id=%s: %s', product_id, exc)
            return False

    def get_categories(self) -> list:
        """Coupang 카테고리 목록을 반환한다."""
        try:
            path = '/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-categories'
            result = self._api_request('GET', path)
            if 'error' in result:
                logger.warning('get_categories failed: %s', result['error'])
                return []
            return result.get('data', [])
        except Exception as exc:
            logger.error('get_categories failed: %s', exc)
            return []

    def prepare_product(self, collected: dict) -> dict:
        """수집된 상품을 Coupang 업로드 형식으로 변환한다."""
        if not collected:
            return {}
        title = collected.get('title_ko') or collected.get('title_original', '')
        title = '[해외직구] ' + title
        if len(title) > 50:
            title = title[:50]
        category_code = collected.get('category_code', 'GEN')
        category_id = self.CATEGORY_MAP.get(category_code, '76001')
        sell_price = collected.get('sell_price_krw', 0) or 0
        # 100원 단위로 올림
        price = int(math.ceil(sell_price / 100) * 100)
        images = (collected.get('images') or [])[:10]
        return {
            'sku': collected.get('sku', ''),
            'title': title,
            'description_html': collected.get('description_html', ''),
            'price': price,
            'original_price': collected.get('price_krw', price),
            'images': images,
            'category_id': category_id,
            'brand': collected.get('brand', ''),
            'weight_kg': collected.get('weight_kg'),
            'stock': 999,
            'options': collected.get('options', {}),
            'tags': collected.get('tags', []),
            'shipping_fee': 0,
            'delivery_days': '7-14',
            'return_info': '해외직구 상품으로 반품/교환이 불가합니다',
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_product_payload(self, product: dict) -> dict:
        """Coupang Wing API용 상품 페이로드를 구성한다."""
        images = [{'imageOrder': i, 'imageType': 'PRODUCT', 'vendorPath': url}
                  for i, url in enumerate(product.get('images', []))]
        items = [{
            'itemName': product.get('title', ''),
            'originalPrice': product.get('original_price', product.get('price', 0)),
            'salePrice': product.get('price', 0),
            'maximumBuyCount': 99,
            'maximumBuyForPerson': 0,
            'outboundShippingTimeDay': 2,
            'images': images,
            'notices': [],
            'attributes': [],
        }]
        return {
            'displayCategoryCode': product.get('category_id', '76001'),
            'sellerProductName': product.get('title', ''),
            'vendorId': self.vendor_id,
            'saleStartedAt': '2021-01-01T00:00:00',
            'saleEndedAt': '2099-12-31T00:00:00',
            'displayProductName': product.get('title', ''),
            'brand': product.get('brand', ''),
            'manufacture': '',
            'description': product.get('description_html', ''),
            'deliveryMethod': 'SEQUENCIAL',
            'deliveryCompanyCode': 'DIRECT_DELIVERY',
            'deliveryChargeType': 'FREE',
            'deliveryCharge': 0,
            'freeShipOverAmount': 0,
            'deliveryChargeOnReturn': 5000,
            'remoteAreaDeliveryCharge': 0,
            'underPriceGuarantee': False,
            'mediumCategoryType': product.get('category_id', '76001'),
            'items': items,
        }

    def _generate_hmac_signature(self, method: str, url_path: str, date: str) -> str:
        """Coupang Wing API용 HMAC-SHA256 서명을 생성한다.

        message = date + method + url_path (query string 포함)
        """
        message = date + method + url_path
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _api_request(self, method: str, path: str, data: dict = None) -> dict:
        """Coupang Wing API에 요청을 전송한다.

        Authorization: CEA algorithm=HmacSHA256, access-key={key}, signed-date={date}, signature={sig}
        429: rate limit → 재시도
        401: 인증 오류 → 즉시 반환
        500: 서버 오류 → 반환
        """
        if not self.access_key or not self.secret_key:
            return {'error': 'Missing Coupang API credentials'}
        url = self.API_BASE + path
        date = datetime.now(timezone.utc).strftime('%y%m%dT%H%M%SZ')
        signature = self._generate_hmac_signature(method, path, date)
        auth_header = (
            f'CEA algorithm=HmacSHA256, access-key={self.access_key}, '
            f'signed-date={date}, signature={signature}'
        )
        headers = {
            'Authorization': auth_header,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        for attempt in range(3):
            try:
                resp = requests.request(method, url, json=data, headers=headers, timeout=30)
                if resp.status_code == 429:
                    logger.warning('Coupang rate limit hit, retrying in %ds (attempt %d)', 5, attempt + 1)
                    time.sleep(5 * (attempt + 1))
                    continue
                if resp.status_code == 401:
                    logger.error('Coupang API auth error 401')
                    return {'error': 'Authentication failed (401)'}
                if resp.status_code >= 500:
                    logger.warning('Coupang server error %d', resp.status_code)
                    return {'error': f'Server error ({resp.status_code})'}
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as exc:
                logger.warning('Coupang API request failed (attempt %d): %s', attempt + 1, exc)
                if attempt < 2:
                    time.sleep(3)
        return {'error': 'API request failed after retries'}
