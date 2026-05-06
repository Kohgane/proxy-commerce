"""tests/test_ai_cache.py — AI 캐시 테스트 (Phase 134)."""
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


class TestAICache:
    def _make_cache(self):
        from src.ai.cache import AICache
        with patch("src.ai.cache.AICache._get_ws", return_value=None):
            cache = AICache()
        return cache

    def test_get_returns_none_when_no_ws(self):
        cache = self._make_cache()
        result = cache.get("test_key")
        assert result is None

    def test_set_silently_skips_when_no_ws(self):
        cache = self._make_cache()
        cache.set("key", {"data": 1})  # Should not raise

    def test_get_returns_cached_value(self):
        from src.ai.cache import AICache
        cache = self._make_cache()

        # Mock worksheet
        mock_ws = MagicMock()
        now = datetime.now(timezone.utc).isoformat()
        cached_data = [{"title_ko": "캐시된 제목"}]
        mock_ws.get_all_records.return_value = [{
            "cache_key": "test_key",
            "source_hash": "abc123",
            "result_json": json.dumps(cached_data),
            "provider": "openai",
            "created_at": now,
            "hits": "0",
            "tokens": "100",
            "cost_usd": "0.01",
        }]
        cache._ws = mock_ws

        result = cache.get("test_key")
        assert result == cached_data

    def test_get_returns_none_for_expired(self):
        from src.ai.cache import AICache
        import os
        os.environ["AI_CACHE_TTL_DAYS"] = "30"
        cache = self._make_cache()

        mock_ws = MagicMock()
        old_date = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        mock_ws.get_all_records.return_value = [{
            "cache_key": "test_key",
            "source_hash": "abc123",
            "result_json": json.dumps([{"title_ko": "old"}]),
            "provider": "openai",
            "created_at": old_date,
            "hits": "0",
            "tokens": "100",
            "cost_usd": "0.01",
        }]
        cache._ws = mock_ws

        result = cache.get("test_key")
        assert result is None

    def test_get_returns_none_for_wrong_key(self):
        from src.ai.cache import AICache
        cache = self._make_cache()

        mock_ws = MagicMock()
        now = datetime.now(timezone.utc).isoformat()
        mock_ws.get_all_records.return_value = [{
            "cache_key": "other_key",
            "result_json": json.dumps([]),
            "created_at": now,
        }]
        cache._ws = mock_ws

        result = cache.get("test_key")
        assert result is None

    def test_set_appends_row(self):
        from src.ai.cache import AICache
        cache = self._make_cache()

        mock_ws = MagicMock()
        cache._ws = mock_ws

        cache.set("new_key", [{"title_ko": "새 제목"}], provider="openai", tokens=100)
        mock_ws.append_row.assert_called_once()

        row = mock_ws.append_row.call_args[0][0]
        assert row[0] == "new_key"  # cache_key
        assert "새 제목" in row[2]  # result_json contains the data

    def test_invalidate_deletes_row(self):
        from src.ai.cache import AICache
        cache = self._make_cache()

        mock_ws = MagicMock()
        now = datetime.now(timezone.utc).isoformat()
        mock_ws.get_all_records.return_value = [{
            "cache_key": "del_key",
            "result_json": "[]",
            "created_at": now,
        }]
        cache._ws = mock_ws

        cache.invalidate("del_key")
        mock_ws.delete_rows.assert_called_once()
