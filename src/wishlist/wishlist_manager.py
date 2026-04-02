"""src/wishlist/wishlist_manager.py — Phase 43: 위시리스트 CRUD."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_WISHLISTS_PER_USER = 10
MAX_ITEMS_PER_WISHLIST = 100


class WishlistManager:
    """사용자별 위시리스트 CRUD.

    - 위시리스트 생성/삭제/이름 변경
    - 아이템 추가/삭제/이동 (폴더 그룹 간)
    - 아이템별 메모, 우선순위(1~5), 추가일
    - 사용자별 최대 위시리스트: 10, 위시리스트별 최대 아이템: 100
    """

    def __init__(self):
        self._wishlists: Dict[str, dict] = {}   # wishlist_id → wishlist
        self._items: Dict[str, dict] = {}        # item_id → item

    # ── 위시리스트 CRUD ─────────────────────────────────────────────

    def create_wishlist(self, user_id: str, name: str = '기본') -> dict:
        """위시리스트 생성."""
        user_lists = [w for w in self._wishlists.values() if w['user_id'] == user_id]
        if len(user_lists) >= MAX_WISHLISTS_PER_USER:
            raise ValueError(f"사용자당 최대 위시리스트 수 초과: {MAX_WISHLISTS_PER_USER}")
        wl_id = str(uuid.uuid4())[:8]
        wl = {
            'id': wl_id,
            'user_id': user_id,
            'name': name,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._wishlists[wl_id] = wl
        logger.info("위시리스트 생성: %s (user=%s)", wl_id, user_id)
        return wl

    def get_wishlist(self, wishlist_id: str) -> Optional[dict]:
        return self._wishlists.get(wishlist_id)

    def list_wishlists(self, user_id: str) -> List[dict]:
        return [w for w in self._wishlists.values() if w['user_id'] == user_id]

    def rename_wishlist(self, wishlist_id: str, name: str) -> dict:
        wl = self._wishlists.get(wishlist_id)
        if wl is None:
            raise KeyError(f"위시리스트 없음: {wishlist_id}")
        wl['name'] = name
        return wl

    def delete_wishlist(self, wishlist_id: str) -> bool:
        if wishlist_id not in self._wishlists:
            return False
        del self._wishlists[wishlist_id]
        # 관련 아이템 삭제
        to_delete = [i for i, item in self._items.items() if item['wishlist_id'] == wishlist_id]
        for item_id in to_delete:
            del self._items[item_id]
        return True

    # ── 아이템 CRUD ──────────────────────────────────────────────────

    def add_item(self, wishlist_id: str, product_id: str, **kwargs) -> dict:
        """아이템 추가."""
        if wishlist_id not in self._wishlists:
            raise KeyError(f"위시리스트 없음: {wishlist_id}")
        existing = [i for i in self._items.values() if i['wishlist_id'] == wishlist_id]
        if len(existing) >= MAX_ITEMS_PER_WISHLIST:
            raise ValueError(f"위시리스트 최대 아이템 수 초과: {MAX_ITEMS_PER_WISHLIST}")
        priority = int(kwargs.get('priority', 3))
        if not (1 <= priority <= 5):
            raise ValueError("우선순위는 1~5 사이여야 합니다")
        item_id = str(uuid.uuid4())[:8]
        item = {
            'id': item_id,
            'wishlist_id': wishlist_id,
            'product_id': product_id,
            'memo': kwargs.get('memo', ''),
            'priority': priority,
            'added_at': datetime.now(timezone.utc).isoformat(),
        }
        self._items[item_id] = item
        return item

    def remove_item(self, item_id: str) -> bool:
        if item_id not in self._items:
            return False
        del self._items[item_id]
        return True

    def get_item(self, item_id: str) -> Optional[dict]:
        return self._items.get(item_id)

    def list_items(self, wishlist_id: str) -> List[dict]:
        return [i for i in self._items.values() if i['wishlist_id'] == wishlist_id]

    def move_item(self, item_id: str, target_wishlist_id: str) -> dict:
        """아이템을 다른 위시리스트로 이동."""
        item = self._items.get(item_id)
        if item is None:
            raise KeyError(f"아이템 없음: {item_id}")
        if target_wishlist_id not in self._wishlists:
            raise KeyError(f"대상 위시리스트 없음: {target_wishlist_id}")
        item['wishlist_id'] = target_wishlist_id
        return item

    def update_item(self, item_id: str, **kwargs) -> dict:
        """메모/우선순위 수정."""
        item = self._items.get(item_id)
        if item is None:
            raise KeyError(f"아이템 없음: {item_id}")
        if 'memo' in kwargs:
            item['memo'] = kwargs['memo']
        if 'priority' in kwargs:
            priority = int(kwargs['priority'])
            if not (1 <= priority <= 5):
                raise ValueError("우선순위는 1~5 사이여야 합니다")
            item['priority'] = priority
        return item
