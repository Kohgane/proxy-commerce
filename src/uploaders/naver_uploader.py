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

    # Y7-B(2026-10-08): 옛 `CATEGORY_MAP`(정규화 코드 → 50000000 등)은 **전부 최상위 카테고리**였다 — 리프가 아니라
    #   네이버가 `leafCategoryId NotValid`(400)로 거부했다(운영 등록 성공 0건). 지웠다. 카테고리는 오너 지정
    #   (`naver_category_id`) → 정본 사전 매칭(`CATEGORY_PATTERNS`) 순서이고, 리프 여부는 `naver_categories`가 잰다.

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
    # ★ 카테고리 사전(오너 grep `ss_upload.py` CAT의 낱말·리프에서 출발) — 쿠팡 예측과 **별개 축**.
    #   Y7-D(오너 2026-10-08): 판정은 **줄 순서와 무관**하다(`match_category`).
    #   - 상품명에 들어 있는 낱말 중 **가장 긴 낱말**을 가진 줄이 이긴다.
    #   - 같은 길이면 그 줄의 낱말이 상품명에 **더 많이** 든 쪽, 그래도 같으면 위 줄.
    #   - 한 글자 낱말은 상품명 낱말 **전체**이거나 **끝 글자**일 때만 — 한국어 합성어는 뒤가 중심 말.
    #   Y7-D 후속(오너 2026-10-08): 「노트」「허브」「데스크」 삭제(너무 넓음).
    #   Y7-D 결정 2(오너 2026-10-09): 정본 리프 ID를 **운영 네이버 트리**(app_state `naver_categories`)와 대조해
    #   (a) 리프이고 (b) 경로 이름이 낱말 뜻과 맞는 것만 남겼다 — 고치지 않고 **삭제**(맞는 ID를 짐작해 넣는 게 더 위험).
    #     삭제: 50004132 보드게임(피젯·퍼즐… / 기본 리프) · 50000646 남성가방>숄더백(백팩·파우치…) ·
    #           50000570 키링(목걸이·팔찌·주얼리 / 카라비너·스트랩) · 50003413 전동드릴(멀티툴·나이프…) ·
    #           50000406 네일케어도구(가위·원예) · 50004737 건어물>멸치(텀블러·머그·주전자…) ·
    #           50002335 목록에 없음(문구) · 50000205·50000167 상위 분류(음향·의류) · 50001854 주방가전>냉동고(캔들·디퓨저)
    #   사전이 못 정하면 기본 리프로 채우지 않는다 — 내가 고른 기록 → 쿠팡 예측 다리(Y7-C/E) → 못 정하면 보류(`category_unset`).
    #   ★ 낱말을 더할 때는 **네이버 리프 ID(운영 트리 대조)와 테스트 없이 추가 금지** — 낱말 하나가 운영 상품명 수십 개를 옮긴다.
    CATEGORY_PATTERNS = (
        (r"키링", '50000570'),              # 패션잡화>패션소품>키링 (운영 트리 2026-10-08 23:37 KST)
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

    # 템플릿에서 **상품별 값**이 들어 있는 경로(구조 기본값과 구분). 여기 값들은 전부 우리가 덮어야 한다.
    TEMPLATE_PRODUCT_PATHS = (
        ('originProduct', 'name'),
        ('originProduct', 'detailContent'),
        ('originProduct', 'images', 'representativeImage', 'url'),
        ('originProduct', 'detailAttribute', 'sellerCodeInfo', 'sellerManagementCode'),
        ('originProduct', 'detailAttribute', 'productInfoProvidedNotice', 'etc', 'itemName'),
        ('originProduct', 'detailAttribute', 'productInfoProvidedNotice', 'etc', 'modelName'),
        ('originProduct', 'detailAttribute', 'productInfoProvidedNotice', 'etc', 'manufacturer'),
        ('smartstoreChannelProduct', 'channelProductName'),
    )

    @classmethod
    def template_product_values(cls) -> tuple:
        """템플릿에 박힌 **상품별 값**들. 토큰을 손으로 나열하지 않아도 템플릿이 바뀌면 따라온다.

        `optionalImages`는 리스트라 별도로 훑는다. 구조 기본값(CJGLS·ETC 등)은 여기 안 들어온다 —
        경로를 명시했기 때문(값 전체를 긁으면 정상 값까지 유출로 오판한다).
        """
        tpl = cls.payload_template()
        out = []
        for path in cls.TEMPLATE_PRODUCT_PATHS:
            node = tpl
            for key in path:
                node = (node or {}).get(key) if isinstance(node, dict) else None
            if isinstance(node, str) and node.strip():
                out.append(node.strip())
        for img in (((tpl.get('originProduct') or {}).get('images') or {})
                    .get('optionalImages') or []):
            url = (img or {}).get('url') if isinstance(img, dict) else None
            if isinstance(url, str) and url.strip():
                out.append(url.strip())
        return tuple(out)

    @classmethod
    def _example_tokens(cls) -> tuple:
        extra = [t.strip() for t in os.getenv('NAVER_TEMPLATE_EXAMPLE_TOKENS', '').split(',')
                 if t.strip()]
        return tuple(cls.TEMPLATE_EXAMPLE_TOKENS) + cls.template_product_values() + tuple(extra)

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
                    # 같은 경로가 여러 토큰(하드코딩·템플릿 파생)에 걸려도 **1건**으로 보고한다.
                    if t and t.lower() in node.lower():
                        found.append({'path': path, 'token': t, 'value': node[:80]})
                        break
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
        _pfx = self.ACCOUNT_PREFIXES.get(self.account or '')
        if _pfx:
            # V1''(오너 2026-10-03): 스토어 계정은 **자기 이름만** 읽는다 — `NAVER_<STORE>_CLIENT_ID/SECRET`.
            #   예전엔 없으면 공용 NAVER_CLIENT_ID(= 네이버 **로그인** OAuth 키와 같은 이름)·NAVER_COMMERCE_*로
            #   떨어져, 두 스토어가 한 앱 키를 쓰거나 로그인 키로 토큰을 청하는 일이 조용히 났다.
            self.client_id = os.getenv(f'{_pfx}_CLIENT_ID', '').strip()
            self.client_secret = os.getenv(f'{_pfx}_CLIENT_SECRET', '').strip()
            if not (self.client_id and self.client_secret):
                # V 추가: 공용 NAVER_COMMERCE_* 가 **실측으로 이 스토어 앱**이라고 확정됐을 때만 승격(캐시만 본다 — 네트워크 0).
                try:
                    from src.seller_console.smartstore_routing import promoted_store
                    if promoted_store() == self.account:
                        self.client_id = os.getenv('NAVER_COMMERCE_CLIENT_ID', '').strip()
                        self.client_secret = os.getenv('NAVER_COMMERCE_CLIENT_SECRET', '').strip()
                except Exception:
                    pass
        else:
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
            # Y7-F: 상세 본문의 이미지도 대표 사진과 같은 네이버 CDN으로(정본 템플릿도 shop-phinf 주소). 못 올린 장은 본문에서 뺀다.
            if self.image_upload_enabled and '<img' in str(product.get('description_html') or ''):
                product = {**product, 'description_html': self._detail_to_cdn(product.get('description_html') or '',
                                                                              product.get('sku', ''))}
            # Y7-F: 상세 본문이 비면 보내지 않는다 — 네이버까지 가서 400 `detailContent NotBlank`를 받지 않게(사전검증과 같은 판정).
            from src.uploaders import naver_detail as _nd
            if not _nd.body_has_content(product.get('description_html') or ''):
                from src.uploaders import naver_invalid as _ni
                _r = _ni.row('originProduct.detailContent', '', str(product.get('item_id') or ''))
                return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                        'reason_code': 'naver_required_detailContent', 'error': _r['line'],
                        'error_lines': [_r['line']], 'action_url': _r['action_url'], 'action_label': _r['action_label']}
            # Y7 — 조합형 옵션(신규 등록만). 못 보내는 모양이면 **전송 0**으로 보류하고 사유코드를 싣는다.
            from src.uploaders.naver_options import plan as _option_plan
            opt = _option_plan(product, stock_default=self.STOCK_QUANTITY)
            if opt['mode'] == 'hold':
                logger.info('네이버 옵션 보류 sku=%s code=%s', product.get('sku', ''), opt['reason_code'])
                return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                        'reason_code': opt['reason_code'], 'error': opt['why']}
            product = {**product, '_option_plan': opt}
            # Y7-C: 카테고리는 사전검증과 **같은 함수**로 정한다(오너 지정 → 내가 고른 기록 → 사전 → 쿠팡 예측 다리).
            from src.uploaders import naver_categories as _ncat
            _cid, _csrc = _ncat.pick({**product, 'naver_category_id': product.get('category_id')})
            if _cid and _csrc != 'manual':
                logger.info('네이버 카테고리 %s(%s) sku=%s', _cid, _csrc, product.get('sku', ''))
                product = {**product, 'category_id': _cid}
            payload = self._build_product_payload(product)
            # 템플릿 예시값 유출 게이트 — 남의 상품 정보로 등록하느니 **중단**한다(택배사 게이트 동형).
            leaks = self.find_template_leaks(payload)
            if leaks:
                detail = '; '.join(f"{l['path']}={l['value']}" for l in leaks[:3])
                logger.error('템플릿 예시값 유출 %d건 — 등록 중단 sku=%s: %s',
                             len(leaks), product.get('sku', ''), detail)
                return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                        'error': f'템플릿 예시값이 페이로드에 남아 등록 중단({len(leaks)}건): {detail}'}
            # Y7-B — 리프 카테고리 가드(사전검증과 같은 판정). 네이버까지 가서 400을 받지 않는다.
            from src.uploaders import naver_categories as _ncat
            _ch = _ncat.hold({**product, 'naver_category_id': product.get('category_id')}, account=self.account or '')
            if _ch:
                return {'success': False, 'held': True, 'sku': product.get('sku', ''),
                        'reason_code': _ch['code'], 'error': _ch['line'],
                        'action_url': _ncat.picker_url(str(product.get('item_id') or ''))}
            path = '/v2/products'
            result = self._api_request('POST', path, data=payload)
            if 'error' in result:
                # Y7-B: 400 + `invalidInputs` — 다시 해도 같은 답이다. 「잠시 뒤 다시 시도」 대신 필드별 조치로.
                from src.uploaders import naver_invalid as _ni
                inv = _ni.rows(result.get('body') or '', str(product.get('item_id') or '')) \
                    if result.get('http_status') == 400 else []
                if inv:
                    act = _ni.first_action(inv)
                    return {'success': False, 'sku': product.get('sku', ''), 'reason_code': 'naver_invalid_input',
                            'error': '네이버가 입력값을 거부했어요 — ' + ' · '.join(r['line'] for r in inv),
                            'error_lines': [r['line'] for r in inv], 'raw': result['error'],
                            'action_url': act['url'], 'action_label': act['label']}
                return {'success': False, 'error': result['error'], 'sku': product.get('sku', '')}
            product_id = str(result.get('originProductNo', ''))
            # M6: 구매자 화면 주소는 **채널 상품번호**다(원상품번호와 다른 번호 — 식별자 오용 지뢰). 없으면 비운다.
            channel_no = str(result.get('smartstoreChannelProductNo') or '')
            url = f'https://smartstore.naver.com/main/products/{channel_no}' if channel_no else ''
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

    def count_products(self, statuses=None):
        """U0b — 스토어 등록 한도(판매중·판매대기·품절 합계 1,000) 확인용 상품 수. 못 세면 None.

        `POST /v1/products/search` `productStatusTypes`(볼트 「네이버 커머스 API 지뢰」: 이 필터는 동작한다) ·
        `size=1`로 `totalElements`만 읽는다. 응답에 그 칸이 없으면 None(지어내지 않음).
        """
        body = {'productStatusTypes': list(statuses or ['SALE', 'WAIT', 'OUTOFSTOCK']), 'page': 1, 'size': 1}
        res = self._api_request('POST', '/v1/products/search', data=body)
        self.count_error = ''
        if not isinstance(res, dict) or 'error' in res:
            self.count_error = str((res or {}).get('error') if isinstance(res, dict) else res)[:200]
            logger.warning('[스스 한도] %s 상품 수 조회 실패: %s', self.account, (res or {}).get('error') if isinstance(res, dict) else res)
            return None
        n = res.get('totalElements')
        if n is None:
            self.count_error = f'응답에 totalElements 없음: {str(res)[:160]}'
        try:
            return int(n) if n is not None else None
        except (TypeError, ValueError):
            return None

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
        # Y7-B: 오너가 지정한 네이버 리프만 싣는다(없으면 비워 두고 `_compose_payload`가 정본 사전 매칭).
        category_id = str(collected.get('naver_category_id') or '').strip()
        images = (collected.get('images') or [])[:10]
        return {
            'sku': collected.get('sku', ''),
            'title': title,
            'description_html': collected.get('description_html', ''),
            'price': price,
            'original_price': collected.get('price_krw', price),
            'images': images,
            'category_id': category_id,
            'item_id': str(collected.get('item_id') or ''),
            'brand': collected.get('brand', ''),
            'weight_kg': collected.get('weight_kg'),
            'stock': 999,
            'options': collected.get('options', {}),
            # Y7 — 조합형 옵션 재료(SKU·SKU별 판매가·옵션 한국어 사슬 재료). 여기서 떨어지면 옵션이 조용히 단일로 간다.
            'skus': collected.get('skus') or [],
            '_values_ko': collected.get('_values_ko') or {},
            'option_value_overrides': collected.get('option_value_overrides') or {},
            '_names_ko': collected.get('_names_ko') or {},
            'option_name_overrides': collected.get('option_name_overrides') or {},
            'tags': collected.get('tags', []),
            'min_purchase_quantity': collected.get('min_purchase_quantity') or 0,     # Y7-F: 셀러가 2 이상으로 정했을 때만 실림
            'detail_images': [u for u in (collected.get('detail_images') or []) if isinstance(u, str)],
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
        # Y7: 조합형을 실을 때는 같이 못 쓰는 단독형·표준형 칸(템플릿의 빈 목록)을 뺀다 — 빈 칸이라도 섞어 보내지 않는다.
        oi = merged.get('originProduct', {}).get('detailAttribute', {}).get('optionInfo')
        if isinstance(oi, dict) and oi.get('optionCombinations'):
            for k in ('optionSimple', 'simpleOptionSortType', 'standardOptionGroups', 'optionStandards'):
                if not oi.get(k) or k == 'simpleOptionSortType':
                    oi.pop(k, None)
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
        stock = self.STOCK_QUANTITY
        opt = product.get('_option_plan') or {}
        option_info = None
        if opt.get('mode') == 'combo':
            # Y7: 판매가 = 가장 싼 조합, 조합별 price = 그 위 추가금. 상품 재고 = 조합 재고 합.
            price, stock, option_info = int(opt['sale_price']), int(opt['stock']), opt['option_info']
        payload = {
            'originProduct': {
                'statusType': self.STATUS_TYPE,
                'saleType': 'NEW',
                # 명시 카테고리 없으면 사전 매칭, 그래도 없으면 빈칸(등록 전 `hold`가 보류 — 기본 리프 없음).
                'leafCategoryId': (str(product.get('category_id') or '').strip()
                                   or self.resolve_category(product.get('title'))),
                'name': (product.get('title') or '')[:100],
                'detailContent': product.get('description_html', ''),
                'images': {'representativeImage': {'url': rep}, 'optionalImages': optional},
                'salePrice': price,
                'stockQuantity': stock,
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
                # ★ 실측 유출 지점(카나리 9차 준비): 템플릿의 channelProductName이 남의 상품명이었다.
                #   `originProduct.name`과 **같은 소스**로 덮는다 — 스토어 노출명이 상품명과 어긋나면 안 된다.
                'channelProductName': (product.get('title') or '')[:100],
                'channelProductDisplayStatusType': 'ON',
                'naverShoppingRegistration': self.NAVER_SHOPPING_REGISTRATION,
            },
        }
        if option_info:
            payload['originProduct']['detailAttribute']['optionInfo'] = option_info
        # Y7-F(오너 2026-10-09): 구매수량 칸은 **기본으로 보내지 않는다** — 13:32 KST 400 `minPurchaseQuantity NumberMin`
        #   「최소구매수량 항목은 2개 이상」(예전엔 1을 늘 실었다 · `maxPurchaseQuantityPer1Time`은 문서에 없는 이름이었다).
        #   셀러가 최소수량을 2 이상으로 정한 경우에만 그 값 하나를 싣는다.
        mq = self.min_purchase_quantity(product)
        if mq:
            payload['originProduct']['detailAttribute']['purchaseQuantityInfo'] = {'minPurchaseQuantity': mq}
        return payload

    @staticmethod
    def min_purchase_quantity(product: dict) -> int:
        """셀러가 정한 최소구매수량(2 이상일 때만) — 아니면 0(칸을 보내지 않음). 네이버 문서 상한 10,000."""
        try:
            v = int(str((product or {}).get('min_purchase_quantity') or '').strip())
        except ValueError:
            return 0
        return min(v, 10000) if v >= 2 else 0

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

    _IMG_SRC_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*>', re.I)

    def _detail_to_cdn(self, html_body: str, sku: str = '') -> str:
        """상세 본문 `<img src>` → 네이버 CDN 주소. 이미 네이버(pstatic) 주소면 그대로. 못 올린 장의 `<img>`는 뺀다(외부 주소를 보내지 않음)."""
        import html as _h
        srcs = []
        for m in self._IMG_SRC_RE.finditer(html_body or ''):
            u = _h.unescape(m.group(1))
            if u.startswith(('http://', 'https://')) and 'pstatic.net' not in u and u not in srcs:
                srcs.append(u)
        if not srcs:
            return html_body
        mapping = {}
        for i in range(0, len(srcs), self.IMAGE_MAX_COUNT):
            chunk = srcs[i:i + self.IMAGE_MAX_COUNT]
            shot = self.upload_images(chunk)
            if not shot.get('ok'):
                logger.warning('상세 이미지 업로드 실패 sku=%s — %s', sku, shot.get('reason'))
                continue
            skipped = {str(x.get('url') or '') for x in shot.get('skipped') or []}
            kept = [u for u in chunk if (self.normalize_source_url(u) or u) not in skipped and u not in skipped]
            if len(kept) == len(shot.get('urls') or []):
                mapping.update(dict(zip(kept, shot['urls'])))
            else:                                       # 짝을 못 맞추면 짐작하지 않는다 — 그 묶음은 빠진다
                logger.warning('상세 이미지 짝 불일치 sku=%s — 보냄 %d · 받음 %d', sku, len(kept), len(shot.get('urls') or []))

        def _swap(m):
            u = _h.unescape(m.group(1))
            if 'pstatic.net' in u or not u.startswith(('http://', 'https://')):
                return m.group(0)
            if u in mapping:
                return m.group(0).replace(m.group(1), _h.escape(mapping[u], quote=True))
            return ''                                   # 못 올린 장 — 본문에서 뺀다
        return self._IMG_SRC_RE.sub(_swap, html_body)

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
        from src.utils.http_timeouts import allow as _http_allow
        for att in range(self.IMAGE_RETRY):
            try:
                # Z8: 외부 호출 read 상한은 15s — 사진 최대 10장 한 요청은 예외(60s, 이 호출만)
                with _http_allow(read=60, why='네이버 이미지 업로드(최대 10장)'):
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
    #   `_resp_body`/`_fail_detail`은 **`BaseUploader`가 단일 소스**(쿠팡과 공유).
    #   여기서 재구현하지 않는다 — 같은 규칙을 두 곳에 두면 한쪽만 고쳐진다(이 세션 4례).
    #: Y7-B — 400 `invalidInputs[].name`별 조치 문구. Y7-F: 표는 `naver_invalid.FIELDS` 한 곳(여기는 그 사본 — 옛 이름 호환).
    from src.uploaders.naver_invalid import FIELDS as _NI_FIELDS
    INVALID_INPUT_ACTIONS = {k: v[0] for k, v in _NI_FIELDS.items()}
    del _NI_FIELDS

    @classmethod
    def invalid_input_lines(cls, body: str) -> list:
        """400 본문 → `[(필드명, 조치 한 줄)]`. `invalidInputs`가 없으면 빈 목록(매퍼 `naver_invalid` 한 곳)."""
        from src.uploaders.naver_invalid import rows
        return [(r["name"], r["line"]) for r in rows(body)]

    _WORD_SPLIT = re.compile(r"[^0-9A-Za-z\uac00-\ud7a3]+")

    @classmethod
    def _token_hit(cls, token: str, name: str, words: list) -> bool:
        """사전 낱말 하나가 상품명에 걸리나 — 두 글자 이상은 포함, 한 글자는 낱말 전체이거나 끝 글자일 때만."""
        if len(token) == 1:
            return any(w == token or w.endswith(token) for w in words)
        return token.lower() in name.lower()

    @classmethod
    def match_details(cls, title: str) -> dict:
        """사전 판정 근거 `{leaf, token, row, hits}` — 못 정하면 leaf 빈칸. 위 규칙(가장 긴 낱말 → 적중 수 → 위 줄)."""
        name = str(title or '')
        words = [w for w in cls._WORD_SPLIT.split(name) if w]
        best = None
        for row, (pattern, leaf) in enumerate(cls.CATEGORY_PATTERNS):
            hits = [t for t in pattern.split('|') if t and cls._token_hit(t, name, words)]
            if not hits:
                continue
            key = (max(len(t) for t in hits), len(hits), -row)
            if best is None or key > best[0]:
                best = (key, {'leaf': leaf, 'token': max(hits, key=len), 'row': row + 1, 'hits': hits})
        return best[1] if best else {'leaf': '', 'token': '', 'row': 0, 'hits': []}

    @classmethod
    def match_category(cls, title: str) -> str:
        """사전 매칭만 — 매칭이 없으면 빈 문자열(기본 리프로 채우지 않는다, Y7-B 가드용)."""
        return cls.match_details(title)['leaf']

    @classmethod
    def resolve_category(cls, title: str) -> str:
        """상품명 → 리프 카테고리 ID(사전 매칭만). 미매칭이면 빈칸 — 기본 리프로 채우지 않는다.

        정본은 미매칭을 기본 리프(50004132)로 등록했지만 그 ID는 운영 트리에서 「보드게임」이다(Y7-D 결정 2).
        빈칸이면 등록 전에 `naver_categories.hold`가 보류(`category_unset`)로 막는다.
        """
        return cls.match_category(title)

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
            return f'{prefix}_CLIENT_ID/{prefix}_CLIENT_SECRET'
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
                    # Y7-B: 상태·본문을 따로 싣는다 — 400 `invalidInputs`는 필드별 조치로 바꿔 보여 준다.
                    # Y7-F: 본문은 **자르지 않고** 싣는다 — 300자에서 잘라 `invalidInputs` 2개짜리 JSON을 못 읽었다(13:32 KST).
                    return {'error': f'네이버 거부 — {last}', 'http_status': resp.status_code,
                            'body': self._resp_body(resp, limit=20000)}
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
