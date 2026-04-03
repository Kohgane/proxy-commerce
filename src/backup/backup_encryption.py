"""src/backup/backup_encryption.py — 백업 무결성 검증 (HMAC-SHA256)."""
from __future__ import annotations

import hashlib
import hmac
import json


_DEFAULT_KEY = b"proxy-commerce-backup-key"


class BackupEncryption:
    """HMAC-SHA256 서명/검증으로 백업 무결성 보장."""

    def __init__(self, key: bytes = _DEFAULT_KEY) -> None:
        self._key = key

    def sign(self, data: str) -> dict:
        """데이터에 HMAC 서명 추가."""
        sig = hmac.new(self._key, data.encode(), hashlib.sha256).hexdigest()
        return {"data": data, "signature": sig}

    def verify(self, signed: dict) -> bool:
        """서명 검증."""
        data = signed.get("data", "")
        expected = hmac.new(self._key, data.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signed.get("signature", ""))

    def sign_dict(self, payload: dict) -> dict:
        data_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return self.sign(data_str)

    def verify_dict(self, signed: dict) -> bool:
        return self.verify(signed)
