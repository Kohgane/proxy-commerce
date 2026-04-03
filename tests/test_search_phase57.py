"""tests/test_search_phase57.py — Phase 57: 검색 엔진 고도화 테스트."""
from __future__ import annotations

import pytest
from src.search.search_index import SearchIndex
from src.search.tokenizer import Tokenizer
from src.search.ranker import Ranker
from src.search.facet_collector import FacetCollector
from src.search.search_suggester import SearchSuggester


class TestSearchIndex:
    def setup_method(self):
        self.index = SearchIndex()

    def test_add_and_search(self):
        self.index.add_document("d1", {"title": "python programming", "body": "learn python"})
        self.index.add_document("d2", {"title": "java basics", "body": "java introduction"})
        results = self.index.search("python")
        doc_ids = [r[0] for r in results]
        assert "d1" in doc_ids
        assert "d2" not in doc_ids

    def test_search_returns_scores(self):
        self.index.add_document("d1", {"title": "apple apple apple"})
        self.index.add_document("d2", {"title": "apple banana"})
        results = self.index.search("apple")
        assert results[0][0] == "d1"  # higher frequency = higher score

    def test_get_document(self):
        self.index.add_document("d1", {"title": "test doc"})
        doc = self.index.get_document("d1")
        assert doc["title"] == "test doc"

    def test_get_missing_document(self):
        assert self.index.get_document("nonexistent") is None

    def test_remove_document(self):
        self.index.add_document("d1", {"title": "to remove"})
        self.index.remove_document("d1")
        assert self.index.get_document("d1") is None
        results = self.index.search("remove")
        assert not any(r[0] == "d1" for r in results)

    def test_top_k_limit(self):
        for i in range(20):
            self.index.add_document(f"d{i}", {"title": "common word"})
        results = self.index.search("common", top_k=5)
        assert len(results) <= 5

    def test_update_document(self):
        self.index.add_document("d1", {"title": "old content"})
        self.index.add_document("d1", {"title": "new content"})
        doc = self.index.get_document("d1")
        assert doc["title"] == "new content"


class TestTokenizer:
    def setup_method(self):
        self.tokenizer = Tokenizer()

    def test_basic_tokenize(self):
        tokens = self.tokenizer.tokenize("Hello World foo")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens

    def test_punctuation_split(self):
        tokens = self.tokenizer.tokenize("hello, world! foo.bar")
        assert "hello" in tokens
        assert "world" in tokens

    def test_korean_tokenize(self):
        tokens = self.tokenizer.tokenize("안녕하세요 python")
        assert "안녕하세요" in tokens
        assert "python" in tokens

    def test_mixed_korean_english(self):
        tokens = self.tokenizer.tokenize("파이썬 programming 언어")
        assert "파이썬" in tokens
        assert "programming" in tokens
        assert "언어" in tokens

    def test_empty_string(self):
        tokens = self.tokenizer.tokenize("")
        assert tokens == []


class TestRanker:
    def setup_method(self):
        self.ranker = Ranker()
        self.index = SearchIndex()

    def test_rank_by_tfidf(self):
        self.index.add_document("d1", {"text": "python python python"})
        self.index.add_document("d2", {"text": "python java"})
        self.index.add_document("d3", {"text": "java ruby"})
        candidates = ["d1", "d2", "d3"]
        results = self.ranker.rank(["python"], candidates, self.index)
        # d1 should rank highest (most python occurrences)
        assert results[0][0] == "d1"

    def test_rank_empty_candidates(self):
        results = self.ranker.rank(["query"], [], self.index)
        assert results == []

    def test_rank_no_match(self):
        self.index.add_document("d1", {"text": "java"})
        results = self.ranker.rank(["python"], ["d1"], self.index)
        assert results == []


class TestFacetCollector:
    def setup_method(self):
        self.collector = FacetCollector()

    def test_add_and_collect(self):
        self.collector.add_document("d1", {"category": "books", "brand": "acme"})
        self.collector.add_document("d2", {"category": "books", "brand": "beta"})
        self.collector.add_document("d3", {"category": "electronics", "brand": "acme"})
        facets = self.collector.collect(["d1", "d2"])
        assert facets["category"]["books"] == 2

    def test_get_facets_field(self):
        self.collector.add_document("d1", {"color": "red"})
        self.collector.add_document("d2", {"color": "blue"})
        self.collector.add_document("d3", {"color": "red"})
        counts = self.collector.get_facets("color")
        assert counts["red"] == 2
        assert counts["blue"] == 1

    def test_collect_empty_ids(self):
        self.collector.add_document("d1", {"cat": "a"})
        facets = self.collector.collect([])
        assert facets == {}


class TestSearchSuggester:
    def setup_method(self):
        self.suggester = SearchSuggester()

    def test_suggest_basic(self):
        self.suggester.add_term("python", 10)
        self.suggester.add_term("programming", 5)
        self.suggester.add_term("pytest", 8)
        suggestions = self.suggester.suggest("py")
        assert "python" in suggestions
        assert "pytest" in suggestions
        assert "programming" not in suggestions

    def test_suggest_ordered_by_weight(self):
        self.suggester.add_term("apple", 10)
        self.suggester.add_term("application", 5)
        suggestions = self.suggester.suggest("app")
        assert suggestions[0] == "apple"

    def test_suggest_limit(self):
        for i in range(10):
            self.suggester.add_term(f"test{i}", float(i))
        suggestions = self.suggester.suggest("test", limit=3)
        assert len(suggestions) <= 3

    def test_suggest_no_match(self):
        self.suggester.add_term("python", 1)
        suggestions = self.suggester.suggest("xyz")
        assert suggestions == []

    def test_add_term_accumulates_weight(self):
        self.suggester.add_term("python", 5)
        self.suggester.add_term("python", 5)
        self.suggester.add_term("java", 8)
        suggestions = self.suggester.suggest("p")
        assert "python" in suggestions
