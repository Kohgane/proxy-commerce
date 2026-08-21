import base64
import hashlib
import hmac
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

WOO_WEBHOOK_SECRET = os.getenv('WOO_WEBHOOK_SECRET', '')
WOO_API_VERSION = os.getenv('WOO_API_VERSION', 'wc/v3')


def _woo_base() -> str:
    """WooCommerce 스토어 base URL을 호출 시점에 읽고 정규화한다.

    - `WC_URL`(인앱 셀러 자격증명) / `WOO_BASE_URL`(레거시) 둘 다 지원.
    - scheme 없으면 https:// 보정 → `https:///...` 빈 호스트 오류 방지.
    - 모듈 import 시점이 아닌 호출 시점에 읽어 seller_market_env 주입을 반영.
    """
    raw = (os.getenv('WC_URL') or os.getenv('WOO_BASE_URL') or '').strip()
    if not raw:
        return ''
    if not raw.startswith(('http://', 'https://')):
        raw = 'https://' + raw
    return raw.rstrip('/')


def _woo_ck() -> str:
    """Consumer Key — WOO_CK/WC_KEY 둘 다 지원, 호출 시점에 읽음."""
    return os.getenv('WOO_CK') or os.getenv('WC_KEY') or ''


def _woo_cs() -> str:
    """Consumer Secret — WOO_CS/WC_SECRET 둘 다 지원, 호출 시점에 읽음."""
    return os.getenv('WOO_CS') or os.getenv('WC_SECRET') or ''


def _woo_endpoint(resource: str = '') -> str:
    """WooCommerce REST 엔드포인트 절대 URL. base 미설정 시 정직하게 실패."""
    base = _woo_base()
    if not base:
        raise RuntimeError(
            "WooCommerce 스토어 URL이 설정되지 않았습니다 "
            "(WC_URL 또는 WOO_BASE_URL). 마켓 연결(키 설정)에서 사이트 URL을 입력하세요."
        )
    suffix = f"/{resource.lstrip('/')}" if resource else ""
    return f"{base}/wp-json/{WOO_API_VERSION}{suffix}"

# WooCommerce 카테고리 매핑 (slug 기반)
WOO_CATEGORY_MAP = {
    'bag': {'name': '가방', 'slug': 'bag'},
    'wallet': {'name': '지갑', 'slug': 'wallet'},
    'perfume': {'name': '향수', 'slug': 'perfume'},
    'pouch': {'name': '파우치', 'slug': 'pouch'},
    'accessory': {'name': '액세서리', 'slug': 'accessory'},
}

# 국가 코드 → 원산지명 매핑
_ORIGIN_MAP = {'JP': '일본', 'FR': '프랑스', 'US': '미국', 'KR': '한국'}


def _auth_params():
    # v61: 하위호환용(테스트/구 호출). 실제 요청은 Basic Auth 헤더(_request_with_retry) 경로.
    return {"consumer_key": _woo_ck(), "consumer_secret": _woo_cs()}


# v61 STEP1: Bluehost ModSecurity 회피 — 봇 UA 대신 일반 브라우저형 UA + Accept.
_WOO_UA = os.getenv(
    "WOO_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
)
_WOO_HEADERS = {"User-Agent": _WOO_UA, "Accept": "application/json"}


def _clean_params(extra_params):
    """v61 STEP1: 빈 값 파라미터(특히 sku=) 제거 — WooCommerce가 빈 sku=로 406/오작동."""
    return {k: v for k, v in (extra_params or {}).items()
            if v is not None and str(v).strip() != ""}


def _request_with_retry(method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
    """WooCommerce API 요청 + 지수 백오프 재시도.

    v61 STEP1(406 수리): 자격증명을 쿼리스트링 → **HTTP Basic Auth 헤더**(HTTPS 표준 경로)로,
    일반 브라우저형 User-Agent(Bluehost ModSecurity 회피), 빈 sku= 파라미터 제거.
    실패 시 응답 본문 요약을 **마스킹 후** 진단 로그에(자격증명 평문 0).
    """
    from src.utils.secret_mask import mask_text, mask_url
    extra_params = _clean_params(kwargs.pop('params', {}))
    headers = {**_WOO_HEADERS, **(kwargs.pop('headers', {}) or {})}
    ck, cs = _woo_ck(), _woo_cs()
    auth = (ck, cs) if (ck and cs) else None
    _masked_url = mask_url(url)

    for attempt in range(max_retries):
        try:
            from src.market_throttle import pace
            pace("woocommerce")   # v45: 큐 페이싱(자체 429 재시도는 아래 유지)
            r = requests.request(method, url, params=extra_params, headers=headers,
                                 auth=auth, timeout=30, **kwargs)
            if r.status_code == 429:
                retry_after = float(r.headers.get('Retry-After', 2))
                logger.warning("WooCommerce rate limit hit, retrying after %ss", retry_after)
                time.sleep(retry_after)
                continue
            if r.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("WooCommerce server error %s (%s), retrying in %ss",
                               r.status_code, _masked_url, wait)
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                # v61 STEP1: 4xx는 원인 진단(마스킹된 본문 요약) — 동어반복·평문 금지.
                body = ""
                try:
                    body = mask_text(r.text[:400], secrets=[ck, cs])
                except Exception:
                    pass
                logger.warning("WooCommerce %s %s → 실패 요약: %s", r.status_code, _masked_url, body)
            r.raise_for_status()
            return r
        except requests.exceptions.ConnectionError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning("Connection error, retrying in %ss: %s", wait, mask_text(str(e), secrets=[ck, cs]))
            time.sleep(wait)
    raise RuntimeError("Max retries exceeded for WooCommerce API")


def get_or_create_category(category_slug: str) -> int:
    """
    WooCommerce 카테고리를 slug로 조회, 없으면 생성.
    카테고리 ID를 반환.
    """
    url = _woo_endpoint("products/categories")
    r = _request_with_retry('GET', url, params={'slug': category_slug})
    categories = r.json()

    if categories:
        return categories[0]['id']

    cat_info = WOO_CATEGORY_MAP.get(category_slug, {'name': category_slug, 'slug': category_slug})
    r = _request_with_retry('POST', url, json=cat_info)
    return r.json()['id']


def get_or_create_tag(tag_name: str) -> int:
    """
    WooCommerce 태그를 이름으로 조회, 없으면 생성.
    태그 ID를 반환.
    """
    url = _woo_endpoint("products/tags")
    r = _request_with_retry('GET', url, params={'search': tag_name})
    tags = r.json()

    for t in tags:
        if t['name'].lower() == tag_name.lower():
            return t['id']

    r = _request_with_retry('POST', url, json={'name': tag_name})
    return r.json()['id']


def _prepare_images(images_str: str) -> list:
    """
    카탈로그 images 필드(콤마 구분 URL) → WooCommerce images 배열 변환.
    """
    if not images_str:
        return []
    urls = [url.strip() for url in images_str.split(',') if url.strip()]
    return [{'src': url, 'position': i} for i, url in enumerate(urls)]


def _prepare_stock(stock_value, manage: bool = True) -> dict:
    """재고 관련 필드 생성."""
    return {
        'manage_stock': manage,
        'stock_quantity': int(stock_value) if stock_value else 0,
        'stock_status': 'instock' if int(stock_value or 0) > 0 else 'outofstock',
    }


def _generate_description(catalog_row: dict) -> str:
    """벤더별 WooCommerce 상품 설명 HTML 생성.

    v86-O: 셀러가 드로어에서 편집·꾸민 상세(블록→HTML 또는 원문 설명)가 있으면 그것을 본문으로
    쓰고(실반영), 없을 때만 기존 벤더 템플릿 헤더로 폴백. 배송·관부가세·교환반품 안내(컴플라이언스)는
    항상 하단에 유지.
    """
    vendor = catalog_row.get('vendor', '')
    source_country = catalog_row.get('source_country', '')

    origin = _ORIGIN_MAP.get(source_country, source_country)

    seller_body = str(catalog_row.get('description') or '').strip()
    if seller_body:
        head = seller_body
    else:
        head = (
            f"<h3>{catalog_row.get('title_ko', '')}</h3>\n"
            f"<p><strong>브랜드:</strong> {catalog_row.get('brand', '')}</p>\n"
            f"<p><strong>원산지:</strong> {origin}</p>"
        )

    html = f"""<div class="product-detail">
{head}
"""

    if vendor == 'PORTER':
        html += f"""<p><strong>시리즈:</strong> {catalog_row.get('category', '')}</p>
<div class="shipping-notice">
<h4>📦 배송 안내</h4>
<p>일본 직구 상품으로 배송기간은 영업일 기준 7-14일 소요됩니다.</p>
<p>젠마켓(Zenmarket) 배대지를 통해 배송됩니다.</p>
</div>
"""
    elif vendor == 'MEMO_PARIS':
        html += """<div class="shipping-notice">
<h4>📦 배송 안내</h4>
<p>프랑스 직구 상품으로 배송기간은 영업일 기준 10-18일 소요됩니다.</p>
</div>
"""

    html += """<div class="customs-notice">
<h4>🏛️ 관부가세 안내</h4>
<p>해외 직구 상품은 물품가 15만원 초과 시 관부가세가 부과될 수 있습니다.</p>
<p>관부가세는 수령인(구매자) 부담입니다.</p>
</div>
<div class="return-policy">
<h4>↩️ 교환/반품</h4>
<p>해외 배송 특성상 단순 변심에 의한 교환/반품은 어렵습니다.</p>
<p>상품 하자 시 사진 첨부하여 문의 부탁드립니다.</p>
</div>
</div>"""

    return html


def prepare_product_data(catalog_row: dict, sell_price_krw: float) -> dict:
    """
    카탈로그 표준 행 → WooCommerce 상품 데이터 변환.

    - title_ko → name
    - 카탈로그 category → WooCommerce categories
    - tags → WooCommerce tags
    - images → WooCommerce images
    - 재고/배송 정보 포함
    """
    category = catalog_row.get('category', '')
    tags_str = catalog_row.get('tags', '')
    images_str = catalog_row.get('images', '')
    source_country = catalog_row.get('source_country', '')

    origin = _ORIGIN_MAP.get(source_country, source_country)

    product = {
        'name': catalog_row.get('title_ko') or catalog_row.get('title_en', ''),
        'sku': catalog_row.get('sku', ''),
        'regular_price': str(int(sell_price_krw)),
        'description': _generate_description(catalog_row),
        'short_description': f"원산지: {origin} | 브랜드: {catalog_row.get('brand', '')}",
        'images': _prepare_images(images_str),
        'manage_stock': True,
        'stock_quantity': int(catalog_row.get('stock', 0)),
        'stock_status': 'instock' if int(catalog_row.get('stock', 0)) > 0 else 'outofstock',
        'shipping_class': 'overseas',
        'meta_data': [
            {'key': 'source_country', 'value': source_country},
            {'key': 'original_price', 'value': str(catalog_row.get('buy_price', ''))},
            {'key': 'original_currency', 'value': catalog_row.get('buy_currency', '')},
            {'key': 'vendor', 'value': catalog_row.get('vendor', '')},
        ],
    }

    if category:
        try:
            cat_id = get_or_create_category(category)
            product['categories'] = [{'id': cat_id}]
        except Exception as e:
            logger.warning("Failed to map category '%s': %s", category, e)

    if tags_str:
        tag_ids = []
        for tag in tags_str.split(','):
            tag = tag.strip()
            if tag:
                try:
                    tag_ids.append({'id': get_or_create_tag(tag)})
                except Exception as e:
                    logger.warning("Failed to create tag '%s': %s", tag, e)
        if tag_ids:
            product['tags'] = tag_ids

    # v88-C 파일럿 카나리: status(draft) + 파일럿 메타(비노출 _-prefix) 지원. 미지정이면 기존 동작(publish) 불변.
    _status = str(catalog_row.get('status') or '').strip().lower()
    if _status in ('draft', 'pending', 'private', 'publish'):
        product['status'] = _status
    for _m in (catalog_row.get('extra_meta') or []):
        if isinstance(_m, dict) and _m.get('key'):
            product['meta_data'].append({'key': str(_m['key']), 'value': str(_m.get('value', ''))})

    # v88-C: 무재고 구매대행 — manage_stock/stock_status 명시 오버라이드(미지정이면 기존 동작 불변).
    if catalog_row.get('manage_stock') is not None:
        product['manage_stock'] = bool(catalog_row.get('manage_stock'))
        if product['manage_stock'] is False:
            product.pop('stock_quantity', None)       # 재고관리 off면 수량 불필요
    _ss = str(catalog_row.get('stock_status') or '').strip().lower()
    if _ss in ('instock', 'outofstock', 'onbackorder'):
        product['stock_status'] = _ss

    return product


def list_products_by_status(status: str = 'draft', per_page: int = 100) -> list:
    """상태별 상품 목록(백필 매칭용). meta_data 포함. 페이지네이션(넉넉히 5페이지)."""
    out, url = [], _woo_endpoint("products")
    for page in range(1, 6):
        r = _request_with_retry('GET', url, params={'status': status, 'per_page': per_page, 'page': page})
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        if len(rows) < per_page:
            break
    return out


def update_product(product_id, patch: dict) -> bool:
    """상품 부분 업데이트(백필 — 재등록 아님). 성공 시 True."""
    if not product_id or not isinstance(patch, dict) or not patch:
        return False
    url = _woo_endpoint(f"products/{product_id}")
    r = _request_with_retry('PUT', url, json=patch)
    return bool(isinstance(r.json(), dict) and r.json().get('id'))


def verify_woo_webhook(payload: bytes, signature: str) -> bool:
    """
    WooCommerce 웹훅 서명 검증.
    WooCommerce는 X-WC-Webhook-Signature 헤더에 HMAC-SHA256 서명을 포함.
    """
    if not WOO_WEBHOOK_SECRET:
        logger.warning("WOO_WEBHOOK_SECRET not set — webhook verification skipped")
        return True

    digest = hmac.new(
        WOO_WEBHOOK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256,
    ).digest()
    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, signature)


def get_store_info() -> dict:
    """WooCommerce 스토어 정보 조회 (연결 테스트용)."""
    url = _woo_endpoint()
    r = _request_with_retry('GET', url)
    return r.json()


def _find_by_sku(sku: str):
    # v61 STEP1: 빈 sku로 조회하면 전체 목록의 첫 상품을 오매칭 → 빈 sku면 조회 안 함(신규 등록).
    if not (sku or "").strip():
        return None
    url = _woo_endpoint("products")
    r = _request_with_retry('GET', url, params={'sku': sku})
    lst = r.json()
    return lst[0] if isinstance(lst, list) and lst else None


def upsert_product(prod: dict):
    """상품 등록 또는 갱신. 기존 시그니처 하위호환 유지."""
    sku = prod.get('sku') or ''
    found = _find_by_sku(sku)
    if found:
        pid = found['id']
        logger.info("WooCommerce 상품 갱신: SKU=%s, ID=%s", sku, pid)
        u = _request_with_retry('PUT', _woo_endpoint(f"products/{pid}"), json=prod)
        return u.json()
    else:
        logger.info("WooCommerce 상품 신규 등록: SKU=%s", sku)
        c = _request_with_retry('POST', _woo_endpoint("products"), json=prod)
        return c.json()


def upsert_batch(products: list, batch_size: int = 10) -> dict:
    """
    WooCommerce Batch API 활용한 대량 상품 처리.
    /products/batch 엔드포인트 사용.
    """
    url = _woo_endpoint("products/batch")
    results = {'created': 0, 'updated': 0, 'errors': []}

    for i in range(0, len(products), batch_size):
        batch = products[i:i + batch_size]

        create_items = []
        update_items = []

        for prod in batch:
            sku = prod.get('sku', '')
            existing = _find_by_sku(sku)
            if existing:
                prod['id'] = existing['id']
                update_items.append(prod)
            else:
                create_items.append(prod)

        payload = {}
        if create_items:
            payload['create'] = create_items
        if update_items:
            payload['update'] = update_items

        if payload:
            try:
                r = _request_with_retry('POST', url, json=payload)
                data = r.json()
                results['created'] += len(data.get('create', []))
                results['updated'] += len(data.get('update', []))
            except Exception as e:
                logger.error("Batch upsert error: %s", e)
                results['errors'].append(str(e))

    return results
