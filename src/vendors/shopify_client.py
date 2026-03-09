import os
import time
import hmac
import hashlib
import base64
import logging
import requests

logger = logging.getLogger(__name__)

SHOP = os.getenv('SHOPIFY_SHOP')
TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')
CLIENT_SECRET = os.getenv('SHOPIFY_CLIENT_SECRET')
API_VERSION = os.getenv('SHOPIFY_API_VERSION', '2024-07')
API = f"https://{SHOP}/admin/api/{API_VERSION}"
GRAPHQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"


def _headers():
    return {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}


def verify_webhook(data: bytes, hmac_header: str) -> bool:
    """
    Shopify 웹훅 HMAC-SHA256 서명 검증.

    Shopify는 웹훅 전송 시 X-Shopify-Hmac-Sha256 헤더에
    CLIENT_SECRET으로 서명한 HMAC을 포함합니다.

    Args:
        data: 웹훅 요청 바디 (raw bytes)
        hmac_header: X-Shopify-Hmac-Sha256 헤더 값

    Returns:
        True if valid, False otherwise
    """
    if not CLIENT_SECRET:
        logger.warning("SHOPIFY_CLIENT_SECRET not set — webhook verification skipped")
        return True  # graceful degradation

    digest = hmac.new(
        CLIENT_SECRET.encode('utf-8'),
        data,
        hashlib.sha256,
    ).digest()
    computed = base64.b64encode(digest).decode()

    return hmac.compare_digest(computed, hmac_header)


def _request_with_retry(method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
    """
    Shopify API 요청 + 지수 백오프 재시도.
    Rate limit (429) 처리 포함.
    """
    for attempt in range(max_retries):
        # Merge caller-supplied headers (if any) on top of default auth headers
        merged_headers = {**_headers(), **kwargs.pop('headers', {})}
        try:
            r = requests.request(method, url, headers=merged_headers, timeout=30, **kwargs)
            if r.status_code == 429:
                retry_after = float(r.headers.get('Retry-After', 2))
                logger.warning("Shopify rate limit hit, retrying after %ss", retry_after)
                time.sleep(retry_after)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.ConnectionError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning("Connection error, retrying in %ss: %s", wait, e)
            time.sleep(wait)
    raise RuntimeError("Max retries exceeded")


def graphql_query(query: str, variables: dict = None) -> dict:
    """
    Shopify Admin GraphQL API 호출.
    Shopify Markets (다중통화) 등 고급 기능에 사용.
    """
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    r = _request_with_retry('POST', GRAPHQL_URL, json=payload)
    data = r.json()

    if 'errors' in data:
        logger.error("GraphQL errors: %s", data['errors'])
        raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")

    return data.get('data', {})


def _find_by_sku_graphql(sku: str):
    """GraphQL로 SKU 직접 검색 (효율적)."""
    # Strip characters that could interfere with Shopify's search query syntax
    safe_sku = sku.replace('"', '').replace("'", '').replace('\n', '').replace('\r', '').strip()
    query = """
    query findProductBySku($query: String!) {
      products(first: 1, query: $query) {
        edges {
          node {
            id
            legacyResourceId
            variants(first: 10) {
              edges {
                node {
                  sku
                }
              }
            }
          }
        }
      }
    }
    """
    data = graphql_query(query, variables={"query": f"sku:{safe_sku}"})
    edges = data.get('products', {}).get('edges', [])
    if edges:
        node = edges[0]['node']
        return {'id': int(node['legacyResourceId'])}
    return None


def _find_by_sku(sku: str):
    """SKU로 상품 검색. GraphQL 우선, 실패 시 REST 폴백."""
    try:
        return _find_by_sku_graphql(sku)
    except Exception as e:
        logger.warning("GraphQL SKU lookup failed, falling back to REST: %s", e)

    # REST 폴백: 전체 상품 조회 후 필터링
    r = _request_with_retry('GET', f"{API}/products.json?limit=250")
    for p in r.json().get('products', []):
        for v in p.get('variants', []):
            if v.get('sku') == sku:
                return p
    return None


def get_shop_info() -> dict:
    """현재 Shopify 스토어 정보 조회 (연결 테스트용)"""
    r = _request_with_retry('GET', f"{API}/shop.json")
    return r.json().get('shop', {})


def upsert_product(prod: dict):
    """상품 등록 또는 갱신. 기존 시그니처 하위호환 유지."""
    sku = prod['variants'][0]['sku']
    current = _find_by_sku(sku)
    if current:
        pid = current['id']
        logger.info("Shopify 상품 갱신: SKU=%s, ID=%s", sku, pid)
        u = _request_with_retry('PUT', f"{API}/products/{pid}.json", json={"product": prod})
        return u.json()['product']
    else:
        logger.info("Shopify 상품 신규 등록: SKU=%s", sku)
        c = _request_with_retry('POST', f"{API}/products.json", json={"product": prod})
        return c.json()['product']
