"""Naver SmartStore 상품 업로더."""

import logging
import math
import os
import time

import requests

from src.market_relay import RelayError, relay_request

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

    # ── P5 정본 승계(오너 SSH 실측 `ss_upload.py`) — 추측 금지, 실증값만 ────────────
    #   쿠팡과 **다른 축**이다: 계정 = chezgoga / gocosmos (쿠팡 고가네/우주대행과 별개).
    ACCOUNT_PREFIXES = {'chezgoga': 'NAVER_CHEZGOGA', 'gocosmos': 'NAVER_GOCOSMOS'}
    # 출고지/반품지 주소 ID — 정본 스크립트는 하드코딩이었으나 **env화**(하드코딩 금지·오너 지시).
    #   기본값이 곧 실증값이라 env 미설정이어도 정본으로 등록된다(계정별 오버라이드 가능).
    DEFAULT_ADDRESS_IDS = {
        'chezgoga': {'ship': '107519271', 'return': '107519270'},
        'gocosmos': {'ship': '107987297', 'return': '107987296'},
    }
    DEFAULT_LEAF_CATEGORY = '50004132'      # 정본 기본 리프 카테고리
    # 구매대행 통관 · 반품/교환비 · 판매상태 — 전부 정본 승계.
    CUSTOMS_TAX_TYPE = 'PURCHASE_AGENT'
    RETURN_FEE = 25000
    EXCHANGE_FEE = 50000
    STATUS_TYPE = 'SALE'
    STOCK_QUANTITY = 999
    NAVER_SHOPPING_REGISTRATION = True
    # 원산지 — **스마트스토어 정본**(쿠팡과 다른 허용 문구·실증됨). 어댑터별 원산지 정책 분기.
    ORIGIN_AREA_CODE = '03'
    ORIGIN_AREA_CONTENT = '상세설명에 표시'
    # 이미지 업로드(정본 `naver_img.upload` 상당) — 실패 시 등록 차단(정본과 동일).
    IMAGE_UPLOAD_PATH = '/v1/product-images/upload'

    def __init__(self, account: str = None):
        """Naver SmartStore 업로더 초기화. 환경변수에서 API 키를 읽는다.

        네이버 커머스 자격증명은 코드 경로에 따라 두 이름이 혼용되어 왔다.
        업로드/읽기 진단이 같은 값을 쓰도록 NAVER_COMMERCE_* 를 폴백으로 허용한다.
        """
        self.account = (account or '').strip().lower() or None
        self.client_id = self._acct_env('NAVER_CLIENT_ID') or os.getenv('NAVER_COMMERCE_CLIENT_ID', '')
        self.client_secret = (self._acct_env('NAVER_CLIENT_SECRET')
                              or os.getenv('NAVER_COMMERCE_CLIENT_SECRET', ''))
        self.channel_id = self._acct_env('NAVER_CHANNEL_ID')
        # 출고지/반품지 주소 ID — env 우선, 미설정이면 정본 실증값(계정별).
        _addr = self.DEFAULT_ADDRESS_IDS.get(self.account or '', {})
        self.ship_address_id = self._acct_env('NAVER_SHIP_ADDRESS_ID', _addr.get('ship', ''))
        self.return_address_id = self._acct_env('NAVER_RETURN_ADDRESS_ID', _addr.get('return', ''))
        if not self.client_id:
            logger.warning('NAVER_CLIENT_ID is not set')
        if not self.client_secret:
            logger.warning('NAVER_CLIENT_SECRET is not set')
        self._access_token = None
        self._token_expires = 0

    def _acct_env(self, base_env: str, default: str = '') -> str:
        """계정 접두 우선 env 읽기 — 쿠팡 `_ship_env`와 동형 규약(계정 간 혼입 방지).

        base_env='NAVER_SHIP_ADDRESS_ID' → account='chezgoga'면 `NAVER_CHEZGOGA_SHIP_ADDRESS_ID` 우선,
        없으면 무접두 `NAVER_SHIP_ADDRESS_ID`, 그래도 없으면 default(정본 실증값).
        """
        prefix = self.ACCOUNT_PREFIXES.get(self.account or '')
        if prefix:
            suffix = base_env[len('NAVER_'):]
            val = os.getenv(f'{prefix}_{suffix}', '').strip()
            if val:
                return val
        return os.getenv(base_env, '').strip() or default

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
        """Naver Commerce API 상품 페이로드 — **정본 승계**(오너 SSH 실측 ss_upload.py).

        쿠팡과 **다른 값**을 쓰는 지점(어댑터 4지점 중 원산지·배송·카테고리):
          · 원산지 = `originAreaCode "03"` + `"상세설명에 표시"` (스마트스토어 허용 문구·실증)
          · 통관 = `customsTaxType PURCHASE_AGENT`(구매대행)
          · 반품 25,000 / 교환 50,000 · statusType SALE · 재고 999 · 네이버쇼핑 등록 True
          · 출고지/반품지 = 주소 ID(env, 기본값=정본 실증값)
        추측 금지 — 여기 값은 전부 통과 이력이 있는 스크립트에서 온 것이다.
        """
        images = [u for u in (product.get('images') or []) if u]
        rep = images[0] if images else ''
        optional = [{'url': u} for u in images[1:]]
        price = int(product.get('price', 0) or 0)
        return {
            'originProduct': {
                'statusType': self.STATUS_TYPE,
                'saleType': 'NEW',
                'leafCategoryId': str(product.get('category_id') or self.DEFAULT_LEAF_CATEGORY),
                'name': (product.get('title') or '')[:100],
                'detailContent': product.get('description_html', ''),
                'images': {'representativeImage': {'url': rep}, 'optionalImages': optional},
                'salePrice': price,
                'stockQuantity': self.STOCK_QUANTITY,
                'deliveryInfo': {
                    'deliveryType': 'DELIVERY',
                    'deliveryAttributeType': 'NORMAL',
                    'deliveryCompany': self._acct_env('NAVER_DELIVERY_COMPANY', 'CJGLS'),
                    'deliveryFee': {'deliveryFeeType': 'FREE'},
                    'claimDeliveryInfo': {
                        # 정본: 반품 25,000 / 교환 50,000 (해외 구매대행 실비).
                        'returnDeliveryFee': self.RETURN_FEE,
                        'exchangeDeliveryFee': self.EXCHANGE_FEE,
                        'shippingAddressId': self._as_int(self.ship_address_id),
                        'returnAddressId': self._as_int(self.return_address_id),
                    },
                },
                'detailAttribute': {
                    'naverShoppingSearchInfo': {
                        'manufacturerName': product.get('brand', ''),
                        'brandName': product.get('brand', ''),
                    },
                    'afterServiceInfo': {
                        'afterServiceTelephoneNumber': self._acct_env('NAVER_AS_PHONE'),
                        'afterServiceGuideContent': product.get('return_info', '')
                                                    or '해외 구매대행 상품입니다.',
                    },
                    'purchaseQuantityInfo': {
                        'minPurchaseQuantity': 1, 'maxPurchaseQuantityPer1Time': 99,
                    },
                    # ★ 원산지 정본 — 쿠팡과 다른 축(마켓별 원산지 정책 분기).
                    'originAreaInfo': {
                        'originAreaCode': self.ORIGIN_AREA_CODE,
                        'content': self.ORIGIN_AREA_CONTENT,
                    },
                    'sellerCodeInfo': {'sellerManagementCode': product.get('sku', '')},
                    # 구매대행 통관(정본).
                    'customsTaxType': self.CUSTOMS_TAX_TYPE,
                },
            },
            'smartstoreChannelProduct': {
                'channelProductDisplayStatusType': 'ON',
                'naverShoppingRegistration': self.NAVER_SHOPPING_REGISTRATION,
            },
        }

    @staticmethod
    def _as_int(v):
        """주소 ID 등 정본상 int로 보내야 하는 값. 숫자가 아니면 원본 유지(정직)."""
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return v

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
            # v87-S7: 토큰 발급도 **릴레이 경유**(단일 관문). 직결로 나가면 네이버가 IP로 막아
            #   토큰을 못 받고, 그 뒤 모든 호출이 연쇄 실패한다(GW.IP_NOT_ALLOWED).
            resp = relay_request(
                'POST', self._TOKEN_URL,
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'type': 'SELF',
                },
                timeout=15, market="smartstore", key=str(self.client_id or ""),
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
                # 고정 IP 릴레이 경유 — 네이버 호출 IP 화이트리스트 대응(v8 / v87-S6-2 mkt.php).
                resp = relay_request(method, url, json=data, headers=headers, timeout=30,
                                     market="smartstore", key=str(self.client_id or ""))
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
