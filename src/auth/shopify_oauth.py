"""
Shopify OAuth 유틸리티.
현재는 HMAC 검증 + 토큰 유효성 확인만 지원.
향후 OAuth 토큰 갱신 등 확장 가능.
"""

import os
import hmac
import hashlib
import logging
import requests
from urllib.parse import parse_qs, urlencode

logger = logging.getLogger(__name__)

SHOP = os.getenv('SHOPIFY_SHOP')
TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')
CLIENT_SECRET = os.getenv('SHOPIFY_CLIENT_SECRET')
API_VERSION = os.getenv('SHOPIFY_API_VERSION', '2024-07')


def verify_request_hmac(query_string: str) -> bool:
    """
    Shopify OAuth 리다이렉트 요청의 HMAC 검증.
    설치/인증 콜백에서 사용.

    Args:
        query_string: URL 쿼리 문자열 (예: "code=xxx&hmac=yyy&shop=zzz")

    Returns:
        True if valid, False otherwise
    """
    if not CLIENT_SECRET:
        logger.warning("SHOPIFY_CLIENT_SECRET not set")
        return False

    params = parse_qs(query_string, keep_blank_values=True)
    hmac_value = params.pop('hmac', [None])[0]
    if not hmac_value:
        return False

    # 파라미터를 key=value 형태로 정렬하여 문자열 생성
    sorted_params = urlencode(sorted(
        (k, v[0]) for k, v in params.items()
    ))

    digest = hmac.new(
        CLIENT_SECRET.encode('utf-8'),
        sorted_params.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(digest, hmac_value)


def validate_access_token() -> bool:
    """
    현재 SHOPIFY_ACCESS_TOKEN이 유효한지 확인.
    Shopify Admin API /shop.json에 간단한 GET 요청으로 테스트.
    """
    if not SHOP or not TOKEN:
        logger.error("SHOPIFY_SHOP or SHOPIFY_ACCESS_TOKEN not set")
        return False

    try:
        url = f"https://{SHOP}/admin/api/{API_VERSION}/shop.json"
        headers = {"X-Shopify-Access-Token": TOKEN}
        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code == 200:
            logger.info("Shopify token valid for shop: %s", r.json().get('shop', {}).get('name'))
            return True
        elif r.status_code == 401:
            logger.error("Shopify access token is invalid or expired")
            return False
        else:
            logger.warning("Unexpected status %s validating Shopify token", r.status_code)
            return False
    except requests.exceptions.RequestException as e:
        logger.error("Failed to validate Shopify token: %s", e)
        return False


def get_scopes() -> list:
    """현재 액세스 토큰의 권한 스코프 조회."""
    if not SHOP or not TOKEN:
        return []

    try:
        url = f"https://{SHOP}/admin/oauth/access_scopes.json"
        headers = {"X-Shopify-Access-Token": TOKEN}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()

        scopes = r.json().get('access_scopes', [])
        return [s['handle'] for s in scopes]
    except Exception as e:
        logger.error("Failed to get scopes: %s", e)
        return []
