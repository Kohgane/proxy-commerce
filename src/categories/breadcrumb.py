"""src/categories/breadcrumb.py — Phase 39: 브레드크럼 경로 생성."""
import logging
from typing import List

logger = logging.getLogger(__name__)


class BreadcrumbGenerator:
    """카테고리 계층 경로 문자열 생성.

    예: "전자제품 > 컴퓨터 > 노트북"
    """

    def __init__(self, separator: str = ' > '):
        self.separator = separator

    def build(self, category_id: str, category_manager) -> str:
        """카테고리 ID로 브레드크럼 경로 생성.

        Args:
            category_id: 대상 카테고리 ID
            category_manager: CategoryManager 인스턴스

        Returns:
            경로 문자열
        """
        cat = category_manager.get(category_id)
        if not cat:
            return ''
        ancestors = category_manager.get_ancestors(category_id)
        path = ancestors + [cat]
        return self.separator.join(c['name'] for c in path)

    def build_from_list(self, categories: List[dict]) -> str:
        """카테고리 딕셔너리 목록으로 브레드크럼 생성."""
        return self.separator.join(c.get('name', '') for c in categories)

    def get_depth(self, category_id: str, category_manager) -> int:
        """카테고리 깊이 (0-based)."""
        ancestors = category_manager.get_ancestors(category_id)
        return len(ancestors)

    def build_all(self, category_manager) -> List[dict]:
        """모든 카테고리의 브레드크럼 생성."""
        result = []
        for cat in category_manager.list_all():
            path = self.build(cat['id'], category_manager)
            result.append({'id': cat['id'], 'name': cat['name'], 'breadcrumb': path})
        return result
