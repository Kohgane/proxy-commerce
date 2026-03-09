import base64
import hashlib
import hmac
import logging
import os
import time

import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

BASE = os.getenv('WOO_BASE_URL')
CK = os.getenv('WOO_CK')
CS = os.getenv('WOO_CS')
WOO_WEBHOOK_SECRET = os.getenv('WOO_WEBHOOK_SECRET', '')
WOO_API_VERSION = os.getenv('WOO_API_VERSION', 'wc/v3')

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
    return {"consumer_key": CK, "consumer_secret": CS}


def _request_with_retry(method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
    """
    WooCommerce API 요청 + 지수 백오프 재시도.
    Rate limit 및 서버 에러(5xx) 처리 포함.
    """
    extra_params = kwargs.pop('params', {})
    merged_params = {**_auth_params(), **extra_params}

    for attempt in range(max_retries):
        try:
            r = requests.request(method, url, params=merged_params, timeout=30, **kwargs)
            if r.status_code == 429:
                retry_after = float(r.headers.get('Retry-After', 2))
                logger.warning("WooCommerce rate limit hit, retrying after %ss", retry_after)
                time.sleep(retry_after)
                continue
            if r.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("WooCommerce server error %s, retrying in %ss", r.status_code, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.ConnectionError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning("Connection error, retrying in %ss: %s", wait, e)
            time.sleep(wait)
    raise RuntimeError("Max retries exceeded for WooCommerce API")


def get_or_create_category(category_slug: str) -> int:
    """
    WooCommerce 카테고리를 slug로 조회, 없으면 생성.
    카테고리 ID를 반환.
    """
    url = urljoin(BASE, f"/wp-json/{WOO_API_VERSION}/products/categories")
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
    url = urljoin(BASE, f"/wp-json/{WOO_API_VERSION}/products/tags")
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
    """벤더별 WooCommerce 상품 설명 HTML 생성."""
    vendor = catalog_row.get('vendor', '')
    source_country = catalog_row.get('source_country', '')

    origin = _ORIGIN_MAP.get(source_country, source_country)

    html = f"""<div class="product-detail">
<h3>{catalog_row.get('title_ko', '')}</h3>
<p><strong>브랜드:</strong> {catalog_row.get('brand', '')}</p>
<p><strong>원산지:</strong> {origin}</p>
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

    return product


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
    url = urljoin(BASE, f"/wp-json/{WOO_API_VERSION}")
    r = _request_with_retry('GET', url)
    return r.json()


def _find_by_sku(sku: str):
    url = urljoin(BASE, f"/wp-json/{WOO_API_VERSION}/products")
    r = _request_with_retry('GET', url, params={'sku': sku})
    lst = r.json()
    return lst[0] if lst else None


def upsert_product(prod: dict):
    """상품 등록 또는 갱신. 기존 시그니처 하위호환 유지."""
    sku = prod.get('sku') or ''
    found = _find_by_sku(sku)
    if found:
        pid = found['id']
        logger.info("WooCommerce 상품 갱신: SKU=%s, ID=%s", sku, pid)
        u = _request_with_retry('PUT', urljoin(BASE, f"/wp-json/{WOO_API_VERSION}/products/{pid}"), json=prod)
        return u.json()
    else:
        logger.info("WooCommerce 상품 신규 등록: SKU=%s", sku)
        c = _request_with_retry('POST', urljoin(BASE, f"/wp-json/{WOO_API_VERSION}/products"), json=prod)
        return c.json()


def upsert_batch(products: list, batch_size: int = 10) -> dict:
    """
    WooCommerce Batch API 활용한 대량 상품 처리.
    /products/batch 엔드포인트 사용.
    """
    url = urljoin(BASE, f"/wp-json/{WOO_API_VERSION}/products/batch")
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
