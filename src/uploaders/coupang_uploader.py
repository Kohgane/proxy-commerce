"""Coupang 상품 업로더."""

import hashlib
import hmac
import logging
import math
import os
import time
from datetime import datetime, timezone

import requests

from src.market_relay import RelayError, relay_request

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

    # 계정별 배송 env 접두 — `_account_creds`(coupang_replicate)와 동일 규약(COUPANG_GOGANE_*/COUPANG_WOOJOO_*).
    ACCOUNT_PREFIXES = {'gogane': 'COUPANG_GOGANE', 'woojoo': 'COUPANG_WOOJOO'}

    # 고시정보 실값 배선(P3 카나리 반려 대응) — 수입자 = 계정별 상호(발명 금지·사실).
    _IMPORTER_NAMES = {'gogane': '고가네', 'woojoo': '우주대행'}
    # 카테고리 예측 + 카테고리별 고시정보 스키마 조회(동적·권위) — '기타 재화' 기본값 폐기.
    CATEGORY_PREDICT_PATH = '/v2/providers/openapi/apis/api/v1/categorization/predict'
    NOTICE_META_PATH = ('/v2/providers/seller_api/apis/api/v1/marketplace/'
                        'meta/category-related-metas/display-category-codes/{code}')

    def __init__(self, access_key: str = None, secret_key: str = None, vendor_id: str = None,
                 account: str = None, overseas_purchased: bool = None):
        """Coupang 업로더 초기화. 기본은 환경변수, **인자로 계정별 자격 오버라이드 가능**(P3 양계정 라우팅).

        access_key/secret_key/vendor_id를 넘기면 그 계정으로 등록(고가네/우주대행 라우팅). 미지정이면 무접두 env.
        **P2 계정별 배송 env(출고지/반품지):** account="gogane"|"woojoo"면 접두 `COUPANG_GOGANE_*`/
        `COUPANG_WOOJOO_*`를 우선 읽고, 없으면 무접두 `COUPANG_*`로 폴백(단, 폴백은 무접두 키가 이 계정
        소유일 때만 — `resolve_base_account` 일치 or account 미지정. 계정 간 배송정보 혼입 방지·정직).
        overseas_purchased=True면 해외구매대행 표기(pccNeeded·고시정보) — 등록 파이프(구매대행)가 명시 전달.
        """
        self.account = (account or '').strip().lower() or None
        self.access_key = access_key if access_key is not None else os.getenv('COUPANG_ACCESS_KEY', '')
        self.secret_key = secret_key if secret_key is not None else os.getenv('COUPANG_SECRET_KEY', '')
        self.vendor_id = vendor_id if vendor_id is not None else os.getenv('COUPANG_VENDOR_ID', '')
        # 셀러 고유 출고지/반품지/Wing ID (Wing > 업체정보 > 배송정보에서 확인) — 계정별 접두 우선.
        self.vendor_user_id = self._ship_env('COUPANG_VENDOR_USER_ID')
        self.return_center_code = self._ship_env('COUPANG_RETURN_CENTER_CODE')
        self.outbound_place_code = self._ship_env('COUPANG_OUTBOUND_SHIPPING_PLACE_CODE')
        self.return_zip = self._ship_env('COUPANG_RETURN_ZIP_CODE')
        self.return_addr = self._ship_env('COUPANG_RETURN_ADDRESS')
        self.return_addr_detail = self._ship_env('COUPANG_RETURN_ADDRESS_DETAIL')
        self.return_charge_name = self._ship_env('COUPANG_RETURN_CHARGE_NAME')
        self.company_contact = self._ship_env('COUPANG_COMPANY_CONTACT_NUMBER')
        try:
            self.return_charge = int(self._ship_env('COUPANG_RETURN_CHARGE', '5000') or 5000)
        except (TypeError, ValueError):
            self.return_charge = 5000
        # 해외구매대행 여부(기본: env). 인자로 명시하면 우선(등록 파이프=구매대행이라 True 전달).
        if overseas_purchased is not None:
            self.overseas_purchased = bool(overseas_purchased)
        else:
            self.overseas_purchased = str(
                os.getenv('COUPANG_OVERSEAS_PURCHASED', '0')
            ).lower() in ('1', 'true', 'yes')
        # 고시정보 실값(발명 금지) — 수입자=계정별 상호, 인증=KC 비대상 표준 문구(오너 실측 확인 후 env 조정).
        self.importer_name = (os.getenv('COUPANG_IMPORTER_NAME', '').strip()
                              or self._IMPORTER_NAMES.get(self.account, '고가네'))
        self.cert_none_text = os.getenv('COUPANG_CERT_NONE_TEXT', '').strip() or '인증 대상 아님'
        # 원산지 폴백(오너 지시: 미확인 = 등록 보류 폐기). 빈 문자열로 명시하면 폴백 끔(=보류 복귀).
        #   쿠팡이 어느 문구를 받는지는 카나리 응답이 실측 — 거부되면 응답 원문 허용 문구로 env 교체.
        _fb = os.getenv('COUPANG_ORIGIN_FALLBACK')
        self.origin_fallback = ('해외' if _fb is None else _fb.strip())
        self._notice_schema_cache = {}   # displayCategoryCode → 고시정보 스키마(메타 API, 1회 조회)
        self._predict_cache = {}         # 상품명 → 예측 categoryId
        if not self.access_key:
            logger.warning('COUPANG_ACCESS_KEY is not set')
        if not self.secret_key:
            logger.warning('COUPANG_SECRET_KEY is not set')
        if not self.vendor_id:
            logger.warning('COUPANG_VENDOR_ID is not set')

    def _ship_env(self, base_env: str, default: str = '') -> str:
        """배송 env를 계정 접두 우선으로 읽는다.

        base_env='COUPANG_RETURN_CENTER_CODE' → 계정 gogane이면 'COUPANG_GOGANE_RETURN_CENTER_CODE' 우선,
        없으면 무접두 'COUPANG_RETURN_CENTER_CODE'로 폴백(무접두가 이 계정 소유일 때만 — 혼입 방지).
        """
        prefix = self.ACCOUNT_PREFIXES.get(self.account or '')
        if prefix:
            suffix = base_env[len('COUPANG_'):]
            val = os.getenv(f'{prefix}_{suffix}', '').strip()
            if val:
                return val
            # 무접두 폴백은 무접두 자격이 이 계정 소유일 때만(다른 계정 배송정보 도용 금지).
            if not self._unprefixed_owned_by_account():
                return default
        return os.getenv(base_env, default)

    def _unprefixed_owned_by_account(self) -> bool:
        """무접두 COUPANG_* 배송/자격이 self.account 소유인가(resolve_base_account 일치)? account 미지정=허용."""
        if not self.account:
            return True
        try:
            from src.pipeline.coupang_replicate import resolve_base_account
            return resolve_base_account() == self.account
        except Exception:
            return True   # 판별 불가 시 기존 동작(폴백 허용) 유지 — 무회귀

    def _missing_shipping_config(self) -> list:
        """쿠팡 등록 필수 출고지/반품지 설정 중 누락된 환경변수명 목록.

        계정(gogane/woojoo) 지정 시 **계정 접두 키명**을 돌려준다(오너가 어느 계정 키를 넣어야 하는지 정직).
        """
        prefix = self.ACCOUNT_PREFIXES.get(self.account or '')
        missing = []
        for env, attr in self.SHIPPING_ENV_FIELDS.items():
            if str(getattr(self, attr, '') or '').strip():
                continue
            missing.append(f'{prefix}_{env[len("COUPANG_"):]}' if prefix else env)
        return missing

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
            # 카테고리 예측(실 리프 ID) → 그 코드로 고시정보 스키마 조회(동적·권위). 네트워크는 이 경로에만.
            cat = self.predict_category(product.get('title', '')) or product.get('category_id', '76001')
            product = {**product, 'category_id': cat}
            schema = self.get_category_notice_schema(cat) or None
            # 고시정보 실값 미확인(원산지 등) → 등록 보류(추정 금지·가짜 성공 0).
            _, hold = self._build_notices(product, schema)
            if hold:
                return {'success': False, 'error': hold, 'sku': product.get('sku', ''), 'held': True}
            payload = self._build_product_payload(product, notice_schema=schema)
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
            'origin': collected.get('origin') or collected.get('brand_country', ''),   # 제조국(고시정보 실값)
            'weight_kg': collected.get('weight_kg'),
            'stock': 999,
            'options': collected.get('options', {}),
            'tags': collected.get('tags', []),
            'shipping_fee': 0,
            'delivery_days': '7-14',
            'return_info': '해외직구 상품으로 반품/교환이 불가합니다',
        }

    # ------------------------------------------------------------------
    # 반려감시 (P4) — 상태이력 조회 · 재승인 요청
    # ------------------------------------------------------------------

    def get_status_histories(self, seller_product_id: str) -> dict:
        """상품 상태변경 이력 조회 — 반려 사유(comment)는 여기에만 있다([[반려 사유 요약 오독 지뢰]]).

        반환: 쿠팡 응답 dict(그대로) 또는 {'error': ...}. reject_watch.latest_rejection_comment가 파싱.
        """
        try:
            path = (f'/v2/providers/seller_api/apis/api/v1/marketplace/'
                    f'seller-products/{seller_product_id}/histories')
            return self._api_request('GET', path)
        except Exception as exc:
            logger.error('get_status_histories failed for sid=%s: %s', seller_product_id, exc)
            return {'error': str(exc)}

    def request_approval(self, seller_product_id: str) -> dict:
        """SAVED(반려/임시저장) 상품 재승인 요청 — `PUT .../seller-products/{sid}/approvals` 한 방.

        오너 승인 게이트 뒤에서만 호출(비가역). 성공/실패 정직 반환(가짜 성공 0).
        """
        try:
            path = (f'/v2/providers/seller_api/apis/api/v1/marketplace/'
                    f'seller-products/{seller_product_id}/approvals')
            result = self._api_request('PUT', path)
            if 'error' in result:
                return {'success': False, 'error': result['error'], 'sku': seller_product_id}
            return {'success': True, 'product_id': seller_product_id}
        except Exception as exc:
            logger.error('request_approval failed for sid=%s: %s', seller_product_id, exc)
            return {'success': False, 'error': str(exc), 'sku': seller_product_id}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    # 쿠팡 '기타 재화' 상품고시정보 표준 항목 — **최후 폴백**(메타 API 조회 실패 시). 기본값 아님.
    _NOTICE_CATEGORY = '기타 재화'
    _NOTICE_DETAILS = [
        '품명 및 모델명',
        '법에 의한 인증·허가 등을 받았음을 확인할 수 있는 경우 그에 대한 사항',
        '제조국 또는 원산지',
        '제조자/수입자',
        'A/S 책임자와 전화번호 또는 소비자상담 관련 전화번호',
    ]

    def predict_category(self, product_name: str) -> str:
        """쿠팡 카테고리 예측 API로 상품명 → **실 카테고리ID**(리프). 실패/미지원 시 '' (폴백 CATEGORY_MAP)."""
        name = str(product_name or '').strip()
        if not name:
            return ''
        if name in self._predict_cache:
            return self._predict_cache[name]
        cid = ''
        try:
            res = self._api_request('POST', self.CATEGORY_PREDICT_PATH, data={'productName': name})
            data = res.get('data') if isinstance(res, dict) else None
            if isinstance(data, dict):
                cid = str(data.get('predictedCategoryId') or data.get('categoryId') or '')
        except Exception as exc:
            logger.warning('카테고리 예측 실패(폴백 사용): %s', exc)
        self._predict_cache[name] = cid
        return cid

    def get_category_notice_schema(self, display_category_code: str) -> list:
        """카테고리 메타 API로 **이 카테고리의 필수 고시정보 스키마**(동적·권위). '기타 재화' 기본값 폐기.

        반환: [{'noticeCategoryName', 'details':[detailName,...]}] · 조회 실패/미지원 시 [](폴백 신호).
        """
        code = str(display_category_code or '').strip()
        if not code:
            return []
        if code in self._notice_schema_cache:
            return self._notice_schema_cache[code]
        out = []
        try:
            res = self._api_request('GET', self.NOTICE_META_PATH.format(code=code))
            data = res.get('data') if isinstance(res, dict) else None
            for nc in ((data or {}).get('noticeCategories') or []):
                names = [d.get('noticeCategoryDetailName')
                         for d in (nc.get('noticeCategoryDetailNames') or [])
                         if d.get('noticeCategoryDetailName')]
                if nc.get('noticeCategoryName') and names:
                    out.append({'noticeCategoryName': nc['noticeCategoryName'], 'details': names})
        except Exception as exc:
            logger.warning('고시정보 스키마 조회 실패(폴백 기타재화): %s', exc)
        self._notice_schema_cache[code] = out
        return out

    def _notice_value_for(self, detail: str, product: dict):
        """고시정보 상세명 → **실값**(발명 금지·사실만). 원산지 미확인이면 None(등록 보류 신호).

        제조자=수집 브랜드 · 수입자=계정 상호 · 원산지=수집값(없으면 None·추정 금지) ·
        A/S·전화=COMPANY_CONTACT_NUMBER env · 인증=KC 비대상 표준 문구 · 품명=상품명.
        """
        d = str(detail or '')
        brand = str(product.get('brand') or '').strip()
        origin = str(product.get('origin') or product.get('brand_country') or '').strip()
        phone = str(self.company_contact or '').strip()
        if '품명' in d or '모델' in d:
            return product.get('title') or '상세페이지 참조'
        if '인증' in d or '허가' in d:
            return self.cert_none_text                       # KC 비대상 표준 문구(오너 실측 확인)
        if '원산지' in d or '제조국' in d:
            # 실측 원산지 우선. 미확인이면 **폴백 문구로 등록 시도**(오너 지시: 보류 폐기).
            #   폴백을 빈 문자열로 껐을 때만 None(=보류) — 특정 국가 추정은 여전히 금지.
            return origin or self.origin_fallback or None
        if '수입자' in d and ('제조자' in d or '제조사' in d):
            return f'{brand or "상세페이지 참조"} / {self.importer_name}'   # 결합 필드
        if '수입자' in d:
            return self.importer_name
        if '제조자' in d or '제조사' in d:
            return brand or '상세페이지 참조'
        if 'A/S' in d or 'AS' in d.upper() or '전화' in d or '상담' in d or '연락' in d:
            return phone or '상세페이지 참조'
        return '상세페이지 참조'

    def _build_notices(self, product: dict, schema=None):
        """옵션 상품고시정보(notices) + **등록 보류 사유**. 반환: (notices:list, hold_reason:str|None).

        P3 카나리 반려 수리: '기타 재화' 기본값 폐기 → **메타 API 고시정보 스키마**로 유형 동적 결정(발명 금지).
        상세명마다 실값(제조자/수입자/원산지/AS/인증). **원산지 미확인이면 등록 보류**(추정 금지).
        schema는 `upload_product`가 메타 API로 조회해 주입(네트워크는 그 경로에만). 미주입 시 '기타 재화' 폴백.
        """
        if not schema:                                       # 폴백: 기타 재화 표준(스키마 미주입/메타 미가용)
            schema = [{'noticeCategoryName': self._NOTICE_CATEGORY, 'details': list(self._NOTICE_DETAILS)}]
        nc = schema[0]                                       # 첫 필수 고시 카테고리
        notices, missing = [], []
        for detail in nc['details']:
            val = self._notice_value_for(detail, product)
            if val is None:                                  # 원산지 등 미확인 필수값 → 보류
                missing.append(detail)
                val = ''                                     # 전송 안 됨(보류로 차단)
            notices.append({'noticeCategoryName': nc['noticeCategoryName'],
                            'noticeCategoryDetailName': detail, 'content': val})
        hold = (f'고시정보 실값 미확인({", ".join(missing)}) — 등록 보류(추정 금지, 원산지 등 확인 필요)'
                if missing else None)
        return notices, hold

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

    def _build_product_payload(self, product: dict, notice_schema=None) -> dict:
        """Coupang Wing API용 상품 페이로드를 구성한다.

        쿠팡 createProduct 필수 필드를 모두 채운다(null/누락 시 등록 거부).
        - 옵션(items[])별: 과세/성인/단위수량/최대구매수량기간/해외구매대행/이미지/고시정보/컨텐츠
        - 상품(root): 묶음배송/도서산간/반품지(주소·우편번호·담당자·연락처·배송비)/출고지/vendorUserId
        """
        title = product.get('title', '') or '상품'
        category_code = product.get('category_id', '76001')   # 예측은 upload_product에서 이미 해결(네트워크 격리)
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
            'notices': self._build_notices(product, notice_schema)[0],  # 상품고시정보(실값). 보류판정=upload_product.
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
                # 고정 IP 릴레이 경유 — 쿠팡 호출 IP 화이트리스트 대응(v8 / v87-S6-2 mkt.php).
                # 미설정이면 직접 호출(폴백). 서명은 위에서 이미 끝났고 릴레이는 포워딩만.
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
            except RelayError as exc:
                # v87-S6-2: 릴레이 계층 실패는 재시도해도 같다(설정·릴레이 다운) → 즉시 정직 반환.
                #   '쿠팡이 거부함'과 '우리 릴레이가 죽음'을 마켓 카드에서 구분하기 위함.
                logger.error('Coupang relay failed: %s', exc)
                return {'error': str(exc)}
            except requests.exceptions.RequestException as exc:
                logger.warning('Coupang API request failed (attempt %d): %s', attempt + 1, exc)
                if attempt < 2:
                    time.sleep(3)
        return {'error': 'API request failed after retries'}
