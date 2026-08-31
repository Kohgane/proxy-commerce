"""Coupang 상품 업로더."""

import hashlib
import hmac
import json
import logging
import math
import os
import re
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
    # 택배사 코드 정본 — 쿠팡 메타 API가 유효 코드 목록을 준다(**새 값 발명 금지**·카나리 6차 거부 대응).
    DELIVERY_COMPANIES_PATH = ('/v2/providers/openapi/apis/api/v1/marketplace/'
                               'meta/coupang-delivery-companies')
    # ★ 배송 페이로드 **정본**(오너 SSH grep 실측 — coupang_upload.py:125, 5,691건 등록 검증값).
    #   구매대행이므로 AGENT_BUY. SEQUENCIAL(구 기본값)은 구매대행에 부적합해 폐기(오너 지시).
    DEFAULT_DELIVERY_METHOD = 'AGENT_BUY'
    DEFAULT_DELIVERY_COMPANY_CODE = 'CJGLS'

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
        # 택배사·배송 방식 — **정본 = 오너 SSH grep 실측**(coupang_upload.py:125, 5,691건 등록에 쓰인 값).
        #   deliveryMethod=AGENT_BUY(구매대행) · deliveryCompanyCode=CJGLS. 기본값이 곧 검증값이라
        #   env 미설정이어도 정본으로 등록된다. 계정별로 다르면 접두 env로 덮어쓴다(하드코딩 아님·오버라이드 가능).
        #   ※ SEQUENCIAL(예전 기본값)은 **구매대행에 부적합** — 오너 지시로 폐기.
        self.delivery_company_code = self._ship_env('COUPANG_DELIVERY_COMPANY_CODE')
        # 명시적으로 빈 값을 준 경우 = 폴백 끔(정본 기본값도 안 씀 → 등록 전 정직 보류).
        self._delivery_code_disabled = (
            self._raw_env_present('COUPANG_DELIVERY_COMPANY_CODE') and not self.delivery_company_code)
        self.delivery_company_name = self._ship_env('COUPANG_DELIVERY_COMPANY_NAME')   # 예: 우체국
        self.delivery_method = self._ship_env('COUPANG_DELIVERY_METHOD',
                                              self.DEFAULT_DELIVERY_METHOD)
        self.delivery_charge_type = self._ship_env('COUPANG_DELIVERY_CHARGE_TYPE', 'FREE')
        # 이미지 규격 실측 게이트(반려 1호). 등록당 이미지 수만큼 HTTP 헤더 조회가 붙으므로
        #   env로 끌 수 있게 둔다(기본 ON — 규격 미달 전송이 더 비싸다).
        self.image_screen_enabled = os.getenv('COUPANG_IMAGE_SCREEN', '1').strip().lower() not in (
            '0', 'false', 'no', 'off')
        self._delivery_companies_cache = None
        self._meta_cache = {}            # displayCategoryCode → 카테고리 메타 원문(고시정보+속성 단일 소스)
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

    @staticmethod
    def _as_int(v):
        """정본 규약상 int로 보내야 하는 값(출고지코드 등). 숫자가 아니면 원본 유지(정직)."""
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return v

    def _raw_env_present(self, base_env: str) -> bool:
        """해당 배송 env가 (접두/무접두 중 하나라도) **정의되어 있는가**. 빈 문자열도 '정의됨'으로 본다."""
        prefix = self.ACCOUNT_PREFIXES.get(self.account or '')
        if prefix and (f'{prefix}_' + base_env[len('COUPANG_'):]) in os.environ:
            return True
        return base_env in os.environ

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

    # 전송 블록 계측 — 저장처는 **기존 로그 관례**(logger). 등록 대장(market_registrations)
    #   스키마는 건드리지 않는다(오너 지시 C2 — 스키마는 별도 결정 사안).
    ATTR_LOG_LIMIT = 1200

    @classmethod
    def _log_attr_block(cls, sku: str, payload: dict, *, outcome: str, detail: str = '') -> str:
        """전송한 attributes·옵션(items) 블록 원문을 로그에 남기고 그 줄을 반환한다.

        카나리 실패 부검이 막힌 근원: **보낸 페이로드가 어디에도 남지 않았다**(대장에 payload 컬럼
        없음·성공 시에만 record). 실패는 물론 성공도 남겨야 "통과한 모양"과 대조가 된다.
        비밀은 담기지 않는다 — attributes/옵션은 상품 값이고 인증 헤더는 여기 없다.
        """
        try:
            items = payload.get('items') or []
            block = [{'itemName': (it or {}).get('itemName', ''),
                      'attributes': (it or {}).get('attributes') or []} for it in items]
            body = json.dumps(block, ensure_ascii=False)[:cls.ATTR_LOG_LIMIT]
        except Exception as exc:                       # 계측이 등록을 죽이지 않게
            body = f'<직렬화 실패: {type(exc).__name__}>'
        line = (f'쿠팡 전송블록 outcome={outcome} sku={sku or "-"} items={len(payload.get("items") or [])} '
                f'attributes={body}' + (f' detail={detail}' if detail else ''))
        (logger.warning if outcome == 'fail' else logger.info)('%s', line)
        return line

    @classmethod
    def _ledger_fail(cls, sku: str, reason: str, *, held: bool = False) -> str:
        """P4 — **실패 건 누적 대장**(기존 로그 관례. 대장 스키마는 건드리지 않는다).

        `market_registrations`는 성공만 적는다 — 그 구조가 "같은 상품 3회 클릭, 실패 3회가
        어디에도 없다"를 만들었다. 성공 대장은 그대로 두고, 실패는 여기서 **1줄씩 누적**한다:
        클릭 3회면 줄 3개(집계가 1로 뭉개지지 않는다). payload 컬럼 결정은 계속 보류.
        """
        at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        line = (f'쿠팡 등록실패대장 at={at} sku={sku or "-"} '
                f'kind={"held" if held else "rejected"} reason={str(reason or "")[:300]}')
        logger.warning('%s', line)
        return line

    def upload_product(self, product: dict) -> dict:
        """Coupang 등록 — **단일 관문**. 실패는 어느 경로로 나가든 여기서 대장에 누적된다.

        반환 계약은 그대로다(`_upload_product_inner`가 실제 로직). 실패 return이 10곳이라
        각 자리에 로그를 흩뿌리면 한 곳을 빠뜨린다 — 관문 하나로 묶는다(v86-L echo 봉인과 동형).
        """
        out = self._upload_product_inner(product)
        if isinstance(out, dict) and not out.get('success'):
            self._ledger_fail(out.get('sku') or product.get('sku', ''),
                              out.get('error', ''), held=bool(out.get('held')))
        return out

    def _upload_product_inner(self, product: dict) -> dict:
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
                    # 전송 전 차단이므로 **보류**다 — 다른 사전 게이트(고시정보·옵션·카테고리)는 전부
                    #   held를 달고 나가는데 여기만 빠져 있었다(대장 누적에서 rejected로 오분류).
                    'held': True,
                    'error': (
                        '쿠팡 출고지/반품지 정보 미설정으로 등록 불가. '
                        '다음 환경변수를 Wing 배송정보 값으로 설정하세요: '
                        + ', '.join(missing)
                    ),
                    'sku': product.get('sku', ''),
                }
            # 택배사 코드 미확정 → 등록 전 정직 실패(카나리 6차 거부 재발 방지). 유효 코드는 쿠팡 목록이 정본.
            if not self.resolve_delivery_company_code():
                pfx = self.ACCOUNT_PREFIXES.get(self.account or '') or 'COUPANG'
                return {
                    'success': False, 'held': True, 'sku': product.get('sku', ''),
                    'error': (
                        '쿠팡 택배사 코드 미설정으로 등록 불가(유효하지 않은 코드 전송 금지). '
                        f'{pfx}_DELIVERY_COMPANY_CODE 를 설정하거나 {pfx}_DELIVERY_COMPANY_NAME(예: 우체국)을 '
                        '설정하세요. 유효 코드 목록은 GET /admin/coupang-delivery-companies 로 확인.'
                    ),
                }
            # SKU 유효성(카나리 8차 근원) — itemName/externalVendorSku로 그대로 나가는 값이다.
            #   URL 파편('…&ref_=pd_hp_…')이 들어오면 쿠팡이 옵션명으로 거부한다. 쓰레기 값 전송 금지.
            from src.collectors.product_key import is_valid_vendor_sku
            sku = str(product.get('sku', '') or '').strip()
            if not is_valid_vendor_sku(sku):
                return {'success': False, 'held': True, 'sku': sku,
                        'error': ('SKU 추출 실패 — 등록 중단(쓰레기 SKU 전송 금지). '
                                  f'상품 URL에서 식별자(아마존 ASIN 등)를 뽑지 못했습니다: {sku!r}')}
            # 이미지 규격 게이트(반려 1호) — 대형본 치환 후 **실치수** 심사. 미달 이미지는 제외하고,
            #   대표이미지가 전멸하면 등록 중단(규격 미달 이미지로 카나리 태우지 않는다·동형 게이트 3번째).
            #   측정 불가는 제외하지 않는다 — '확인 실패'를 '미달'로 단정하지 않는다(정직).
            if self.image_screen_enabled:
                from src.collectors.image_norm import screen_images
                shot = screen_images(product.get('images') or [])
                if not shot['ok']:
                    return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                            'error': f"이미지 규격 미달 — 등록 중단: {shot['reason']}",
                            'images_dropped': shot['dropped']}
                if shot['dropped']:
                    logger.info('이미지 규격 미달 %d장 제외(sku=%s): %s', len(shot['dropped']),
                                product.get('sku', ''), shot['dropped'][:3])
                product = {**product, 'images': shot['images']}
            # 판매가 하한(쿠팡: 옵션 10원 이상) — POST 전 차단으로 왕복 절약(카나리 7차 거부 재발 방지).
            price = self._as_int(product.get('price', 0)) or 0
            if price < 10:
                return {'success': False, 'held': True, 'sku': sku,
                        'error': (f'판매가 미확정({price}원) — 등록 중단. 쿠팡은 옵션 판매가 10원 이상을 '
                                  '요구합니다. 검수표 판매가가 페이로드까지 전달됐는지 확인하세요.')}
            # 카테고리 예측(실 리프 ID) → 그 코드로 고시정보 스키마 조회(동적·권위). 네트워크는 이 경로에만.
            #   **정본: 예측 실패 시 등록 중단**(임의 카테고리로 보내면 거부/오분류 — 추측 전송 금지).
            cat = self.predict_category(product.get('title', '')) or str(product.get('category_id', '') or '')
            if not cat:
                return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                        'error': '쿠팡 카테고리 예측 실패 — 등록 중단(임의 카테고리 전송 금지). 상품명 확인 필요.'}
            product = {**product, 'category_id': cat}
            schema = self.get_category_notice_schema(cat) or None
            # 고시정보 실값 미확인(원산지 등) → 등록 보류(추정 금지·가짜 성공 0).
            _, hold = self._build_notices(product, schema)
            if hold:
                return {'success': False, 'error': hold, 'sku': product.get('sku', ''), 'held': True}
            # 필수 구매 옵션(attributes) — 메타 스키마로 채우고, 못 채운 필수 속성이 있으면 등록 중단.
            #   카나리 9차 거부("필수 구매 옵션 … 존재하지 않습니다") 재발 방지.
            attr_schema = self.get_category_attribute_schema(cat)
            attributes = self.build_attrs(product, attr_schema)
            unmet = self.missing_required_attrs(attributes, attr_schema)
            if unmet:
                return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                        'error': ('필수 구매 옵션 미충족으로 등록 중단(빈 값 전송 금지): '
                                  + ', '.join(unmet))}
            payload = self._build_product_payload(product, notice_schema=schema,
                                                  attr_schema=attr_schema, attributes=attributes)
            path = '/v2/providers/seller_api/apis/api/v1/marketplace/seller-products'
            result = self._api_request('POST', path, data=payload)
            if 'error' in result:
                # 실패 = 무조건 전송 블록 원문을 남긴다(다음 세션이 로그 고고학을 반복하지 않게).
                self._log_attr_block(product.get('sku', ''), payload,
                                     outcome='fail', detail=str(result['error']))
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
                self._log_attr_block(product.get('sku', ''), payload, outcome='fail',
                                     detail=f'code={code} message={msg}')
                return {'success': False, 'error': f'쿠팡 등록 거부: {msg}', 'sku': product.get('sku', '')}
            # 성공분도 남긴다 — 다음 실패의 **대조 정본**(통과한 attributes가 어떤 모양이었나).
            self._log_attr_block(product.get('sku', ''), payload, outcome='ok',
                                 detail=f'sellerProductId={product_id}')
            # ★ 정본 2단계: 등록(POST) 성공 후 **승인요청(PUT approvals)** 별도 호출.
            #   누락하면 상품이 SAVED로 방치된다(심사 진입 안 함). 호출 간 0.4s(레이트리밋).
            approval = None
            if product_id:
                time.sleep(0.4)
                approval = self.request_approval(product_id)
                if not approval.get('success'):
                    logger.warning('승인요청 실패(등록은 됨) sid=%s: %s', product_id, approval.get('error'))
            url = f'https://www.coupang.com/vp/products/{product_id}' if product_id else ''
            return {'success': True, 'product_id': product_id, 'url': url, 'sku': product.get('sku', ''),
                    'approval_requested': bool(approval and approval.get('success')),
                    'approval_error': (None if (approval or {}).get('success') else (approval or {}).get('error'))}
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

    def rebuild_images_for_resubmit(self, images) -> dict:
        """반려분 **이미지 교체 페이로드**. 대형본 치환 + 실치수 심사 후 items[].images 형태로.

        반환 {ok, images(전송용), dropped, unknown, reason}. ok=False면 교체할 이미지가 없다는 뜻이라
        호출부가 재제출을 중단해야 한다(미달 이미지로 재반려되는 왕복 금지).
        """
        from src.collectors.image_norm import screen_images
        shot = screen_images(images or [])
        if not shot['ok']:
            return {'ok': False, 'images': [], 'dropped': shot['dropped'],
                    'unknown': shot['unknown'], 'reason': shot['reason']}
        return {'ok': True, 'images': self._build_images({'images': shot['images']}),
                'dropped': shot['dropped'], 'unknown': shot['unknown'], 'reason': ''}

    def resubmit_product(self, seller_product_id: str, updates: dict = None) -> dict:
        """반려분 **재승인 제출** — 수정이 필요하면 PUT 수정 후, 아니면 승인요청만.

        쿠팡 반려 상품은 SAVED로 내려온다. 사유가 값 문제면 **수정(PUT seller-products) → 승인요청
        (PUT approvals)** 2단계, 사유 없이 재심사만 필요하면 승인요청 1단계.
        비가역이므로 **오너 승인 게이트 뒤에서만** 호출한다. 어느 단계에서 멈췄는지까지 정직 표기.
        """
        sid = str(seller_product_id or '').strip()
        if not sid:
            return {'success': False, 'error': '상품 id 없음'}
        updated = False
        if updates:
            up = self.update_product(sid, updates)
            if not up.get('success'):
                # 수정 실패 상태로 승인요청하면 같은 사유로 또 반려된다 → 여기서 멈춘다.
                return {'success': False, 'product_id': sid, 'stage': 'update',
                        'error': f"상품 수정 실패 — 승인요청 안 함: {up.get('error')}"}
            updated = True
            time.sleep(0.4)                       # 레이트리밋(정본 승계 — 등록 2단계와 동일)
        appr = self.request_approval(sid)
        if not appr.get('success'):
            return {'success': False, 'product_id': sid, 'stage': 'approval',
                    'updated': updated, 'error': appr.get('error')}
        return {'success': True, 'product_id': sid, 'stage': 'approval', 'updated': updated}

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

    def get_delivery_companies(self) -> list:
        """쿠팡 택배사 코드 **정본 목록** 조회(메타 API). 실패/미지원 시 [](폴백 신호).

        반환: [{"code","name"}]. 카나리 6차 거부("유효하지 않은 택배사 코드") 대응 — 코드를 지어내지 않고
        쿠팡이 주는 목록에서 고른다. `/admin/coupang-delivery-companies`로 오너가 직접 조회 가능.
        """
        if self._delivery_companies_cache is not None:
            return self._delivery_companies_cache
        out = []
        try:
            res = self._api_request('GET', self.DELIVERY_COMPANIES_PATH)
            data = res.get('data') if isinstance(res, dict) else None
            rows = data if isinstance(data, list) else ((data or {}).get('deliveryCompanies') or [])
            for r in rows:
                if not isinstance(r, dict):
                    continue
                code = str(r.get('deliveryCompanyCode') or r.get('code') or '').strip()
                name = str(r.get('deliveryCompanyName') or r.get('name') or '').strip()
                if code:
                    out.append({'code': code, 'name': name})
        except Exception as exc:
            logger.warning('택배사 코드 목록 조회 실패: %s', exc)
        self._delivery_companies_cache = out
        return out

    def resolve_delivery_company_code(self) -> str:
        """전송할 택배사 코드 확정. ① 명시 env 코드 → ② env 이름 힌트로 쿠팡 목록 매칭 → ③ **정본 기본값**.

        ③ = DEFAULT_DELIVERY_COMPANY_CODE(오너 SSH grep 실측 CJGLS·5,691건 등록 검증값).
        env를 **명시적으로 빈 값**으로 두면 ''를 돌려주고 호출부가 등록 전 정직 보류시킨다.
        """
        if self.delivery_company_code:                     # ① 명시 env 코드(최우선)
            return self.delivery_company_code
        hint = (self.delivery_company_name or '').strip()
        if hint:                                           # ② 이름 힌트 → 쿠팡 목록 매칭(발명 0)
            for row in self.get_delivery_companies():
                name = row.get('name') or ''
                if hint == name or hint in name:
                    self.delivery_company_code = row['code']    # 1회 확정 후 캐시
                    return row['code']
        if self._delivery_code_disabled:                   # 명시적으로 비움 → 보류(정직)
            return ''
        return self.DEFAULT_DELIVERY_COMPANY_CODE          # ③ 정본 기본값(오너 SSH 실측·5,691건 검증)

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

    def get_category_meta(self, display_category_code: str) -> dict:
        """카테고리 메타 API 응답 `data` 원문(고시정보·속성 스키마의 **단일 소스**). 실패 시 {}.

        같은 응답에 `noticeCategories`(고시정보)와 `attributes`(구매 옵션 스키마)가 함께 온다 —
        카테고리당 1회만 호출해 둘 다 여기서 파생한다(왕복 절약·스키마 불일치 0).
        """
        code = str(display_category_code or '').strip()
        if not code:
            return {}
        if code in self._meta_cache:
            return self._meta_cache[code]
        data = {}
        try:
            res = self._api_request('GET', self.NOTICE_META_PATH.format(code=code))
            d = res.get('data') if isinstance(res, dict) else None
            if isinstance(d, dict):
                data = d
        except Exception as exc:
            logger.warning('카테고리 메타 조회 실패(폴백): %s', exc)
        self._meta_cache[code] = data
        return data

    def get_category_attribute_schema(self, display_category_code: str) -> list:
        """이 카테고리의 **구매 옵션(attributes) 스키마**. 카나리 9차 거부('필수 구매 옵션 없음') 대응.

        반환: [{'attributeTypeName', 'required'(bool), 'exposed', 'dataType'}] · 조회 실패 시 [].
        `required`는 쿠팡 표기(MANDATORY/필수/true) 정규화. 발명 0 — 응답에 있는 것만.
        """
        raw = self.get_category_meta(display_category_code).get('attributes') or []
        # P1 — 메타 attributes[] **원문**을 남긴다(전송블록 계측과 동형).
        #   여태 이 응답은 코드 안에서만 소비되고 흔적이 0이었다 → 다음 카나리에서 메타를 확보한다.
        self._log_meta_attributes(display_category_code, raw)
        out = []
        for a in raw:
            if not isinstance(a, dict):
                continue
            name = str(a.get('attributeTypeName') or '').strip()
            if not name:
                continue
            req = str(a.get('required') or '').strip().upper()
            out.append({
                'attributeTypeName': name,
                'required': req in ('MANDATORY', 'REQUIRED', 'TRUE', 'Y', '필수'),
                'exposed': str(a.get('exposed') or '').strip() or 'EXPOSED',
                'dataType': str(a.get('dataType') or '').strip(),
                # ★ P1 — 여태 **버리던** 세 필드. 단위·허용값 판정의 유일한 근거다.
                #   (이걸 버려서 "단위가 붙을 경로 자체가 없다"가 됐다 — 카나리 실패 부검 결론.)
                'basicUnit': str(a.get('basicUnit') or '').strip(),
                'inputType': str(a.get('inputType') or '').strip(),
                'usableUnits': [str(u).strip() for u in (a.get('usableUnits') or [])
                                if str(u or '').strip()],
            })
        return out

    META_LOG_LIMIT = 2000

    @classmethod
    def _log_meta_attributes(cls, code: str, raw) -> str:
        """카테고리 메타 attributes[] 원문 1줄. 비밀 없음(카테고리 규격 = 공개 스키마)."""
        try:
            body = json.dumps(raw, ensure_ascii=False)[:cls.META_LOG_LIMIT]
        except Exception as exc:
            body = f'<직렬화 실패: {type(exc).__name__}>'
        line = f'쿠팡 카테고리 메타 code={code or "-"} attributes={body}'
        logger.info('%s', line)
        return line

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
        for nc in (self.get_category_meta(code).get('noticeCategories') or []):
            names = [d.get('noticeCategoryDetailName')
                     for d in (nc.get('noticeCategoryDetailNames') or [])
                     if d.get('noticeCategoryDetailName')]
            if nc.get('noticeCategoryName') and names:
                out.append({'noticeCategoryName': nc['noticeCategoryName'], 'details': names})
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
        # 정본: contentsType/detailType 모두 TEXT 고정(5,691건 검증 형태).
        return [{
            'contentsType': 'TEXT',
            'contentDetails': [{'content': body, 'detailType': 'TEXT'}],
        }]

    # ── attributes(필수 구매 옵션) 정본 — 오너 SSH 실측 `build_opt.py::attr_safe`(5,691건 통과) ──────
    #   카나리 9차 거부: "필수 구매 옵션 (미입력시 등록/노출 제한) 존재하지 않습니다."
    #   처방은 **삭제가 아니라 실값 대체**(반려 처리 표준). 아래 규칙은 실증값이라 그대로 승계한다.
    ATTR_BAD_VALUES = frozenset({'', '없음', '-', 'None', 'null',
                                 '상세설명 참조', '상세페이지 참조', '상세참조'})
    _ATTR_COLOR_RE = re.compile(
        r'(Black|White|Blue|Red|Green|Gold|Silver|Brown|Navy|Gray|Grey|Pink|Ivory|Beige|Clear)', re.I)
    _ATTR_SHOE_RE = re.compile(r'\b(2[2-9]0|3[0-1]0)\b')
    _ATTR_NIB_RE = re.compile(r'\b(EF|MF|F|M|B|BB)\b')
    ATTR_VALUE_MAX = 28                                  # 정본: str(av)[:28]
    ATTR_FALLBACK = ({'attributeTypeName': '수량', 'attributeValueName': '1'},)

    @classmethod
    def _attr_value_from_name(cls, type_name: str, product_name: str) -> str:
        """속성명 + 상품명 → 실값. 상품명에서 못 뽑으면 속성별 기본값(정본 표 그대로)."""
        an, name = str(type_name or ''), str(product_name or '')
        if '색상' in an:
            m = cls._ATTR_COLOR_RE.search(name)
            return m.group(1) if m else '블랙'
        if '신발사이즈' in an:                            # ※ FREE/프리는 쿠팡이 거부 — 숫자만
            m = cls._ATTR_SHOE_RE.search(name)
            return m.group(1) if m else '260'
        if '펜촉' in an or '닙' in an or '굵기' in an:
            m = cls._ATTR_NIB_RE.search(name)
            return m.group(1) if m else 'M'
        if '수량' in an or '개수' in an:
            return '1'
        if '중량' in an or '무게' in an:
            return '100'
        if '세트' in an:
            return '단품'
        if '구성품' in an:
            return '본품'
        if '사이즈' in an or '크기' in an:
            return 'FREE'
        return '기타'

    # 수치형 판정 — 값이 **순수 숫자**면 수치로 본다(쿠팡 메타의 타입 표기가 카테고리마다 달라
    #   선언 타입만 믿지 않는다). 결합 여부의 최종 근거는 메타의 basicUnit 존재다.
    _PURE_NUMBER_RE = re.compile(r'^\d+(?:\.\d+)?$')
    _NUM_UNIT_RE = re.compile(r'^\d+(?:\.\d+)?\s*(.*)$')

    @classmethod
    def _schema_index(cls, attr_schema) -> dict:
        """attributeTypeName 기준 스키마 색인 — 단위·허용값 판정의 단일 소스."""
        out = {}
        for e in (attr_schema or []):
            if isinstance(e, dict):
                an = str(e.get('attributeTypeName') or '').strip()
                if an:
                    out[an] = e
        return out

    @classmethod
    def _combine_unit(cls, value: str, entry: dict) -> str:
        """P2 — 수치형 값에 **메타의 basicUnit**을 결합한다('1' -> '1개').

        단위 문자열은 **전부 메타 유래**(하드코딩 0). 메타에 단위가 없으면 결합하지 않는다(발명 0).
        이미 단위가 붙어 있으면(순수 숫자가 아니면) 손대지 않는다 — 이중 결합 방지.
        """
        v = str(value or '').strip()
        unit = str((entry or {}).get('basicUnit') or '').strip()
        if not v or not unit or not cls._PURE_NUMBER_RE.match(v):
            return v
        return f'{v}{unit}'

    @classmethod
    def _unit_allowed(cls, value: str, entry: dict):
        """P3 — 메타가 **허용 단위 목록**(usableUnits)을 주면 그 밖의 값은 차단한다.

        반환 (ok, reason). 목록을 안 주면 통과 — 우리가 목록을 만들지 않는다(발명 0).
        값에서 숫자를 떼어낸 뒤쪽을 단위로 본다: '1개' -> '개', '45' -> ''(단위 없음).
        ※ 값 자체의 enum(색상 등)이 메타 응답에 **어떤 키로 오는지 아직 미확인**이라 판정하지 않는다.
          P1이 남기는 메타 원문 로그에서 그 키가 확인되면 여기에 같은 방식으로 추가한다(추측 금지).
        """
        units = [u for u in ((entry or {}).get('usableUnits') or []) if u]
        if not units:
            return True, ''
        v = str(value or '').strip()
        m = cls._NUM_UNIT_RE.match(v)
        tail = (m.group(1).strip() if m else v)
        if not tail:
            return False, '단위 없음(허용 ' + '/'.join(units) + ')'
        if tail in units:
            return True, ''
        return False, f'허용 밖 단위 {tail!r}(허용 ' + '/'.join(units) + ')'

    @classmethod
    def attr_safe(cls, attrs, name: str = '', attr_schema=None) -> list:
        """구매 옵션 속성 정제 — **정본 승계**(발명 0).

        규칙: gtin 속성 스킵 · BAD 값(및 신발사이즈의 FREE/프리)은 상품명에서 실값 추출 후 기본값 ·
        값 28자 절단 · `exposed` 보존 · 같은 attributeTypeName은 **먼저 온 것만** ·
        결과가 비면 **`[{수량: 1}]` 반환**(빈 배열 전송 금지 — 9차 거부의 직접 처방).
        """
        out, seen, blocked = [], set(), []
        idx = cls._schema_index(attr_schema)
        for a in (attrs or []):
            if not isinstance(a, dict):
                continue
            an = str(a.get('attributeTypeName') or '').strip()
            if not an or 'gtin' in an.lower():            # gtin = 바코드 계열 → 전송 안 함(정본)
                continue
            if an in seen:                                # 중복 차원은 먼저 온 것만(정본)
                continue
            av = a.get('attributeValueName')
            av = '' if av is None else str(av).strip()
            bad = av in cls.ATTR_BAD_VALUES
            if not bad and '신발사이즈' in an and av.upper() in ('FREE', '프리'):
                bad = True                                # 신발사이즈 FREE = 쿠팡 거부(실증)
            if bad:
                av = cls._attr_value_from_name(an, name)
            entry = idx.get(an) or {}
            av = cls._combine_unit(av, entry)             # P2 — 메타 basicUnit 결합
            ok, why = cls._unit_allowed(av, entry)        # P3 — 메타 허용 단위 밖이면 차단
            if not ok:
                # 조용히 버리지 않는다 — 무엇을 왜 뺐는지 남긴다(다음 거부의 대조 근거).
                logger.debug('쿠팡 옵션 차단 attr=%s value=%r 사유=%s', an, av, why)
                blocked.append(f'{an}={av}({why})')
                continue
            item = {'attributeTypeName': an, 'attributeValueName': str(av)[:cls.ATTR_VALUE_MAX]}
            if a.get('exposed'):
                item['exposed'] = a['exposed']            # 원본 exposed 보존(정본)
            out.append(item)
            seen.add(an)
        if blocked:
            logger.warning('쿠팡 옵션 차단 요약 %d건: %s', len(blocked), ' · '.join(blocked))
        return out or [dict(x) for x in cls.ATTR_FALLBACK]

    def build_attrs(self, product: dict, attr_schema=None) -> list:
        """전송할 attributes. 상품이 준 속성 + **카테고리 메타 필수 속성**을 합쳐 `attr_safe`로 정제.

        메타에 필수 속성이 있으면 값이 비어 있어도 **항목을 만들어** attr_safe가 실값으로 채운다
        (빈 배열 = 카나리 9차 거부). 메타 조회 실패 시에도 fallback(수량 1)이 남는다.
        """
        name = str(product.get('title') or '')
        attrs = [a for a in (product.get('attributes') or []) if isinstance(a, dict)]
        have = {str(a.get('attributeTypeName') or '').strip() for a in attrs}
        for s in (attr_schema or []):
            if not s.get('required'):
                continue                                  # 선택 속성은 만들지 않음(발명 최소)
            an = s.get('attributeTypeName')
            if an and an not in have:
                attrs.append({'attributeTypeName': an, 'attributeValueName': '',
                              'exposed': s.get('exposed') or 'EXPOSED'})
        return self.attr_safe(attrs, name, attr_schema)

    def missing_required_attrs(self, attributes, attr_schema=None) -> list:
        """전송 직전 검증 — 메타가 요구하는 **필수 속성 중 실값이 없는 것**의 이름 목록.

        gtin은 전송 대상이 아니므로 제외(정본). 비어 있지 않으면 호출부가 등록을 중단한다
        (택배사·SKU 게이트와 동형 — 쓰레기 값으로 카나리 태우지 않는다).
        """
        filled = {str(a.get('attributeTypeName') or '').strip()
                  for a in (attributes or [])
                  if str(a.get('attributeValueName') or '').strip() not in self.ATTR_BAD_VALUES}
        return [s['attributeTypeName'] for s in (attr_schema or [])
                if s.get('required') and 'gtin' not in str(s.get('attributeTypeName', '')).lower()
                and s.get('attributeTypeName') not in filled]

    def _build_images(self, product: dict) -> list:
        """옵션 이미지. 첫 장은 REPRESENTATION(대표), 나머지는 DETAIL이어야 한다.

        반려 1호 수리: 아마존 사이즈 토큰을 **대형본(_SS1600_)으로 치환**한다(규격 미달 URL 전송 금지).
        쿼리스트링 제거도 정규화 함수가 담당(정본 동일).
        """
        from src.collectors.image_norm import normalize_image_url
        images = []
        for i, url in enumerate(product.get('images', [])):
            if not url:
                continue
            images.append({
                'imageOrder': i,
                'imageType': 'REPRESENTATION' if i == 0 else 'DETAIL',
                'vendorPath': normalize_image_url(url),
            })
        return images

    def _build_product_payload(self, product: dict, notice_schema=None, attr_schema=None,
                               attributes=None) -> dict:
        """Coupang Wing API용 상품 페이로드를 구성한다.

        쿠팡 createProduct 필수 필드를 모두 채운다(null/누락 시 등록 거부).
        - 옵션(items[])별: 과세/성인/단위수량/최대구매수량기간/해외구매대행/이미지/고시정보/컨텐츠
        - 상품(root): 묶음배송/도서산간/반품지(주소·우편번호·담당자·연락처·배송비)/출고지/vendorUserId
        """
        title = (product.get('title', '') or '상품')[:100]     # 정본: name[:100]
        category_code = product.get('category_id', '')        # 예측은 upload_product에서 해결(없으면 FAIL)
        try:
            category_code = int(str(category_code).strip())    # 정본: displayCategoryCode = int
        except (TypeError, ValueError):
            pass
        sku = str(product.get('sku', '') or '').strip() or title
        try:
            price = int(product.get('price', 0) or 0)
        except (TypeError, ValueError):
            price = 0
        # 정본: 정가 = 판매가 15% 상향 후 100원 반올림(할인 표기용).
        original_price = int(round(price * 1.15 / 100) * 100) if price else 0
        brand = str(product.get('brand', '') or '').strip()
        # 정본: searchTags = [브랜드 정규화[:20] or "수입", "해외직구"] + 키워드, 최대 10.
        tags = product.get('tags') or []
        kw = [str(t).strip() for t in tags if str(t).strip()] if isinstance(tags, list) else []
        search_tags = ([(brand[:20] or '수입'), '해외직구'] + kw)[:10]

        # ★ items[] — 5,691건 검증 정본(오너 SSH 실측 coupang_upload.py:122~145). 카나리 7차 거부
        #   "옵션(...): 10원 이상의 판매가를 입력해주세요"의 정답지. 필드명·값 전부 정본 그대로.
        item = {
            'itemName': sku,                                # 정본: itemName = sku(제목 아님)
            'originalPrice': original_price,                 # 정본: price*1.15 100원 반올림
            'salePrice': price,                              # 정본: 옵션 판매가(누락 시 7차 거부)
            'maximumBuyCount': 3,                            # 정본
            'maximumBuyForPerson': 0,
            'maximumBuyForPersonPeriod': 1,
            'outboundShippingTimeDay': 7,                    # 정본(구매대행 출고 7일)
            'unitCount': 1,
            'adultOnly': 'EVERYONE',
            'taxType': 'TAX',
            'parallelImported': 'NOT_PARALLEL_IMPORTED',
            'overseasPurchased': 'OVERSEAS_PURCHASED',       # 정본(구매대행 고정)
            'pccNeeded': True,                               # 정본(개인통관고유부호 필요)
            'externalVendorSku': sku,
            'emptyBarcode': True,                            # 정본(구 emptyBarcodeYn:'Y' 폐기)
            'emptyBarcodeReason': '구매대행상품 바코드없음',
            # 정본: 인증 실측 정답 — 추정 문구(env) 대신 NOT_REQUIRED 구조를 보낸다.
            'certifications': [{'certificationType': 'NOT_REQUIRED', 'certificationCode': ''}],
            'searchTags': search_tags,
            'images': self._build_images(product),
            'notices': self._build_notices(product, notice_schema)[0],  # 고시정보(실값). 보류판정=upload_product.
            'contents': self._build_contents(product),      # 상세컨텐츠(필수)
            # 필수 구매 옵션 — 정본 attr_safe(빈 배열 전송 금지·BAD 값 실값 대체·카나리 9차 거부 대응).
            # 게이트(upload_product)가 이미 만든 블록을 그대로 쓴다 — 두 번 만들면
            #   '게이트가 본 값'과 '보낸 값'이 갈릴 수 있다(이중 구현 금지).
            'attributes': (attributes if attributes is not None
                           else self.build_attrs(product, attr_schema)),
        }
        return {
            'displayCategoryCode': category_code,
            'sellerProductName': title,
            'vendorId': self.vendor_id,
            # 정본: 판매 시작 = 오늘 00:00:00, 종료 = 2099-01-01T23:59:59.
            'saleStartedAt': datetime.now().strftime('%Y-%m-%dT00:00:00'),
            'saleEndedAt': '2099-01-01T23:59:59',
            'displayProductName': title,
            'generalProductName': title,
            # ★ 정본: brand는 **빈 문자열**, 브랜드는 productGroup에 넣는다.
            #   (브랜드 오인 IPR 회피 설계로 추정 — 5,691건이 이 형태로 통과했으므로 그대로 승계.)
            'brand': '',
            'manufacture': brand or '상세페이지 참조',
            'productGroup': brand,
            'description': product.get('description_html', ''),
            # 배송
            'deliveryMethod': self.delivery_method,          # env COUPANG_[계정_]DELIVERY_METHOD
            'deliveryCompanyCode': self.resolve_delivery_company_code(),   # env 코드 → 쿠팡 목록 매칭(발명 0)
            'deliveryChargeType': self.delivery_charge_type,  # env COUPANG_[계정_]DELIVERY_CHARGE_TYPE
            'deliveryCharge': 0,
            'freeShipOverAmount': 0,
            'deliveryChargeOnReturn': self.return_charge,
            'remoteAreaDeliverable': 'N',                   # 도서산간 배송여부
            'unionDeliveryType': 'NOT_UNION_DELIVERY',      # 묶음배송 여부
            'remoteAreaDeliveryCharge': 0,
            'underPriceGuarantee': False,
            # 출고지/반품지 (셀러 Wing 배송정보)
            'outboundShippingPlaceCode': self._as_int(self.outbound_place_code),   # 정본: int
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

        **계측(스마트스토어 #676과 동형):** 실패 사유는 generic 문구가 아니라
        `stage / attempt / error_type / http_status / body 원문`으로만 말한다.
        429=재시도 · 4xx=즉시 반환(되풀이해도 같은 답 — 원문 버리고 3회 삼키던 것이 로그 고고학의 근원)
        · 5xx=원문 실어 반환. 조립 헬퍼는 `BaseUploader` 단일 소스(재구현 금지).
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
        stage = f'{method.upper()} {path}'
        last = ''
        for attempt in range(3):
            try:
                # 고정 IP 릴레이 경유 — 쿠팡 호출 IP 화이트리스트 대응(v8 / v87-S6-2 mkt.php).
                # 미설정이면 직접 호출(폴백). 서명은 위에서 이미 끝났고 릴레이는 포워딩만.
                resp = relay_request(method, url, json=data, headers=headers, timeout=30,
                                     market="coupang", key=str(self.vendor_id or ""))
                if resp.status_code == 429:
                    last = self._fail_detail(stage, attempt + 1, status=429,
                                             body=self._resp_body(resp))
                    logger.warning('쿠팡 재시도 — %s', last)
                    time.sleep(5 * (attempt + 1))
                    continue
                if resp.status_code == 401:
                    last = self._fail_detail(stage, attempt + 1, status=401,
                                             body=self._resp_body(resp))
                    logger.error('쿠팡 인증 실패 — %s', last)
                    return {'error': f'쿠팡 인증 실패 — {last}'}
                if resp.status_code >= 500:
                    last = self._fail_detail(stage, attempt + 1, status=resp.status_code,
                                             body=self._resp_body(resp))
                    logger.warning('쿠팡 서버 오류 — %s', last)
                    return {'error': f'쿠팡 서버 오류 — {last}'}
                if resp.status_code >= 400:
                    # 4xx는 되풀이해도 같은 답 → 본문을 그대로 실어 즉시 반환(3회 삼키기 금지).
                    last = self._fail_detail(stage, attempt + 1, status=resp.status_code,
                                             body=self._resp_body(resp))
                    logger.warning('쿠팡 거부 — %s', last)
                    return {'error': f'쿠팡 거부 — {last}'}
                resp.raise_for_status()
                return resp.json()
            except RelayError as exc:
                # v87-S6-2: 릴레이 계층 실패는 재시도해도 같다(설정·릴레이 다운) → 즉시 정직 반환.
                #   '쿠팡이 거부함'과 '우리 릴레이가 죽음'을 마켓 카드에서 구분하기 위함(error_type).
                last = self._fail_detail(stage, attempt + 1, exc=exc)
                logger.error('쿠팡 릴레이 실패 — %s', last)
                return {'error': f'쿠팡 릴레이 실패 — {last}'}
            except requests.exceptions.RequestException as exc:
                last = self._fail_detail(stage, attempt + 1, exc=exc,
                                         status=getattr(getattr(exc, 'response', None),
                                                        'status_code', None),
                                         body=self._resp_body(getattr(exc, 'response', None)))
                logger.warning('쿠팡 요청 실패 — %s', last)
                if attempt < 2:
                    time.sleep(3)
        return {'error': f'쿠팡 요청 실패(최대 3회) — {last or "사유 미상"}'}
