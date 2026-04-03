"""src/webhook_manager/webhook_signer.py — HMAC-SHA256 서명."""
from __future__ import annotations

import hashlib
import hmac
import json
import time


class WebhookSigner:
    """HMAC-SHA256 서명으로 페이로드 무결성 보장."""

    def sign(self, payload: dict, secret: str, timestamp: int = None) -> dict:
        """페이로드 서명 생성.

        Returns:
            {signature, timestamp, payload_bytes}
        """
        ts = timestamp or int(time.time())
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        signed_content = f"{ts}.{body}"
        sig = hmac.new(
            secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "signature": f"sha256={sig}",
            "timestamp": ts,
            "body": body,
        }

    def verify(self, payload_body: str, signature: str, secret: str,
               timestamp: int = None, tolerance: int = 300) -> bool:
        """서명 검증. tolerance는 초 단위 시간 허용 오차."""
        if not signature.startswith("sha256="):
            return False
        if timestamp is not None:
            now = int(time.time())
            if abs(now - timestamp) > tolerance:
                return False
        ts_prefix = f"{timestamp}." if timestamp else ""
        signed_content = f"{ts_prefix}{payload_body}"
        expected = hmac.new(
            secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
