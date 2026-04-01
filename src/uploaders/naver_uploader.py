"""Naver SmartStore 상품 업로더."""

import logging
import math
import os
import time

import requests

from .base_uploader import BaseUploader

logger = logging.getLogger(__name__)


class NaverSmartStoreUploader(BaseUploader):
    """Naver Commerce API (SmartStore)를 통한 상품 업로더."""

    uploader_name = 'naver_smartstore'
    marketplace = 'naver'

    CATEGORY_MAP = {
        'ELC': '50000003',
        'HOM': '50000004',
        'BTY': '50000002',
        'CLO': '50000000',
        'BAG': '50000001',
        'SPT': '50000007',
        'BBY': '50000005',
        'FOD': '50000006',
        'PET': '50000008',
        'TOY': '50000009',
        'HLT': '50000010',
    }

    API_BASE = 'https://api.commerce.naver.com/external'
    _TOKEN_URL = 'https://api.commerce.naver.com/external/v1/oauth2/token'

    def __init__(self):
        """Naver SmartStore 업로더 초기화. 환경변수에서 API 키를 읽는다."""
        self.client_id = os.getenv('NAVER_CLIENT_ID', '')
        self.client_secret = os.getenv('NAVER_CLIENT_SECRET', '')
        self.channel_id = os.getenv('NAVER_CHANNEL_ID', '')
        if not self.client_id:
            logger.warning('NAVER_CLIENT_ID is not set')
        if not self.client_secret:
            logger.warning('NAVER_CLIENT_SECRET is not set')
        self._access_token = None
        self._token_expires = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_product(self, product: dict) -> dict:
        """Naver SmartStore에 상품을 업로드한다.

        Returns:
            성공: {'success': True, 'product_id': '...', 'url': '...'}
            실패: {'success': False, 'error': '...'}
        """
        try:
            payload = self._build_product_payload(product)
            path = '/v2/products'
            result = self._api_request('POST', path, data=payload)
            if 'error' in result:
                return {'success': False, 'error': result['error'], 'sku': product.get('sku', '')}
            product_id = str(result.get('originProductNo', ''))
            url = f'https://smartstore.naver.com/main/products/{product_id}' if product_id else ''
            return {'success': True, 'product_id': product_id, 'url': url, 'sku': product.get('sku', '')}
        except Exception as exc:
            logger.error('upload_product failed for sku=%s: %s', product.get('sku', ''), exc)
            return {'success': False, 'error': str(exc), 'sku': product.get('sku', '')}

    def update_product(self, product_id: str, updates: dict) -> dict:
        """Naver SmartStore 상품 정보를 업데이트한다."""
        try:
            path = f'/v2/products/origin-products/{product_id}'
            result = self._api_request('PUT', path, data=updates)
            if 'error' in result:
                return {'success': False, 'error': result['error']}
            return {'success': True}
        except Exception as exc:
            logger.error('update_product failed for product_id=%s: %s', product_id, exc)
            return {'success': False, 'error': str(exc)}

    def delete_product(self, product_id: str) -> bool:
        """Naver SmartStore 상품을 삭제한다."""
        try:
            path = f'/v2/products/origin-products/{product_id}'
            result = self._api_request('DELETE', path)
            return 'error' not in result
        except Exception as exc:
            logger.error('delete_product failed for product_id=%s: %s', product_id, exc)
            return False

    def get_categories(self) -> list:
        """Naver Commerce 카테고리 목록을 반환한다."""
        try:
            path = '/v1/product-models/search?categoryDepth=1'
            result = self._api_request('GET', path)
            if 'error' in result:
                logger.warning('get_categories failed: %s', result['error'])
                return []
            return result.get('simpleProductModels', [])
        except Exception as exc:
            logger.error('get_categories failed: %s', exc)
            return []

    def prepare_product(self, collected: dict) -> dict:
        """수집된 상품을 Naver SmartStore 업로드 형식으로 변환한다."""
        if not collected:
            return {}
        title = collected.get('title_ko') or collected.get('title_original', '')
        title = '[해외직구] ' + title
        sell_price = collected.get('sell_price_krw', 0) or 0
        # 10원 단위로 올림
        price = int(math.ceil(sell_price / 10) * 10)
        category_code = collected.get('category_code', 'GEN')
        category_id = self.CATEGORY_MAP.get(category_code, '50000000')
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
        """Naver Commerce API용 상품 페이로드를 구성한다."""
        images = [{'url': url, 'representativeImage': (i == 0)}
                  for i, url in enumerate(product.get('images', []))]
        return {
            'originProduct': {
                'statusType': 'SALE',
                'saleType': 'NEW',
                'leafCategoryId': product.get('category_id', '50000000'),
                'name': product.get('title', ''),
                'detailContent': product.get('description_html', ''),
                'images': {'representativeImage': {'url': images[0]['url'] if images else ''},
                           'optionalImages': images[1:] if len(images) > 1 else []},
                'salePrice': product.get('price', 0),
                'stockQuantity': product.get('stock', 999),
                'deliveryInfo': {
                    'deliveryType': 'DIRECT_DELIVERY',
                    'deliveryAttributeType': 'NORMAL',
                    'deliveryFee': {
                        'deliveryFeeType': 'FREE',
                    },
                },
                'detailAttribute': {
                    'naverShoppingSearchInfo': {
                        'manufacturerName': product.get('brand', ''),
                        'brandName': product.get('brand', ''),
                    },
                    'afterServiceInfo': {
                        'afterServiceTelephoneNumber': '',
                        'afterServiceGuideContent': product.get('return_info', ''),
                    },
                    'purchaseQuantityInfo': {
                        'minPurchaseQuantity': 1,
                        'maxPurchaseQuantityPer1Time': 99,
                    },
                    'originAreaInfo': {
                        'originAreaCode': '0200037',  # 해외
                        'importer': '해외직구',
                    },
                    'sellerCodeInfo': {'sellerManagementCode': product.get('sku', '')},
                },
            },
            'smartstoreChannelProduct': {
                'channelProductDisplayStatusType': 'ON',
            },
        }

    def _get_access_token(self) -> str:
        """OAuth2 client_credentials 방식으로 액세스 토큰을 취득한다.

        토큰이 유효하면 캐시된 값을 반환하고, 만료 시 재발급한다.
        """
        now = time.time()
        if self._access_token and now < self._token_expires - 60:
            return self._access_token
        if not self.client_id or not self.client_secret:
            return ''
        try:
            resp = requests.post(
                self._TOKEN_URL,
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'type': 'SELF',
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get('access_token', '')
            expires_in = int(data.get('expires_in', 3600))
            self._token_expires = now + expires_in
            return self._access_token
        except Exception as exc:
            logger.error('_get_access_token failed: %s', exc)
            return ''

    def _api_request(self, method: str, path: str, data: dict = None) -> dict:
        """Naver Commerce API에 요청을 전송한다."""
        if not self.client_id or not self.client_secret:
            return {'error': 'Missing Naver API credentials'}
        token = self._get_access_token()
        if not token:
            return {'error': 'Failed to obtain access token'}
        url = self.API_BASE + path
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json;charset=UTF-8',
        }
        for attempt in range(3):
            try:
                resp = requests.request(method, url, json=data, headers=headers, timeout=30)
                if resp.status_code == 429:
                    logger.warning('Naver rate limit hit, retrying in %ds (attempt %d)', 5, attempt + 1)
                    time.sleep(5 * (attempt + 1))
                    continue
                if resp.status_code == 401:
                    # 토큰 무효화 후 재시도
                    self._access_token = None
                    self._token_expires = 0
                    if attempt < 2:
                        token = self._get_access_token()
                        headers['Authorization'] = f'Bearer {token}'
                        continue
                    return {'error': 'Authentication failed (401)'}
                if resp.status_code >= 500:
                    logger.warning('Naver server error %d', resp.status_code)
                    return {'error': f'Server error ({resp.status_code})'}
                resp.raise_for_status()
                if resp.content:
                    return resp.json()
                return {}
            except requests.exceptions.RequestException as exc:
                logger.warning('Naver API request failed (attempt %d): %s', attempt + 1, exc)
                if attempt < 2:
                    time.sleep(3)
        return {'error': 'API request failed after retries'}
