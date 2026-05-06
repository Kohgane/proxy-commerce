"""src/auth/providers/naver.py — Naver Login OAuth 2.0 프로바이더 (Phase 133)."""
from __future__ import annotations

import os
from urllib.parse import urlencode

import requests


class NaverProvider:
    """네이버 로그인 OAuth 2.0 프로바이더."""

    name = "naver"

    _AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
    _TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
    _USERINFO_URL = "https://openapi.naver.com/v1/nid/me"

    def __init__(self) -> None:
        self.client_id = os.getenv("NAVER_CLIENT_ID", "")
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_authorize_url(self, state: str, redirect_uri: str) -> str:
        """OAuth 인증 URL 반환."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{self._AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """인가 코드 → 액세스 토큰 교환.

        Returns:
            {"access_token": "...", ...} 또는 {"error": "..."}
        """
        params = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        try:
            r = requests.get(self._TOKEN_URL, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"error": str(exc)}

    def get_user_info(self, access_token: str) -> dict:
        """액세스 토큰으로 사용자 정보 조회.

        Returns:
            {
              "provider_user_id": "...",
              "email": "...",
              "name": "...",
              "avatar_url": "...",
              "provider": "naver"
            }
        """
        try:
            r = requests.get(
                self._USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            r.raise_for_status()
            raw = r.json()
            res = raw.get("response", {})
            return {
                "provider_user_id": res.get("id", ""),
                "email": res.get("email", ""),
                "name": res.get("name", ""),
                "avatar_url": res.get("profile_image", ""),
                "provider": "naver",
            }
        except Exception as exc:
            return {"error": str(exc)}
