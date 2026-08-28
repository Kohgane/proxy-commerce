"""Naver SmartStore 상품 업로더."""

import copy
import json
import logging
import math
import os
import re
import time
from pathlib import Path

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
    # ★ 카테고리 정본(오너 grep `ss_upload.py` CAT) — **순서 유지·첫 매칭 우선**.
    #   쿠팡의 predict_category(API 예측)와 **별개 축**이다: 스마트스토어는 사전 매칭이 정본.
    #   순서를 바꾸면 판정이 바뀐다(예: '주얼리'는 키링 줄 다음에 와야 원래 결과가 나온다). 재정렬 금지.
    CATEGORY_PATTERNS = (
        (r"피젯|EDC|스피너|슬라이더|엔진|오브제|퍼즐|모형|분재", '50004132'),
        (r"슬링백|백팩|가방|패킹큐브|파우치|토트", '50000646'),
        (r"키링|카라비너|스트랩", '50000570'),
        (r"목걸이|팔찌|체인|주얼리", '50000570'),
        (r"멀티툴|나이프|공구|드라이버|드릴|스크러버|에어펌프|레이저|인두", '50003413'),
        (r"가위|원예|전정", '50000406'),
        (r"잔|글라스|텀블러|머그|드리퍼|티|주전자|도마|주방", '50004737'),
        (r"만년필|노트|문구|북마크|데스크", '50002335'),
        (r"신디사이저|이어팁|카드리더|허브|오디오|스피커|헤드폰", '50000205'),
        (r"재킷|티셔츠|샌들|의류", '50000167'),
        (r"향|캔들|디퓨저", '50001854'),
    )
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

    # ── 정본 페이로드 템플릿(오너 SSH `ss_template.json`) — 카나리 7차 근원 ──────────
    #   네이버 400: `originProduct.detailAttribute.minorPurchasable NotNull`.
    #   정본 `ss_upload.py`는 **템플릿의 originProduct 기본값 위에 페이로드를 얹는** 구조인데
    #   그 템플릿이 미승계라 기본 필드가 비었다. 필드를 **하나씩 때우지 않는다** — 템플릿에 다른
    #   필수 기본값이 더 있을 개연이 높아 통째 승계가 왕복 최소(택배사 교훈·오너 지시 2항).
    TEMPLATE_PATH = Path(__file__).with_name('ss_template.json')
    _template_cache = None
    _template_warned = False
    # 템플릿에 남아 있는 **상품별 예시값**(오너 실측: 하베스트라벨 건). 이게 페이로드에 살아 나가면
    #   남의 상품 정보를 우리 상품에 붙여 등록하는 것 — 정직 데이터 위반이자 마켓 제재 사유다.
    #   우리가 덮어야 할 필드를 하나라도 빠뜨리면 조용히 새므로 **전송 직전 게이트**로 막는다.
    #   env `NAVER_TEMPLATE_EXAMPLE_TOKENS`(쉼표 구분)로 추가 가능.
    TEMPLATE_EXAMPLE_TOKENS = ('HARVEST LABEL', 'hgl-0187')
    # 상품고시정보 타입 — **정본 값 그대로**(오너 실측: 통과 이력 조합 = "ETC"(대문자) + `etc{}` 블록).
    #   카나리 8차 근원: 우리가 `etc{}`만 넣고 **타입을 안 넣어** 네이버가 NotValidEnum.
    #   이 값은 **오버라이드가 아니라 폴백**이다 — 템플릿이 타입을 주면 그쪽이 이긴다(정본 우선).
    CANON_NOTICE_TYPE = 'ETC'

    @classmethod
    def payload_template(cls) -> dict:
        """정본 템플릿(캐시). 파일이 없거나 비었으면 **빈 dict** — 현재 동작 불변(정직).

        `_` 접두 키는 메모용이라 전송 페이로드에서 제외한다(네이버 필드에 `_` 접두는 없다).
        """
        if cls._template_cache is None:
            try:
                raw = json.loads(cls.TEMPLATE_PATH.read_text(encoding='utf-8'))
            except FileNotFoundError:
                raw = {}
            except Exception as exc:                       # 형식 오류를 조용히 넘기지 않는다
                logger.error('정본 템플릿(%s) 파싱 실패 — 빈 템플릿으로 진행: %s',
                             cls.TEMPLATE_PATH.name, exc)
                raw = {}
            cls._template_cache = {k: v for k, v in (raw or {}).items()
                                   if not str(k).startswith('_')}
        return cls._template_cache

    @classmethod
    def template_status(cls) -> dict:
        """템플릿 승계 상태(진단용). 미승계면 `ready=False` — '됐다'고 말하지 않는다."""
        tpl = cls.payload_template()
        return {'ready': bool(tpl), 'path': str(cls.TEMPLATE_PATH),
                'top_keys': sorted(tpl.keys()),
                'origin_product_keys': sorted((tpl.get('originProduct') or {}).keys())}

    @classmethod
    def _example_tokens(cls) -> tuple:
        extra = [t.strip() for t in os.getenv('NAVER_TEMPLATE_EXAMPLE_TOKENS', '').split(',')
                 if t.strip()]
        return tuple(cls.TEMPLATE_EXAMPLE_TOKENS) + tuple(extra)

    @classmethod
    def find_template_leaks(cls, payload) -> list:
        """전송 페이로드에 **템플릿 예시값이 남았는지** 전수 스캔. 반환 [{'path','token','value'}].

        우리가 덮을 필드를 하나 빠뜨리면 남의 상품명·SKU가 그대로 나간다(하베스트라벨 건).
        필드명을 열거해 막으면 또 빠뜨리므로 **값 기준으로 전수 검사**한다.
        """
        tokens = cls._example_tokens()
        found = []

        def _walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    _walk(v, f'{path}.{k}' if path else str(k))
            elif isinstance(node, (list, tuple)):
                for i, v in enumerate(node):
                    _walk(v, f'{path}[{i}]')
            elif isinstance(node, str):
                for t in tokens:
                    if t and t.lower() in node.lower():
                        found.append({'path': path, 'token': t, 'value': node[:80]})
        _walk(payload, '')
        return found

    @staticmethod
    def _deep_merge(base: dict, over: dict) -> dict:
        """`base`(템플릿 기본값) 위에 `over`(우리 페이로드)를 **깊게** 덮어쓴다.

        얕은 `update`면 우리 페이로드가 `detailAttribute`를 통째로 대입하는 순간 템플릿의
        형제 기본값(`minorPurchasable` 등)이 **지워진다** — 템플릿을 승계하는 의미가 사라진다.
        그래서 dict끼리만 재귀하고, 스칼라·리스트는 페이로드가 이긴다(정본: deepcopy 후 덮어쓰기).
        """
        for key, val in (over or {}).items():
            cur = base.get(key)
            if isinstance(cur, dict) and isinstance(val, dict):
                NaverSmartStoreUploader._deep_merge(cur, val)
            else:
                base[key] = val
        return base

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
        # 이미지 업로드 게이트(정본) — 등록당 N장 다운로드+업로드가 붙으므로 env로 끌 수 있게.
        #   기본 ON: 외부 CDN URL을 그대로 넣으면 네이버가 거부하거나 이미지가 깨진다.
        self.image_upload_enabled = os.getenv('NAVER_IMAGE_UPLOAD', '1').strip().lower() not in (
            '0', 'false', 'no', 'off')
        self._access_token = None
        self._token_expires = 0
        self.token_error = ''          # 발급 실패 원문(조용한 실패 금지 — 호출부가 그대로 노출)
        # 스마트스토어는 보통 **스토어별 앱**이다. 계정 접두 키가 없어 공용 키로 떨어지면
        #   두 스토어가 같은 자격을 쓰게 되므로 경고를 남긴다(조용한 혼입 방지).
        if self.account and self.client_id and not os.getenv(
                f"{self.ACCOUNT_PREFIXES.get(self.account, 'NAVER')}_CLIENT_ID", '').strip():
            logger.warning('%s 전용 자격(%s_CLIENT_ID) 미설정 — 공용 키로 발급합니다(스토어 혼입 주의).',
                           self.account, self.ACCOUNT_PREFIXES.get(self.account, 'NAVER'))

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
            # 이미지 정본: 외부 URL을 **네이버 CDN으로 업로드**한 뒤 그 URL로 등록한다.
            #   0장이면 등록 차단(정본의 raise와 같은 철학 — 이미지 없는 상품 공개 금지).
            if self.image_upload_enabled and product.get('images'):
                shot = self.upload_images(product.get('images'))
                if not shot['ok']:
                    return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                            'error': f"이미지 업로드 실패 — 등록 중단: {shot['reason']}"}
                if shot['skipped']:
                    logger.info('이미지 %d장 스킵 sku=%s — %s', len(shot['skipped']),
                                product.get('sku', ''),
                                '; '.join(s['reason'] for s in shot['skipped']))
                product = {**product, 'images': shot['urls']}
            payload = self._build_product_payload(product)
            # 템플릿 예시값 유출 게이트 — 남의 상품 정보로 등록하느니 **중단**한다(택배사 게이트 동형).
            leaks = self.find_template_leaks(payload)
            if leaks:
                detail = '; '.join(f"{l['path']}={l['value']}" for l in leaks[:3])
                logger.error('템플릿 예시값 유출 %d건 — 등록 중단 sku=%s: %s',
                             len(leaks), product.get('sku', ''), detail)
                return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                        'error': f'템플릿 예시값이 페이로드에 남아 등록 중단({len(leaks)}건): {detail}'}
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

        **조립 순서(정본과 동일)**: `deepcopy(템플릿)` → 그 위에 아래 페이로드를 **깊게** 덮어쓴다.
        템플릿이 비어 있으면 결과는 페이로드 그대로(현재 동작 불변).
        """
        payload = self._compose_payload(product)
        tpl = self.payload_template()
        if not tpl and not type(self)._template_warned:
            type(self)._template_warned = True
            logger.warning('정본 템플릿(%s) 미승계 — originProduct 필수 기본값이 빠질 수 있습니다'
                           ' (카나리 7차: detailAttribute.minorPurchasable NotNull).',
                           self.TEMPLATE_PATH.name)
        merged = self._deep_merge(copy.deepcopy(tpl), payload)
        self._ensure_notice_type(merged)
        return merged

    @classmethod
    def _ensure_notice_type(cls, payload: dict) -> dict:
        """상품고시정보 타입 보정 — **없을 때만** 정본 `ETC`를 채운다(오버라이드 아님).

        카나리 8차: `etc{}` 블록만 있고 타입이 없어 `productInfoProvidedNoticeType NotValidEnum`.
        정본 조합은 `"ETC"` + `etc{}`이므로 타입이 비면 그 값을 채우고, 템플릿이 이미 타입을
        주고 있으면 **손대지 않는다**(정본이 우선 — 다른 카테고리는 다른 타입을 쓸 수 있다).
        """
        notice = (((payload or {}).get('originProduct') or {})
                  .get('detailAttribute') or {}).get('productInfoProvidedNotice')
        if isinstance(notice, dict) and not str(notice.get('productInfoProvidedNoticeType') or '').strip():
            notice['productInfoProvidedNoticeType'] = cls.CANON_NOTICE_TYPE
        return payload

    def _compose_payload(self, product: dict) -> dict:
        """우리가 채우는 값만 담은 페이로드(템플릿 오버레이 대상). 기본값은 템플릿이 맡는다."""
        images = [u for u in (product.get('images') or []) if u]
        rep = images[0] if images else ''
        optional = [{'url': u} for u in images[1:]]
        price = int(product.get('price', 0) or 0)
        return {
            'originProduct': {
                'statusType': self.STATUS_TYPE,
                'saleType': 'NEW',
                # 명시 카테고리 없으면 **정본 사전 매칭**(상품명 기준·순서 우선), 그래도 없으면 기본 리프.
                'leafCategoryId': (str(product.get('category_id') or '').strip()
                                   or self.resolve_category(product.get('title'))),
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
                    # ★ 상품고시정보 — 템플릿 예시값(하베스트라벨) 위에 **우리 상품 값을 반드시 덮는다**.
                    #   출처는 쿠팡 고시정보와 **같은 소스**: 상품명·SKU·수집 브랜드·AS 연락처(env).
                    #   비어 있으면 빈 값으로 덮는다 — 남의 브랜드를 붙여 등록하느니 네이버가
                    #   '필수값 없음'으로 거부하는 편이 정직하다(가짜 정보 0).
                    'productInfoProvidedNotice': {
                        'etc': {
                            'itemName': (product.get('title') or '')[:100],
                            'modelName': product.get('sku', ''),
                            'manufacturer': product.get('brand', ''),
                            'afterServiceDirector': self._acct_env('NAVER_AS_PHONE'),
                        },
                    },
                    # 구매대행 통관(정본) — 템플릿의 NOT_APPLICABLE을 덮는다(우리가 구매대행이다).
                    'customsTaxType': self.CUSTOMS_TAX_TYPE,
                },
            },
            'smartstoreChannelProduct': {
                'channelProductDisplayStatusType': 'ON',
                'naverShoppingRegistration': self.NAVER_SHOPPING_REGISTRATION,
            },
        }

    # ── 이미지 업로드 정본(오너 SSH `naver_img.py`) ──────────────────────────────
    IMAGE_MIN_BYTES = 1024          # 정본: 1KB 미만은 썸네일 쓰레기 → 스킵
    IMAGE_MAX_COUNT = 10            # 정본: 한 번에 최대 10장
    IMAGE_RETRY = 3                 # 정본: 429·예외 모두 최대 3회
    # 카나리 3차 반려 원문: "PhotoInfraUpload.extension — JPEG/JPG/GIF/PNG/BMP만 허용".
    # 소스가 amazon.de WebP였다. **이 집합은 네이버 전용** — 쿠팡/WC는 webp 무해하므로 강제 안 함.
    IMAGE_ALLOWED_FORMATS = ('jpg', 'jpeg', 'png', 'gif', 'bmp')

    @classmethod
    def normalize_source_url(cls, url: str) -> str:
        """외부 이미지 URL 정규화(정본): 쿼리스트링 제거 · `//` 시작이면 https: 부착."""
        u = str(url or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        return u.split('?')[0]

    def _fetch_image(self, url: str, on_skip=None):
        """외부 URL → `FetchedImage`(bytes·content_type·ext). 실패/규격미달이면 None.

        **다운로드는 `collectors.image_norm.fetch_image_bytes`에 위임**한다 — 소스 CDN 다운로드는
        마켓 아웃바운드가 아니지만, 이 모듈은 마켓 호출 전용 관문(v87-S7: 직결 requests 금지)이라
        외부 fetch를 밖으로 뺀다. UA·1KB·확장자 판별 규칙은 그쪽이 정본으로 보유.

        `allowed_formats`를 여기서만 넘긴다 — 네이버가 거부하는 WebP를 **JPEG로 실변환**(파일명
        위장 아님)해서 받는다. 변환 실패는 None → 그 이미지 스킵, 0장이면 기존 게이트가 등록 차단.

        `on_skip(url, reason)`은 **스킵 사유**를 받아 온다(조용한 스킵 금지 — 1KB 미만인지·
        다운로드 실패인지·변환 실패인지 호출부가 그대로 표기한다).
        """
        from src.collectors.image_norm import fetch_image_bytes
        return fetch_image_bytes(url, min_bytes=self.IMAGE_MIN_BYTES,
                                 allowed_formats=self.IMAGE_ALLOWED_FORMATS,
                                 on_skip=on_skip)

    def upload_images(self, urls) -> dict:
        """외부 이미지 URL 목록 → **네이버 CDN URL** 목록. 정본 `naver_img.upload` 승계.

        흐름: 정규화 → 서버가 다운로드 → `multipart/form-data`(필드명 `imageFiles` 반복) 업로드 →
        응답 `images[].url`. **릴레이 경유**(IP 게이트 — 직결 시 GW.IP_NOT_ALLOWED).
        반환 {ok, urls, skipped, reason}. 조용한 실패 금지 — 오류 본문 200자까지 사유에 담는다.
        """
        cleaned, skipped = [], []
        for u in (urls or [])[:self.IMAGE_MAX_COUNT]:
            n = self.normalize_source_url(u)
            if not n:
                skipped.append({'url': str(u or ''), 'reason': 'URL 정규화 실패'})
                continue
            got = self._fetch_image(
                n, on_skip=lambda su, sr: skipped.append({'url': su, 'reason': sr}))
            if got is None:
                if not any(s['url'] == n for s in skipped):     # 사유 없이 빠지는 일 없게(보루)
                    skipped.append({'url': n, 'reason': '사유 미상'})
                continue
            cleaned.append(got)
        if skipped:
            logger.info('이미지 %d장 스킵 — %s', len(skipped),
                        '; '.join(f"{s['reason']}({s['url'][-48:]})" for s in skipped))
        if not cleaned:
            return {'ok': False, 'urls': [], 'skipped': skipped,
                    'reason': ('업로드할 이미지 0장 — '
                               + '; '.join(s['reason'] for s in skipped[:3]))}

        token = self._get_access_token()
        if not token:
            # 원문이 범인을 지목한다(invalid_client·GW.IP_NOT_ALLOWED·서명 오류 등) — 그대로 올린다.
            return {'ok': False, 'urls': [], 'skipped': skipped,
                    'reason': f'네이버 토큰 발급 실패 — {self.token_error or "사유 미상"}'}
        # multipart 본문을 미리 조립해 **바이트로** 넘긴다 — 릴레이(mkt.php)가 body를 base64로
        #   그대로 전달하므로, 이렇게 하면 직결·릴레이 어느 경로든 같은 요청이 나간다.
        # ★ 카나리 5차 근원: 2-튜플 `(filename, body)`을 주면 requests가 **part Content-Type을 아예
        #   안 붙인다**(실측). 네이버 PhotoInfra가 part MIME으로 확장자를 판정하면 빈 값 → `.extension`
        #   거부. 3-튜플로 **filename·바이트·MIME을 한 세트**로 넘긴다 — 셋 다 `FetchedImage` 출처.
        files = [('imageFiles', (p.filename, p.data, p.content_type)) for p in cleaned]
        prepped = requests.Request('POST', self.API_BASE + self.IMAGE_UPLOAD_PATH,
                                   files=files).prepare()
        # 카나리 진단: 실제로 나가는 part 메타를 남긴다(다음 반려 때 추측 대신 증거로 판정).
        logger.info('네이버 이미지 업로드 %d장 — parts=%s', len(cleaned),
                    ', '.join(f'{p.filename}({p.content_type},{len(p.data)}B)' for p in cleaned))
        headers = {'Authorization': f'Bearer {token}',
                   'Content-Type': prepped.headers['Content-Type']}
        payload_bytes = len(prepped.body or b'')
        last = ''
        for att in range(self.IMAGE_RETRY):
            try:
                resp = relay_request('POST', self.API_BASE + self.IMAGE_UPLOAD_PATH,
                                     headers=headers, data=prepped.body, timeout=60,
                                     market='smartstore', key=str(self.client_id or ''))
                if getattr(resp, 'status_code', 0) == 429:
                    last = self._fail_detail('image_upload', att + 1, status=429,
                                             body=self._resp_body(resp))
                    logger.warning('이미지 업로드 재시도 — %s', last)
                    time.sleep(3 * (att + 1))          # 정본 백오프
                    continue
                resp.raise_for_status()
                data = resp.json()
                out = [i.get('url') for i in (data.get('images') or []) if i.get('url')]
                if not out:
                    return {'ok': False, 'urls': [], 'skipped': skipped,
                            'reason': f'네이버 응답에 이미지 URL 없음: {str(data)[:200]}'}
                logger.info('네이버 이미지 업로드 성공 %d장(%dB 전송)', len(out), payload_bytes)
                return {'ok': True, 'urls': out, 'skipped': skipped, 'reason': ''}
            except requests.exceptions.HTTPError as exc:
                status = getattr(exc.response, 'status_code', None)
                last = self._fail_detail('image_upload', att + 1, exc=exc, status=status,
                                         body=self._resp_body(exc.response))
                logger.warning('이미지 업로드 실패 — %s', last)
                # 4xx는 같은 요청을 되풀이해도 같은 답이다 — 즉시 사유를 올린다(재시도 낭비 0).
                if status is not None and 400 <= int(status) < 500 and int(status) != 429:
                    break
                time.sleep(3 * (att + 1))
            except Exception as exc:
                last = self._fail_detail('image_upload', att + 1, exc=exc)
                logger.warning('이미지 업로드 실패 — %s', last)
                time.sleep(3 * (att + 1))
        return {'ok': False, 'urls': [], 'skipped': skipped,
                'reason': f'이미지 업로드 실패(최대 {self.IMAGE_RETRY}회, 전송 {payload_bytes}B): {last}'}

    # ── 실패 원문 노출(카나리 6차) ────────────────────────────────────────────────
    #   generic "API request failed after retries"는 로그 고고학을 강제한다. 재시도 루프가
    #   **둘**(이미지 업로드·상품 등록)이므로 사유 조립을 **한 함수로** 둔다 — 한쪽만 고쳐지는
    #   패턴(#673 서명·#675 part MIME)을 또 만들지 않기 위해.
    @staticmethod
    def _resp_body(resp, limit: int = 200) -> str:
        """응답 본문 앞 limit자. 못 읽으면 빈 문자열(사유 조립이 예외로 죽지 않게)."""
        try:
            return (getattr(resp, 'text', '') or '')[:limit]
        except Exception:
            return ''

    @staticmethod
    def _fail_detail(stage: str, attempt: int, *, exc=None, status=None, body: str = '') -> str:
        """{stage, attempt, error_type, http_status, body[:200]} 한 줄.

        `RelayError`는 `requests.RequestException`을 상속하므로 **릴레이가 죽은 것**과
        **마켓이 거부한 것**이 같은 except로 잡힌다 — error_type을 찍어 둘을 가른다.
        """
        parts = [f'stage={stage}', f'attempt={attempt}']
        if exc is not None:
            parts.append(f'error_type={type(exc).__name__}')
            parts.append(f'error={str(exc)[:200]}')
        if status is not None:
            parts.append(f'http_status={status}')
        if body:
            parts.append(f'body={body}')
        return ' '.join(parts)

    @classmethod
    def resolve_category(cls, title: str) -> str:
        """상품명 → 리프 카테고리 ID. **정본 사전 매칭**(순서 유지·첫 매칭 우선), 미매칭이면 기본 리프.

        쿠팡은 예측 API가 정본이고 실패 시 등록을 중단하지만, 스마트스토어는 **사전 매칭이 정본**이라
        미매칭도 기본 리프로 등록한다(정본 스크립트 동작 그대로 — 규칙을 바꾸지 않는다).
        """
        name = str(title or '')
        for pattern, leaf in cls.CATEGORY_PATTERNS:
            if re.search(pattern, name, re.I):
                return leaf
        return cls.DEFAULT_LEAF_CATEGORY

    @staticmethod
    def _as_int(v):
        """주소 ID 등 정본상 int로 보내야 하는 값. 숫자가 아니면 원본 유지(정직)."""
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return v

    def _get_access_token(self) -> str:
        """OAuth2 client_credentials 토큰 발급. 실패 사유는 `self.token_error`에 **원문 200자**로 남긴다.

        **정본 서명 = bcrypt `client_secret_sign`**(평문 client_secret 아님).
        서명 규칙은 `market_adapters.smartstore_adapter._naver_signature`가 단일 소스 —
        이 파일이 따로 구현하면 두 경로가 갈린다(카나리 1차 실패의 근원이 정확히 그것이었다).

        v87-S7: 발급도 **릴레이 경유**(직결이면 네이버가 IP로 막아 토큰부터 실패 → 연쇄 실패).
        """
        now = time.time()
        if self._access_token and now < self._token_expires - 60:
            return self._access_token
        self.token_error = ''
        if not self.client_id or not self.client_secret:
            self.token_error = ('네이버 커머스 자격 미설정 — '
                                f'{self._cred_env_hint()} 를 설정하세요.')
            return ''
        from src.seller_console.market_adapters.smartstore_adapter import _naver_signature
        timestamp = str(int(now * 1000))
        sign = _naver_signature(self.client_id, self.client_secret, timestamp)
        if not sign:
            self.token_error = ("전자서명 생성 실패 — Client Secret이 '$2a$…' 형식(bcrypt salt)인지 "
                                "확인하세요. 평문 시크릿은 네이버가 받지 않습니다.")
            logger.warning('네이버 토큰 발급 실패(서명): %s', self.token_error)
            return ''
        try:
            resp = relay_request(
                'POST', self._TOKEN_URL,
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'timestamp': timestamp,
                    'client_secret_sign': sign,      # ★ 정본: bcrypt 서명(평문 secret 아님)
                    'type': 'SELF',
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=15, market="smartstore", key=str(self.client_id or ""),
            )
        except Exception as exc:
            self.token_error = f'토큰 요청 실패: {str(exc)[:200]}'
            logger.error('네이버 토큰 발급 실패(요청): %s', self.token_error)
            return ''
        status = getattr(resp, 'status_code', 0)
        if status != 200:
            # ★ 원문이 범인을 지목한다(invalid_client·GW.IP_NOT_ALLOWED·서명 오류 등) — 조용한 실패 금지.
            body = (getattr(resp, 'text', '') or '').strip().replace('\n', ' ')[:200]
            self.token_error = f'HTTP {status}: {body}'
            logger.warning('네이버 토큰 발급 실패 HTTP %s: %s', status, body)
            return ''
        try:
            data = resp.json()
        except Exception as exc:
            self.token_error = f'토큰 응답 파싱 실패: {str(exc)[:200]}'
            return ''
        self._access_token = data.get('access_token', '')
        if not self._access_token:
            self.token_error = f'응답에 access_token 없음: {str(data)[:200]}'
            return ''
        self._token_expires = now + int(data.get('expires_in', 3600))
        return self._access_token

    def _cred_env_hint(self) -> str:
        """이 계정이 읽는 자격 env 이름(설정 안내용). 계정 접두가 있으면 그것을 먼저 안내한다."""
        prefix = self.ACCOUNT_PREFIXES.get(self.account or '')
        if prefix:
            return f'{prefix}_CLIENT_ID/{prefix}_CLIENT_SECRET (또는 공용 NAVER_COMMERCE_CLIENT_ID/SECRET)'
        return 'NAVER_COMMERCE_CLIENT_ID / NAVER_COMMERCE_CLIENT_SECRET'

    def _api_request(self, method: str, path: str, data: dict = None) -> dict:
        """Naver Commerce API에 요청을 전송한다."""
        if not self.client_id or not self.client_secret:
            return {'error': f'네이버 커머스 자격 미설정 — {self._cred_env_hint()}'}
        token = self._get_access_token()
        if not token:
            return {'error': f'네이버 토큰 발급 실패 — {self.token_error or "사유 미상"}'}
        url = self.API_BASE + path
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json;charset=UTF-8',
        }
        stage = f'{method.upper()} {path}'
        last = ''
        for attempt in range(3):
            try:
                # 고정 IP 릴레이 경유 — 네이버 호출 IP 화이트리스트 대응(v8 / v87-S6-2 mkt.php).
                resp = relay_request(method, url, json=data, headers=headers, timeout=30,
                                     market="smartstore", key=str(self.client_id or ""))
                if resp.status_code == 429:
                    last = self._fail_detail(stage, attempt + 1, status=429,
                                             body=self._resp_body(resp))
                    logger.warning('네이버 재시도 — %s', last)
                    time.sleep(5 * (attempt + 1))
                    continue
                if resp.status_code == 401:
                    # 토큰 무효화 후 재시도
                    last = self._fail_detail(stage, attempt + 1, status=401,
                                             body=self._resp_body(resp))
                    self._access_token = None
                    self._token_expires = 0
                    if attempt < 2:
                        token = self._get_access_token()
                        headers['Authorization'] = f'Bearer {token}'
                        continue
                    return {'error': f'네이버 인증 실패 — {last}'}
                if resp.status_code >= 500:
                    last = self._fail_detail(stage, attempt + 1, status=resp.status_code,
                                             body=self._resp_body(resp))
                    logger.warning('네이버 서버 오류 — %s', last)
                    return {'error': f'네이버 서버 오류 — {last}'}
                # ★ 카나리 6차 근원: 여기서 `raise_for_status()`가 4xx를 HTTPError로 던지면
                #   아래 except가 **원문을 버리고** 3회 재시도 후 generic 문구만 남겼다.
                #   4xx는 되풀이해도 같은 답이므로 **본문을 그대로 실어 즉시 반환**한다.
                if resp.status_code >= 400:
                    last = self._fail_detail(stage, attempt + 1, status=resp.status_code,
                                             body=self._resp_body(resp))
                    logger.warning('네이버 거부 — %s', last)
                    return {'error': f'네이버 거부 — {last}'}
                resp.raise_for_status()
                if resp.content:
                    return resp.json()
                return {}
            except requests.exceptions.RequestException as exc:
                # RelayError도 여기로 온다(RequestException 상속) — error_type이 둘을 가른다.
                last = self._fail_detail(stage, attempt + 1, exc=exc,
                                         status=getattr(getattr(exc, 'response', None),
                                                        'status_code', None),
                                         body=self._resp_body(getattr(exc, 'response', None)))
                logger.warning('네이버 요청 실패 — %s', last)
                if attempt < 2:
                    time.sleep(3)
        return {'error': f'네이버 요청 실패(최대 3회) — {last or "사유 미상"}'}
