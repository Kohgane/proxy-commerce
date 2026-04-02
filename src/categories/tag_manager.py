"""src/categories/tag_manager.py — Phase 39: 태그 관리 + 자동 태깅."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TagManager:
    """태그 CRUD, 자동 태깅, 태그 검색."""

    def __init__(self):
        self._tags: Dict[str, dict] = {}  # tag_id → tag
        self._product_tags: Dict[str, set] = {}  # product_id → set of tag_ids
        self._keyword_rules: List[dict] = []  # {'keywords': [...], 'tag_id': ...}

    def create_tag(self, name: str, color: str = '') -> dict:
        """태그 생성."""
        tag_id = str(uuid.uuid4())[:8]
        tag = {
            'id': tag_id,
            'name': name,
            'color': color,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._tags[tag_id] = tag
        return tag

    def get_tag(self, tag_id: str) -> Optional[dict]:
        return self._tags.get(tag_id)

    def get_tag_by_name(self, name: str) -> Optional[dict]:
        for tag in self._tags.values():
            if tag['name'] == name:
                return tag
        return None

    def list_tags(self) -> List[dict]:
        return list(self._tags.values())

    def update_tag(self, tag_id: str, data: dict) -> Optional[dict]:
        tag = self._tags.get(tag_id)
        if not tag:
            return None
        for field in ('name', 'color'):
            if field in data:
                tag[field] = data[field]
        return tag

    def delete_tag(self, tag_id: str) -> bool:
        if tag_id not in self._tags:
            return False
        del self._tags[tag_id]
        # 상품 태그에서도 제거
        for product_id in self._product_tags:
            self._product_tags[product_id].discard(tag_id)
        return True

    def add_tag_to_product(self, product_id: str, tag_id: str) -> bool:
        """상품에 태그 추가."""
        if tag_id not in self._tags:
            raise ValueError(f"태그 없음: {tag_id}")
        if product_id not in self._product_tags:
            self._product_tags[product_id] = set()
        self._product_tags[product_id].add(tag_id)
        return True

    def remove_tag_from_product(self, product_id: str, tag_id: str) -> bool:
        """상품에서 태그 제거."""
        tags = self._product_tags.get(product_id, set())
        if tag_id in tags:
            tags.discard(tag_id)
            return True
        return False

    def get_product_tags(self, product_id: str) -> List[dict]:
        """상품의 태그 목록."""
        tag_ids = self._product_tags.get(product_id, set())
        return [self._tags[tid] for tid in tag_ids if tid in self._tags]

    def search_tags(self, query: str) -> List[dict]:
        """태그 이름 검색."""
        query_lower = query.lower()
        return [t for t in self._tags.values() if query_lower in t['name'].lower()]

    def add_keyword_rule(self, keywords: List[str], tag_id: str) -> dict:
        """자동 태깅 키워드 규칙 추가."""
        if tag_id not in self._tags:
            raise ValueError(f"태그 없음: {tag_id}")
        rule = {'keywords': [k.lower() for k in keywords], 'tag_id': tag_id}
        self._keyword_rules.append(rule)
        return rule

    def auto_tag(self, product_id: str, text: str) -> List[str]:
        """텍스트 기반 자동 태깅. 적용된 tag_id 목록 반환."""
        text_lower = text.lower()
        applied = []
        for rule in self._keyword_rules:
            if any(kw in text_lower for kw in rule['keywords']):
                try:
                    self.add_tag_to_product(product_id, rule['tag_id'])
                    applied.append(rule['tag_id'])
                except ValueError:
                    pass
        return applied
