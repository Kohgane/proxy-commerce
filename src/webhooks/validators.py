"""src/webhooks/validators.py — 웹훅 요청 유효성 검사기.

플랫폼별 HMAC 서명 또는 토큰 검증을 수행한다.

환경변수:
  TELEGRAM_BOT_TOKEN  — Telegram 봇 토큰
"""

import base64
import hashlib
import hmac
import logging
import os
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class WebhookValidator:
    """웹훅 요청 유효성 검사기."""

    def validate(self, platform: str, request_data: Dict) -> Tuple[bool, str]:
        """플랫폼별 웹훅 요청을 검증한다.

        Args:
            platform: 플랫폼 이름 ("shopify", "woocommerce", "telegram").
            request_data: {"headers": dict, "body": bytes, "secret": str} 딕셔너리.

        Returns:
            (유효 여부: bool, 오류 메시지: str) 튜플.
            유효하면 (True, ""), 무효하면 (False, "오류 메시지").
        """
        validators = {
            "shopify": self._validate_shopify,
            "woocommerce": self._validate_woocommerce,
            "telegram": self._validate_telegram,
        }
        validator = validators.get(platform)
        if validator is None:
            return False, f"지원하지 않는 플랫폼: {platform}"
        return validator(request_data)

    def _validate_shopify(self, request_data: Dict) -> Tuple[bool, str]:
        """Shopify HMAC-SHA256 서명을 검증한다."""
        headers = request_data.get("headers", {})
        body = request_data.get("body", b"")
        secret = request_data.get("secret", "")

        if not secret:
            return False, "Shopify 시크릿 누락"

        provided_signature = headers.get("X-Shopify-Hmac-Sha256", "")
        if not provided_signature:
            return False, "X-Shopify-Hmac-Sha256 헤더 누락"

        if isinstance(body, str):
            body = body.encode("utf-8")
        if isinstance(secret, str):
            secret = secret.encode("utf-8")

        # 다이제스트를 한 번만 계산하여 hex와 base64 두 가지 형태로 비교
        digest = hmac.new(secret, body, hashlib.sha256).digest()
        expected = digest.hex()
        expected_b64 = base64.b64encode(digest).decode()

        if hmac.compare_digest(expected, provided_signature) or \
                hmac.compare_digest(expected_b64, provided_signature):
            return True, ""
        return False, "Shopify HMAC 서명 불일치"

    def _validate_woocommerce(self, request_data: Dict) -> Tuple[bool, str]:
        """WooCommerce HMAC-SHA256 서명을 검증한다."""
        headers = request_data.get("headers", {})
        body = request_data.get("body", b"")
        secret = request_data.get("secret", "")

        if not secret:
            return False, "WooCommerce 시크릿 누락"

        provided_signature = headers.get("X-WC-Webhook-Signature", "")
        if not provided_signature:
            return False, "X-WC-Webhook-Signature 헤더 누락"

        if isinstance(body, str):
            body = body.encode("utf-8")
        if isinstance(secret, str):
            secret = secret.encode("utf-8")

        expected = base64.b64encode(
            hmac.new(secret, body, hashlib.sha256).digest()
        ).decode()

        if hmac.compare_digest(expected, provided_signature):
            return True, ""
        return False, "WooCommerce HMAC 서명 불일치"

    def _validate_telegram(self, request_data: Dict) -> Tuple[bool, str]:
        """Telegram 봇 토큰을 검증한다."""
        provided_token = request_data.get("token", "")
        expected_token = os.getenv("TELEGRAM_BOT_TOKEN", "")

        if not expected_token:
            return False, "TELEGRAM_BOT_TOKEN 환경변수 누락"
        if not provided_token:
            return False, "token 필드 누락"

        if hmac.compare_digest(str(provided_token), str(expected_token)):
            return True, ""
        return False, "Telegram 토큰 불일치"
