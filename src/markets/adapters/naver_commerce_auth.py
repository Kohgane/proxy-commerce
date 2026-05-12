"""Naver Commerce token issuance helper."""
from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, Optional

_TOKEN_CACHE: Dict[str, Any] = {}


def _api_base() -> str:
    return os.getenv("NAVER_COMMERCE_API_BASE", "https://api.commerce.naver.com/external").rstrip("/")


def _token_url() -> str:
    return f"{_api_base()}/v1/oauth2/token"


def _build_client_secret_sign(client_id: str, client_secret: str, timestamp_ms: str) -> str:
    import bcrypt

    password = f"{client_id}_{timestamp_ms}".encode("utf-8")
    hashed = bcrypt.hashpw(password, client_secret.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8")


def get_access_token(force_refresh: bool = False, now: Optional[float] = None) -> str:
    client_id = os.getenv("NAVER_COMMERCE_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_COMMERCE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError("NAVER_COMMERCE_CLIENT_ID/NAVER_COMMERCE_CLIENT_SECRET 미설정")

    current = now if now is not None else time.monotonic()
    cached = _TOKEN_CACHE.get("naver_commerce")
    if not force_refresh and cached and cached.get("expires_at", 0) > current + 30:
        return str(cached["access_token"])

    timestamp_ms = str(int(time.time() * 1000))
    payload = {
        "client_id": client_id,
        "timestamp": timestamp_ms,
        "client_secret_sign": _build_client_secret_sign(client_id, client_secret, timestamp_ms),
        "grant_type": "client_credentials",
        "type": "SELF",
    }

    import requests

    response = requests.post(_token_url(), data=payload, timeout=10)
    response.raise_for_status()
    data = response.json() or {}
    access_token = str(data.get("access_token") or "")
    expires_in = int(data.get("expires_in", 300))
    _TOKEN_CACHE["naver_commerce"] = {
        "access_token": access_token,
        "expires_at": current + max(expires_in - 30, 1),
    }
    return access_token
