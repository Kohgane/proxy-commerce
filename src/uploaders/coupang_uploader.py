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

    # 쿠팡 등록에 필요한 셀러 고유 출고지/반품지 설정(Wing 배송정보).
    # 추측 불가 — 환경변수로 받고 없으면 정직하게 실패시킨다.
    SHIPPING_ENV_FIELDS = {
        'COUPANG_VENDOR_USER_ID': 'vendor_user_id',          # Wing 로그인 ID
        'COUPANG_RETURN_CENTER_CODE': 'return_center_code',  # 반품지센터코드
        'COUPANG_OUTBOUND_SHIPPING_PLACE_CODE': 'outbound_place_code',  # 출고지코드
        'COUPANG_RETURN_ZIP_CODE': 'return_zip',             # 반품지우편번호
        'COUPANG_RETURN_ADDRESS': 'return_addr',             # 반품지주소
        'COUPANG_RETURN_CHARGE_NAME': 'return_charge_name',  # 반품지담당자명
        'COUPANG_COMPANY_CONTACT_NUMBER': 'company_contact',  # 반품지연락처
    }

    def __init__(self):
        """Coupang 업로더 초기화. 환경변수에서 API 키·배송정보를 읽는다."""
        self.access_key = os.getenv('COUPANG_ACCESS_KEY', '')
        self.secret_key = os.getenv('COUPANG_SECRET_KEY', '')
        self.vendor_id = os.getenv('COUPANG_VENDOR_ID', '')
        # 셀러 고유 출고지/반품지/Wing ID (Wing > 업체정보 > 배송정보에서 확인)
        self.vendor_user_id = os.getenv('COUPANG_VENDOR_USER_ID', '')
        self.return_center_code = os.getenv('COUPANG_RETURN_CENTER_CODE', '')
        self.outbound_place_code = os.getenv('COUPANG_OUTBOUND_SHIPPING_PLACE_CODE', '')
        self.return_zip = os.getenv('COUPANG_RETURN_ZIP_CODE', '')
        self.return_addr = os.getenv('COUPANG_RETURN_ADDRESS', '')
        self.return_addr_detail = os.getenv('COUPANG_RETURN_ADDRESS_DETAIL', '')
        self.return_charge_name = os.getenv('COUPANG_RETURN_CHARGE_NAME', '')
        self.company_contact = os.getenv('COUPANG_COMPANY_CONTACT_NUMBER', '')
        try:
            self.return_charge = int(os.getenv('COUPANG_RETURN_CHARGE', '5000') or 5000)
        except (TypeError, ValueError):
            self.return_charge = 5000
        # 해외구매대행 여부(기본: 일반 — 추가 인증요건 회피). 1/true 시 구매대행 표기.
        self.overseas_purchased = str(
            os.getenv('COUPANG_OVERSEAS_PURCHASED', '0')
        ).lower() in ('1', 'true', 'yes')
        if not self.access_key:
            logger.warning('COUPANG_ACCESS_KEY is not set')
        if not self.secret_key:
            logger.warning('COUPANG_SECRET_KEY is not set')
        if not self.vendor_id:
            logger.warning('COUPANG_VENDOR_ID is not set')

    def _missing_shipping_config(self) -> list:
        """쿠팡 등록 필수 출고지/반품지 설정 중 누락된 환경변수명 목록."""
        return [
            env for env, attr in self.SHIPPING_ENV_FIELDS.items()
            if not str(getattr(self, attr, '') or '').strip()
        ]

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
            missing = self._missing_shipping_config()
            if missing:
                # 출고지/반품지 미설정 → 쿠팡이 반드시 거부. 가짜 성공 금지(정직).
                return {
                    'success': False,
                    'error': (
                        '쿠팡 출고지/반품지 정보 미설정으로 등록 불가. '
                        '다음 환경변수를 Wing 배송정보 값으로 설정하세요: '
                        + ', '.join(missing)
                    ),
                    'sku': product.get('sku', ''),
                }
            payload = self._build_product_payload(product)
            path = '/v2/providers/seller_api/apis/api/v1/marketplace/seller-products'
            result = self._api_request('POST', path, data=payload)
            if 'error' in result:
                return {'success': False, 'error': result['error'], 'sku': product.get('sku', '')}
            # 쿠팡 응답의 data는 sellerProductId(숫자) 또는 {"sellerProductId": ...} 또는 null일 수 있다.
            data = result.get('data')
            if isinstance(data, dict):
                product_id = str(data.get('sellerProductId') or '')
            elif isinstance(data, (int, str)):
                product_id = str(data)
            else:
                product_id = ''
            code = str(result.get('code') or '').upper()
            if not product_id and code and code not in ('SUCCESS', '200', 'OK'):
                # data null + 비성공 코드 = 등록 거부 → 가짜 성공 금지(정직)
                msg = result.get('message') or f'코드 {code}'
                return {'success': False, 'error': f'쿠팡 등록 거부: {msg}', 'sku': product.get('sku', '')}
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
            return result.get('data') or []
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

    # 쿠팡 '기타 재화' 상품고시정보 표준 항목(필수). 값은 상세페이지 참조로 채운다.
    _NOTICE_CATEGORY = '기타 재화'
    _NOTICE_DETAILS = [
        '품명 및 모델명',
        '법에 의한 인증·허가 등을 받았음을 확인할 수 있는 경우 그에 대한 사항',
        '제조국 또는 원산지',
        '제조자/수입자',
        'A/S 책임자와 전화번호 또는 소비자상담 관련 전화번호',
    ]

    def _build_notices(self, product: dict) -> list:
        """옵션 상품고시정보(notices). 비우면 쿠팡이 거부 → 표준 항목을 채운다."""
        phone = self.company_contact or '상세페이지 참조'
        notices = []
        for detail in self._NOTICE_DETAILS:
            content = phone if '전화번호' in detail else '상품 상세페이지 참조'
            notices.append({
                'noticeCategoryName': self._NOTICE_CATEGORY,
                'noticeCategoryDetailName': detail,
                'content': content,
            })
        return notices

    def _build_contents(self, product: dict) -> list:
        """옵션 상세컨텐츠(contents). 비우면 쿠팡이 거부 → 상세설명 HTML/텍스트로 채운다."""
        body = (product.get('description_html') or '').strip()
        if not body:
            body = product.get('title', '') or '상품 상세페이지를 참조해 주세요.'
        is_html = '<' in body and '>' in body
        return [{
            'contentsType': 'HTML' if is_html else 'TEXT',
            'contentDetails': [{
                'content': body,
                'detailType': 'HTML' if is_html else 'TEXT',
            }],
        }]

    def _build_images(self, product: dict) -> list:
        """옵션 이미지. 첫 장은 REPRESENTATION(대표), 나머지는 DETAIL이어야 한다."""
        images = []
        for i, url in enumerate(product.get('images', [])):
            if not url:
                continue
            images.append({
                'imageOrder': i,
                'imageType': 'REPRESENTATION' if i == 0 else 'DETAIL',
                'vendorPath': url,
            })
        return images

    def _build_product_payload(self, product: dict) -> dict:
        """Coupang Wing API용 상품 페이로드를 구성한다.

        쿠팡 createProduct 필수 필드를 모두 채운다(null/누락 시 등록 거부).
        - 옵션(items[])별: 과세/성인/단위수량/최대구매수량기간/해외구매대행/이미지/고시정보/컨텐츠
        - 상품(root): 묶음배송/도서산간/반품지(주소·우편번호·담당자·연락처·배송비)/출고지/vendorUserId
        """
        title = product.get('title', '') or '상품'
        category_code = product.get('category_id', '76001')
        try:
            stock = int(product.get('stock', 99) or 99)
        except (TypeError, ValueError):
            stock = 99
        tags = product.get('tags') or []
        search_tags = [str(t) for t in tags][:20] if isinstance(tags, list) else []

        item = {
            'itemName': title,
            'originalPrice': product.get('original_price', product.get('price', 0)),
            'salePrice': product.get('price', 0),
            'maximumBuyCount': stock,                       # 판매가능재고
            'maximumBuyForPersonPeriod': 1,                 # 최대구매수량 기간(일)
            'maximumBuyForPerson': 0,                       # 인당 최대구매수량(0=제한없음)
            'outboundShippingTimeDay': 2,                   # 출고소요일
            'unitCount': 1,                                 # 단위수량
            'adultOnly': 'EVERYONE',                        # 성인여부
            'taxType': 'TAX',                               # 과세여부
            'parallelImported': 'NOT_PARALLEL_IMPORTED',    # 병행수입 아님
            'overseasPurchased': (
                'OVERSEAS_PURCHASED' if self.overseas_purchased
                else 'NOT_OVERSEAS_PURCHASED'
            ),                                              # 해외구매대행 여부
            'pccNeeded': bool(self.overseas_purchased),     # 개인통관고유부호 필요여부
            'externalVendorSku': product.get('sku', ''),
            'emptyBarcodeYn': 'Y',                          # 바코드 없음
            'emptyBarcodeReason': '해외 상품으로 바코드 미보유',
            'searchTags': search_tags,
            'images': self._build_images(product),
            'notices': self._build_notices(product),        # 상품고시정보(필수)
            'contents': self._build_contents(product),      # 상세컨텐츠(필수)
            'attributes': [],
        }
        return {
            'displayCategoryCode': category_code,
            'sellerProductName': title,
            'vendorId': self.vendor_id,
            'saleStartedAt': '2021-01-01T00:00:00',
            'saleEndedAt': '2099-12-31T00:00:00',
            'displayProductName': title,
            'generalProductName': title,
            'brand': product.get('brand', ''),
            'manufacture': product.get('brand', '') or '상세페이지 참조',
            'productGroup': '',
            'description': product.get('description_html', ''),
            # 배송
            'deliveryMethod': 'SEQUENCIAL',
            'deliveryCompanyCode': 'DIRECT_DELIVERY',
            'deliveryChargeType': 'FREE',
            'deliveryCharge': 0,
            'freeShipOverAmount': 0,
            'deliveryChargeOnReturn': self.return_charge,
            'remoteAreaDeliverable': 'N',                   # 도서산간 배송여부
            'unionDeliveryType': 'NOT_UNION_DELIVERY',      # 묶음배송 여부
            'remoteAreaDeliveryCharge': 0,
            'underPriceGuarantee': False,
            # 출고지/반품지 (셀러 Wing 배송정보)
            'outboundShippingPlaceCode': self.outbound_place_code,
            'returnCenterCode': self.return_center_code,
            'returnChargeName': self.return_charge_name,    # 반품지담당자명
            'companyContactNumber': self.company_contact,   # 반품지연락처
            'returnZipCode': self.return_zip,               # 반품지우편번호
            'returnAddress': self.return_addr,              # 반품지주소
            'returnAddressDetail': self.return_addr_detail or self.return_addr,
            'returnCharge': self.return_charge,             # 반품배송비
            'vendorUserId': self.vendor_user_id,            # Wing 로그인 ID
            'requested': True,                              # 자동승인 요청
            'mediumCategoryType': category_code,
            'items': [item],
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
                # 고정 IP 릴레이 경유(MARKET_RELAY_URL 설정 시) — 쿠팡 호출 IP 화이트리스트 대응(v8).
                # 미설정이면 직접 호출(폴백). 서명은 위에서 이미 끝났고 릴레이는 포워딩만.
                from src.market_relay import relay_request
                resp = relay_request(method, url, json=data, headers=headers, timeout=30,
                                     market="coupang", key=str(self.vendor_id or ""))
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
