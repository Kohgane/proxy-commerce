"""src/auth/oauth_provider.py — OAuth2 provider abstraction (Google, Kakao)."""

import os
from urllib.parse import urlencode

PROVIDER_CONFIG = {
    'google': {
        'auth_url': 'https://accounts.google.com/o/oauth2/auth',
        'client_id_env': 'GOOGLE_CLIENT_ID',
        'scope': 'openid email profile',
    },
    'kakao': {
        'auth_url': 'https://kauth.kakao.com/oauth/authorize',
        'client_id_env': 'KAKAO_CLIENT_ID',
        'scope': 'profile_nickname profile_image account_email',
    },
}


class OAuthProvider:
    """OAuth2 provider for Google and Kakao."""

    def __init__(self, provider: str = 'google'):
        if provider not in PROVIDER_CONFIG:
            raise ValueError(f"Unsupported provider: {provider}. Supported: {list(PROVIDER_CONFIG)}")
        self.provider = provider
        self.config = PROVIDER_CONFIG[provider]
        self.client_id = os.getenv(self.config['client_id_env'], f'demo_{provider}_client_id')

    def get_authorization_url(self, redirect_uri: str, state: str = '') -> str:
        """Build the OAuth2 authorization URL."""
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': self.config['scope'],
        }
        if state:
            params['state'] = state
        return f"{self.config['auth_url']}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for tokens (simulated/mocked)."""
        return {
            'access_token': f'mock_access_token_{self.provider}_{code[:8]}',
            'token_type': 'Bearer',
            'expires_in': 3600,
            'refresh_token': f'mock_refresh_token_{self.provider}_{code[:8]}',
            'scope': self.config['scope'],
        }

    def get_user_profile(self, access_token: str) -> dict:
        """Get user profile from provider (mocked)."""
        if self.provider == 'google':
            return {
                'sub': 'google_user_123',
                'email': 'user@example.com',
                'name': 'Test User',
                'picture': 'https://example.com/avatar.jpg',
                'provider': 'google',
            }
        elif self.provider == 'kakao':
            return {
                'id': 'kakao_user_456',
                'kakao_account': {
                    'email': 'user@kakao.com',
                    'profile': {
                        'nickname': 'KakaoUser',
                        'profile_image_url': 'https://example.com/kakao_avatar.jpg',
                    },
                },
                'provider': 'kakao',
            }
        return {}

    def map_profile(self, raw_profile: dict, provider: str) -> dict:
        """Map raw provider profile to internal format."""
        if provider == 'google':
            return {
                'id': raw_profile.get('sub', ''),
                'email': raw_profile.get('email', ''),
                'name': raw_profile.get('name', ''),
                'provider': 'google',
                'avatar_url': raw_profile.get('picture', ''),
            }
        elif provider == 'kakao':
            account = raw_profile.get('kakao_account', {})
            profile = account.get('profile', {})
            return {
                'id': str(raw_profile.get('id', '')),
                'email': account.get('email', ''),
                'name': profile.get('nickname', ''),
                'provider': 'kakao',
                'avatar_url': profile.get('profile_image_url', ''),
            }
        raise ValueError(f"Unsupported provider for mapping: {provider}")
