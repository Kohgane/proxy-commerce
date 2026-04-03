"""src/webhook_manager/webhook_signer.py — 웹훅 서명."""
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


class WebhookSigner:
    """HMAC-SHA256 웹훅 서명 및 검증."""

    def sign(self, payload_bytes: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    def verify(self, payload_bytes: bytes, signature: str, secret: str) -> bool:
        expected = self.sign(payload_bytes, secret)
        return hmac.compare_digest(expected, signature)
