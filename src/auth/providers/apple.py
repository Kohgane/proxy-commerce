"""src/auth/providers/apple.py — Sign in with Apple OAuth 2.0 프로바이더 (v14).

Apple은 client_secret을 .p8 키로 서명한 ES256 JWT로 만든다(짧은 만료). 콜백은 form_post(POST).
응답의 id_token(JWT)에 sub/email이 들어 있어 별도 userinfo 엔드포인트가 없다.
키 미설정/라이브러리 미설치 시 is_configured=False → 버튼 비노출(가짜 활성 금지).

오너 액션: Apple Developer에서 Services ID(APPLE_CLIENT_ID), Team ID(APPLE_TEAM_ID),
Key ID(APPLE_KEY_ID), .p8 개인키(APPLE_PRIVATE_KEY) 발급/설정. (또는 미리 만든 APPLE_CLIENT_SECRET.)
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlencode

import requests


class AppleProvider:
    """Sign in with Apple 프로바이더."""

    name = "apple"

    _AUTH_URL = "https://appleid.apple.com/auth/authorize"
    _TOKEN_URL = "https://appleid.apple.com/auth/token"

    def __init__(self) -> None:
        self.client_id = os.getenv("APPLE_CLIENT_ID", "").strip()          # Services ID
        self.team_id = os.getenv("APPLE_TEAM_ID", "").strip()
        self.key_id = os.getenv("APPLE_KEY_ID", "").strip()
        # 개행이 \n 으로 인코딩돼 들어올 수 있어 복원
        self.private_key = os.getenv("APPLE_PRIVATE_KEY", "").strip().replace("\\n", "\n")
        # 미리 계산한 client_secret(JWT)을 직접 줄 수도 있음(선택)
        self.client_secret_env = os.getenv("APPLE_CLIENT_SECRET", "").strip()

    @property
    def is_configured(self) -> bool:
        if not self.client_id:
            return False
        if self.client_secret_env:
            return True
        return bool(self.team_id and self.key_id and self.private_key)

    # 호환용 속성(_oauth_runtime이 client_secret을 읽음) — 실제 시크릿은 JWT라 노출 안 함
    @property
    def client_secret(self) -> str:
        return self.client_secret_env or ("(.p8 키로 생성)" if (self.team_id and self.key_id and self.private_key) else "")

    def _build_client_secret(self) -> str:
        if self.client_secret_env:
            return self.client_secret_env
        import jwt  # PyJWT (ES256은 cryptography 필요)
        now = int(time.time())
        payload = {
            "iss": self.team_id,
            "iat": now,
            "exp": now + 3600,
            "aud": "https://appleid.apple.com",
            "sub": self.client_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="ES256", headers={"kid": self.key_id, "alg": "ES256"})

    def get_authorize_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "response_mode": "form_post",   # Apple은 콜백을 POST로 보냄
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "name email",
        }
        return f"{self._AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """인가 코드 → 토큰. id_token(JWT)을 access_token 슬롯에 매핑(흐름 호환)."""
        try:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.client_id,
                "client_secret": self._build_client_secret(),
            }
            r = requests.post(self._TOKEN_URL, data=data, timeout=10)
            r.raise_for_status()
            js = r.json()
            if isinstance(js, dict) and js.get("id_token") and not js.get("access_token"):
                js["access_token"] = js["id_token"]
            return js
        except Exception as exc:
            return {"error": str(exc)}

    def get_user_info(self, access_token: str) -> dict:
        """access_token == id_token(JWT) 디코드 → sub/email. (Apple 토큰엔드포인트가 발급한 토큰)"""
        try:
            import jwt
            claims = jwt.decode(access_token, options={"verify_signature": False})
            return {
                "provider_user_id": claims.get("sub", ""),
                "email": claims.get("email", ""),
                "name": "",
                "avatar_url": "",
                "provider": "apple",
            }
        except Exception as exc:
            return {"error": str(exc)}
