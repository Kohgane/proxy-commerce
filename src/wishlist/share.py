"""src/wishlist/share.py — Phase 43: 위시리스트 공유 (공유 링크, 권한 설정)."""
import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class WishlistShare:
    """위시리스트 공유 토큰 생성 및 조회 (읽기 전용)."""

    def __init__(self):
        self._shares: Dict[str, dict] = {}   # token → share record

    def create_share(self, wishlist_id: str, expires_at: Optional[str] = None) -> dict:
        """공유 토큰 생성."""
        token = secrets.token_urlsafe(16)
        share = {
            'token': token,
            'wishlist_id': wishlist_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'expires_at': expires_at,
            'active': True,
        }
        self._shares[token] = share
        logger.info("위시리스트 공유 생성: wishlist=%s token=%s", wishlist_id, token)
        return share

    def get_share(self, token: str) -> Optional[dict]:
        return self._shares.get(token)

    def revoke_share(self, token: str) -> bool:
        share = self._shares.get(token)
        if share is None:
            return False
        share['active'] = False
        return True

    def is_valid(self, token: str) -> bool:
        """토큰 유효성 검사 (존재 + 활성 + 만료 체크)."""
        share = self._shares.get(token)
        if share is None or not share['active']:
            return False
        if share['expires_at']:
            try:
                exp = datetime.fromisoformat(share['expires_at'])
                if datetime.now(timezone.utc) > exp:
                    return False
            except ValueError:
                return False
        return True

    def list_shares(self, wishlist_id: str) -> list:
        return [s for s in self._shares.values() if s['wishlist_id'] == wishlist_id]
