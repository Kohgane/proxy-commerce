"""tests/test_ai_listing_cache_key.py — Phase 151.1: 캐시 키 정상화 테스트.

- 캐시 키에 CURRENT_PHASE 포함 확인
- 캐시 키에 prompt_version 포함 확인
- Phase 변경 시 다른 캐시 키 생성 확인
- prompt_version 변경 시 다른 캐시 키 생성 확인
- page_url이 다르면 다른 캐시 키 생성 확인
"""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _mock_provider(monkeypatch):
    monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "mock")


class TestMakeAnalysisCacheKey:
    def test_key_contains_phase(self, monkeypatch):
        """캐시 키에 Phase 번호가 포함되어야 한다."""
        monkeypatch.setenv("CURRENT_PHASE_OVERRIDE", "151")
        import importlib
        import src.version as vmod
        importlib.reload(vmod)

        from src.ai_listing.analyzer import _make_analysis_cache_key
        key = _make_analysis_cache_key("abc123", "v2_explicit_fields")
        assert "phase=151" in key

        monkeypatch.delenv("CURRENT_PHASE_OVERRIDE")
        importlib.reload(vmod)

    def test_key_contains_prompt_version(self):
        """캐시 키에 prompt_version이 포함되어야 한다."""
        from src.ai_listing.analyzer import _make_analysis_cache_key
        key_v1 = _make_analysis_cache_key("abc123", "v1")
        key_v2 = _make_analysis_cache_key("abc123", "v2_explicit_fields")
        assert "prompt=v1" in key_v1
        assert "prompt=v2_explicit_fields" in key_v2

    def test_different_phase_different_key(self, monkeypatch):
        """Phase가 다르면 다른 캐시 키가 생성되어야 한다."""
        from src.ai_listing.analyzer import _make_analysis_cache_key
        import importlib, src.version as vmod

        monkeypatch.setenv("CURRENT_PHASE_OVERRIDE", "149")
        importlib.reload(vmod)
        key_149 = _make_analysis_cache_key("abc123", "v2_explicit_fields")

        monkeypatch.setenv("CURRENT_PHASE_OVERRIDE", "151")
        importlib.reload(vmod)
        key_151 = _make_analysis_cache_key("abc123", "v2_explicit_fields")

        assert key_149 != key_151

        monkeypatch.delenv("CURRENT_PHASE_OVERRIDE")
        importlib.reload(vmod)

    def test_different_prompt_version_different_key(self):
        """prompt_version이 다르면 다른 캐시 키가 생성되어야 한다."""
        from src.ai_listing.analyzer import _make_analysis_cache_key
        key_v1 = _make_analysis_cache_key("abc123", "v1", "https://example.com/p")
        key_v2 = _make_analysis_cache_key("abc123", "v2_explicit_fields", "https://example.com/p")
        assert key_v1 != key_v2

    def test_different_page_url_different_key(self):
        """page_url이 다르면 다른 캐시 키가 생성되어야 한다."""
        from src.ai_listing.analyzer import _make_analysis_cache_key
        key_a = _make_analysis_cache_key("abc123", "v2_explicit_fields", "https://example.com/a")
        key_b = _make_analysis_cache_key("abc123", "v2_explicit_fields", "https://example.com/b")
        assert key_a != key_b

    def test_key_contains_img_hash(self):
        """캐시 키에 이미지 해시가 포함되어야 한다."""
        from src.ai_listing.analyzer import _make_analysis_cache_key
        key = _make_analysis_cache_key("deadbeef1234", "v2_explicit_fields")
        assert "img=deadbeef1234" in key


class TestAnalyzeCacheUsesNewKey:
    def test_analyze_image_stores_with_phase_key(self, monkeypatch):
        """analyze_image가 새 Phase 포함 캐시 키로 저장해야 한다."""
        monkeypatch.setenv("CURRENT_PHASE_OVERRIDE", "151")
        import importlib, src.version as vmod
        importlib.reload(vmod)

        from src.ai_listing import analyzer
        analyzer._analysis_cache.clear()

        analyzer.analyze_image(image_url="https://example.com/cache_key_test.jpg")

        # 저장된 키에 phase=151이 포함되어야 함
        keys = list(analyzer._analysis_cache.keys())
        assert len(keys) == 1
        assert "phase=151" in keys[0]
        assert "prompt=" in keys[0]

        monkeypatch.delenv("CURRENT_PHASE_OVERRIDE")
        importlib.reload(vmod)

    def test_phase_149_cache_not_hit_by_phase_151(self, monkeypatch):
        """Phase 149 캐시가 Phase 151에서 재사용되지 않아야 한다."""
        from src.ai_listing import analyzer
        analyzer._analysis_cache.clear()

        import importlib, src.version as vmod

        # Phase 149로 캐싱
        monkeypatch.setenv("CURRENT_PHASE_OVERRIDE", "149")
        importlib.reload(vmod)
        r149 = analyzer.analyze_image(image_url="https://example.com/eight_ball.jpg")
        assert not r149.get("_analysis_cache_hit")

        # Phase 151에서 같은 URL 요청 → 캐시 미스여야 함
        monkeypatch.setenv("CURRENT_PHASE_OVERRIDE", "151")
        importlib.reload(vmod)
        r151 = analyzer.analyze_image(image_url="https://example.com/eight_ball.jpg")
        assert not r151.get("_analysis_cache_hit"), "Phase 149 캐시가 Phase 151에서 히트되면 안 됩니다"

        monkeypatch.delenv("CURRENT_PHASE_OVERRIDE")
        importlib.reload(vmod)


class TestEvictAnalysisCache:
    def test_evict_removes_all_img_entries(self, monkeypatch):
        """_evict_analysis_cache_for_image가 동일 이미지의 모든 캐시 삭제."""
        from src.ai_listing import analyzer
        from src.ai_listing.analyzer import _compute_image_hash, _evict_analysis_cache_for_image
        import importlib, src.version as vmod

        analyzer._analysis_cache.clear()
        img_url = "https://example.com/evict_test.jpg"
        img_hash = _compute_image_hash(image_url=img_url)

        # Phase 149/150/151로 캐싱된 척 직접 삽입
        analyzer._analysis_cache[f"phase=149:prompt=v1:url=nourl:img={img_hash}"] = {"result": {}, "_cached_at": time.time()}
        analyzer._analysis_cache[f"phase=150:prompt=v2_explicit_fields:url=nourl:img={img_hash}"] = {"result": {}, "_cached_at": time.time()}
        analyzer._analysis_cache[f"phase=151:prompt=v2_explicit_fields:url=nourl:img={img_hash}"] = {"result": {}, "_cached_at": time.time()}
        # 다른 이미지 캐시 (삭제되면 안 됨)
        analyzer._analysis_cache["phase=151:prompt=v2_explicit_fields:url=nourl:img=other_hash"] = {"result": {}, "_cached_at": time.time()}

        deleted = _evict_analysis_cache_for_image(img_hash)
        assert deleted == 3
        assert "phase=151:prompt=v2_explicit_fields:url=nourl:img=other_hash" in analyzer._analysis_cache

    def test_clear_all_analysis_cache(self):
        """clear_all_analysis_cache가 모든 캐시 항목을 삭제해야 한다."""
        from src.ai_listing import analyzer
        from src.ai_listing.analyzer import clear_all_analysis_cache

        analyzer._analysis_cache["key1"] = {"result": {}, "_cached_at": time.time()}
        analyzer._analysis_cache["key2"] = {"result": {}, "_cached_at": time.time()}
        assert len(analyzer._analysis_cache) >= 2

        count = clear_all_analysis_cache()
        assert count >= 2
        assert len(analyzer._analysis_cache) == 0
