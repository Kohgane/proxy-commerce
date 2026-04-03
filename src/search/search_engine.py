"""src/search/search_engine.py — Phase 48: 검색 엔진 (키워드 매칭, 인덱싱)."""
import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# 스코어 가중치
WEIGHT_TITLE = 3
WEIGHT_TAGS = 2
WEIGHT_DESCRIPTION = 1


class SearchEngine:
    """키워드 기반 상품 검색 (인메모리 역인덱스).

    - 한국어/영어/중국어/일본어 키워드 지원 (토큰화: 공백 분리 + n-gram)
    - 검색 결과 스코어링: 제목 3x, 태그 2x, 설명 1x
    """

    def __init__(self):
        self._products: Dict[str, dict] = {}       # product_id → product
        self._index: Dict[str, Set[str]] = defaultdict(set)  # token → {product_ids}

    def index_product(self, product: dict):
        """상품 인덱싱."""
        pid = product.get('id')
        if not pid:
            raise ValueError("상품 ID 필수")
        self._products[pid] = product
        # 기존 인덱스 제거 후 재인덱싱
        self._remove_from_index(pid)
        # 제목 토큰
        for token in self._tokenize(product.get('title', '')):
            self._index[token].add(pid)
        # 태그 토큰
        for tag in product.get('tags', []):
            for token in self._tokenize(tag):
                self._index[token].add(pid)
        # 설명 토큰 (첫 200자)
        desc = product.get('description', '')[:200]
        for token in self._tokenize(desc):
            self._index[token].add(pid)

    def remove_product(self, product_id: str):
        self._remove_from_index(product_id)
        self._products.pop(product_id, None)

    def search(self, query: str, limit: int = 20) -> List[dict]:
        """키워드 검색 + 스코어링."""
        tokens = self._tokenize(query)
        if not tokens:
            return []
        scores: Dict[str, float] = defaultdict(float)
        for token in tokens:
            matched = self._index.get(token, set())
            for pid in matched:
                product = self._products.get(pid)
                if product is None:
                    continue
                scores[pid] += self._score(product, token)
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [self._products[pid] for pid, _ in sorted_results[:limit] if pid in self._products]

    def get_product(self, product_id: str) -> Optional[dict]:
        return self._products.get(product_id)

    def get_all_products(self) -> List[dict]:
        return list(self._products.values())

    # ── 내부 메서드 ─────────────────────────────────────────────────

    def _tokenize(self, text: str) -> List[str]:
        """텍스트 토큰화 (소문자 변환 + 공백 분리 + 2-gram for non-ASCII)."""
        if not text:
            return []
        text = text.lower()
        tokens = set()
        # 공백 기반 분리
        words = re.split(r'[\s\-_,./]+', text)
        for word in words:
            word = word.strip()
            if not word:
                continue
            tokens.add(word)
            # 비ASCII (한/중/일) n-gram (2자)
            if any(ord(c) > 127 for c in word) and len(word) >= 2:
                for i in range(len(word) - 1):
                    tokens.add(word[i:i + 2])
        return [t for t in tokens if len(t) >= 1]

    def _score(self, product: dict, token: str) -> float:
        score = 0.0
        token_lower = token.lower()
        if token_lower in self._tokenize(product.get('title', '')):
            score += WEIGHT_TITLE
        for tag in product.get('tags', []):
            if token_lower in self._tokenize(tag):
                score += WEIGHT_TAGS
                break
        if token_lower in self._tokenize(product.get('description', '')[:200]):
            score += WEIGHT_DESCRIPTION
        return score

    def _remove_from_index(self, product_id: str):
        for token_set in self._index.values():
            token_set.discard(product_id)
