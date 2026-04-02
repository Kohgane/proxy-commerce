"""src/categories/category_manager.py — Phase 39: 계층 카테고리 CRUD."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CategoryManager:
    """무한 깊이 계층 카테고리 관리.

    - CRUD
    - 이동 (parent 변경)
    - 자식 포함 삭제
    """

    def __init__(self):
        self._categories: Dict[str, dict] = {}

    def create(self, data: dict) -> dict:
        """카테고리 생성."""
        cat_id = data.get('id') or str(uuid.uuid4())[:8]
        parent_id = data.get('parent_id')
        if parent_id and parent_id not in self._categories:
            raise ValueError(f"부모 카테고리 없음: {parent_id}")
        cat = {
            'id': cat_id,
            'name': data.get('name', ''),
            'slug': data.get('slug', ''),
            'parent_id': parent_id,
            'order': int(data.get('order', 0)),
            'active': bool(data.get('active', True)),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._categories[cat_id] = cat
        logger.info("카테고리 생성: %s (parent=%s)", cat_id, parent_id)
        return cat

    def get(self, cat_id: str) -> Optional[dict]:
        return self._categories.get(cat_id)

    def list_children(self, parent_id: Optional[str] = None) -> List[dict]:
        """직속 자식 카테고리 목록."""
        return [c for c in self._categories.values() if c['parent_id'] == parent_id]

    def list_top_level(self) -> List[dict]:
        """최상위 카테고리 목록 (parent_id=None)."""
        return self.list_children(None)

    def get_ancestors(self, cat_id: str) -> List[dict]:
        """조상 카테고리 목록 (루트 → 현재 부모)."""
        ancestors = []
        current = self._categories.get(cat_id)
        if not current:
            return ancestors
        parent_id = current['parent_id']
        while parent_id:
            parent = self._categories.get(parent_id)
            if not parent:
                break
            ancestors.insert(0, parent)
            parent_id = parent['parent_id']
        return ancestors

    def get_descendants(self, cat_id: str) -> List[dict]:
        """모든 자손 카테고리 목록."""
        result = []
        stack = list(self.list_children(cat_id))
        while stack:
            child = stack.pop()
            result.append(child)
            stack.extend(self.list_children(child['id']))
        return result

    def move(self, cat_id: str, new_parent_id: Optional[str]) -> Optional[dict]:
        """카테고리 이동."""
        cat = self._categories.get(cat_id)
        if not cat:
            return None
        if new_parent_id and new_parent_id not in self._categories:
            raise ValueError(f"대상 부모 카테고리 없음: {new_parent_id}")
        # 순환 참조 방지
        if new_parent_id:
            descendants = {d['id'] for d in self.get_descendants(cat_id)}
            if new_parent_id in descendants:
                raise ValueError("순환 참조: 자손 카테고리로 이동 불가")
        cat['parent_id'] = new_parent_id
        return cat

    def update(self, cat_id: str, data: dict) -> Optional[dict]:
        """카테고리 업데이트."""
        cat = self._categories.get(cat_id)
        if not cat:
            return None
        for field in ('name', 'slug', 'order', 'active'):
            if field in data:
                cat[field] = data[field]
        return cat

    def delete(self, cat_id: str, delete_children: bool = False) -> bool:
        """카테고리 삭제.

        Args:
            delete_children: True면 자식도 모두 삭제, False면 자식이 있으면 오류
        """
        if cat_id not in self._categories:
            return False
        children = self.list_children(cat_id)
        if children and not delete_children:
            raise ValueError(f"자식 카테고리 존재: {[c['id'] for c in children]}")
        if delete_children:
            for desc in self.get_descendants(cat_id):
                self._categories.pop(desc['id'], None)
        del self._categories[cat_id]
        return True

    def list_all(self) -> List[dict]:
        return list(self._categories.values())
