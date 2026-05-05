"""src/auth/providers/kakao.py — Kakao OAuth 2.0 프로바이더 (Phase 133)."""
from __future__ import annotations

import os
from urllib.parse import urlencode
from typing import Optional

import requests


class KakaoProvider:
    """카카오 로그인 OAuth 2.0 프로바이더."""

    name = "kakao"

    _AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
    _TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    _USERINFO_URL = "https://kapi.kakao.com/v2/user/me"

    def __init__(self) -> None:
        self.client_id = os.getenv("KAKAO_REST_API_KEY", "")
        self.client_secret = os.getenv("KAKAO_CLIENT_SECRET", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id)

    def get_authorize_url(self, state: str, redirect_uri: str) -> str:
        """OAuth 인증 URL 반환."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"{self._AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """인가 코드 → 액세스 토큰 교환.

        Returns:
            {"access_token": "...", ...} 또는 {"error": "..."}
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        try:
            r = requests.post(self._TOKEN_URL, data=data, timeout=10)
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
              "provider": "kakao"
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
            account = raw.get("kakao_account", {})
            profile = account.get("profile", {})
            return {
                "provider_user_id": str(raw.get("id", "")),
                "email": account.get("email", ""),
                "name": profile.get("nickname", ""),
                "avatar_url": profile.get("profile_image_url", ""),
                "provider": "kakao",
            }
        except Exception as exc:
            return {"error": str(exc)}
