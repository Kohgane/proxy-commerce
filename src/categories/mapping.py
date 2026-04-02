"""src/categories/mapping.py — Phase 39: 플랫폼 카테고리 ID 매핑."""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PLATFORMS = {'coupang', 'naver', 'internal'}


class CategoryMapping:
    """플랫폼 간 카테고리 ID 매핑.

    내부 카테고리 ID ↔ 쿠팡/네이버 카테고리 ID
    """

    def __init__(self):
        # internal_id → {'coupang': ..., 'naver': ...}
        self._mappings: Dict[str, Dict[str, str]] = {}

    def set_mapping(self, internal_id: str, platform: str, platform_id: str) -> dict:
        """매핑 설정."""
        if platform not in PLATFORMS:
            raise ValueError(f"지원하지 않는 플랫폼: {platform}")
        if internal_id not in self._mappings:
            self._mappings[internal_id] = {}
        self._mappings[internal_id][platform] = platform_id
        logger.info("카테고리 매핑 설정: %s → %s:%s", internal_id, platform, platform_id)
        return self._mappings[internal_id]

    def get_mapping(self, internal_id: str, platform: str) -> Optional[str]:
        """특정 플랫폼의 카테고리 ID 조회."""
        return self._mappings.get(internal_id, {}).get(platform)

    def get_all_mappings(self, internal_id: str) -> dict:
        """내부 ID의 모든 플랫폼 매핑 조회."""
        return self._mappings.get(internal_id, {})

    def find_by_platform_id(self, platform: str, platform_id: str) -> Optional[str]:
        """플랫폼 ID로 내부 ID 역조회."""
        for internal_id, mappings in self._mappings.items():
            if mappings.get(platform) == platform_id:
                return internal_id
        return None

    def find_unmapped(self, internal_ids: List[str], platform: str) -> List[str]:
        """매핑되지 않은 내부 카테고리 ID 목록."""
        return [
            iid for iid in internal_ids
            if not self._mappings.get(iid, {}).get(platform)
        ]

    def list_all_mappings(self) -> List[dict]:
        """전체 매핑 목록."""
        result = []
        for internal_id, platforms in self._mappings.items():
            result.append({'internal_id': internal_id, **platforms})
        return result

    def delete_mapping(self, internal_id: str, platform: Optional[str] = None) -> bool:
        """매핑 삭제."""
        if internal_id not in self._mappings:
            return False
        if platform:
            self._mappings[internal_id].pop(platform, None)
        else:
            del self._mappings[internal_id]
        return True
