"""tests/test_ai_copywriter.py — AI 카피라이터 테스트 (Phase 134)."""
import os
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_request(**kwargs):
    from src.ai.copywriter import CopyRequest
    defaults = {
        "title": "Women Yoga Leggings High Waist Black",
        "source_lang": "en",
        "marketplace": "coupang",
        "variants": 1,
    }
    defaults.update(kwargs)
    return CopyRequest(**defaults)


# ---------------------------------------------------------------------------
# provider 선택
# ---------------------------------------------------------------------------

class TestProviderSelection:
    def test_selects_openai_when_key_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from src.ai.copywriter import AICopywriter
        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        assert writer.provider == "openai"

    def test_selects_deepl_when_only_deepl(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("DEEPL_API_KEY", "deepl-test")
        from src.ai.copywriter import AICopywriter
        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        assert writer.provider == "deepl_only"

    def test_selects_stub_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPL_API_KEY", raising=False)
        from src.ai.copywriter import AICopywriter
        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        assert writer.provider == "stub"


# ---------------------------------------------------------------------------
# 스텁 / dry-run
# ---------------------------------------------------------------------------

class TestStubGeneration:
    def test_dry_run_returns_stub(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from src.ai.copywriter import AICopywriter
        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        req = make_request()
        results = writer.generate(req)
        assert len(results) == 1
        assert results[0].provider == "stub"
        assert results[0].cached is False

    def test_stub_has_required_fields(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.ai.copywriter import AICopywriter
        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        req = make_request(variants=3)
        results = writer.generate(req)
        assert len(results) == 3
        for r in results:
            assert r.title_ko
            assert isinstance(r.bullet_points, list)
            assert isinstance(r.keywords, list)

    def test_no_keys_returns_stub(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPL_API_KEY", raising=False)
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        from src.ai.copywriter import AICopywriter
        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        req = make_request()
        results = writer.generate(req)
        assert results[0].provider == "stub"


# ---------------------------------------------------------------------------
# 캐시 hit/miss
# ---------------------------------------------------------------------------

class TestCache:
    def test_cache_hit_returns_cached_result(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from src.ai.copywriter import AICopywriter, CopyResult

        cached_data = [{
            "title_ko": "[캐시] 레깅스",
            "bullet_points": ["특징1"],
            "description_html": "<p>설명</p>",
            "keywords": ["레깅스"],
            "seo_meta_title": "SEO 제목",
            "seo_meta_desc": "SEO 설명",
            "forbidden_terms_warnings": [],
            "tokens_used": 100,
            "cost_usd": "0.01",
            "cached": False,
            "provider": "openai",
            "variant_index": 0,
        }]

        mock_cache = MagicMock()
        mock_cache.get.return_value = cached_data
        mock_budget = MagicMock()
        mock_budget.can_spend.return_value = True

        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        writer.cache = mock_cache
        writer.budget = mock_budget

        req = make_request()
        results = writer.generate(req)
        assert len(results) == 1
        assert results[0].title_ko == "[캐시] 레깅스"
        assert results[0].cached is True
        mock_cache.get.assert_called_once()

    def test_cache_miss_proceeds_to_generation(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from src.ai.copywriter import AICopywriter

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_budget = MagicMock()
        mock_budget.can_spend.return_value = True

        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        writer.cache = mock_cache
        writer.budget = mock_budget
        writer.provider = "stub"

        req = make_request()
        results = writer.generate(req)
        assert results[0].provider == "stub"
        mock_cache.set.assert_called_once()


# ---------------------------------------------------------------------------
# 예산 차단
# ---------------------------------------------------------------------------

class TestBudgetBlock:
    def test_budget_exceeded_raises_error(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        from src.ai.copywriter import AICopywriter
        from src.ai.budget import BudgetExceededError

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_budget = MagicMock()
        mock_budget.can_spend.return_value = False
        mock_budget.summary.return_value = {
            "limit_usd": 100.0, "used_usd": 100.5,
            "remaining_usd": -0.5, "pct": 100.5, "status": "exceeded",
        }

        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        writer.cache = mock_cache
        writer.budget = mock_budget
        writer.provider = "openai"

        req = make_request()
        with pytest.raises(BudgetExceededError):
            writer.generate(req)


# ---------------------------------------------------------------------------
# CopyRequest 캐시 키
# ---------------------------------------------------------------------------

class TestCopyRequestCacheKey:
    def test_same_request_same_key(self):
        from src.ai.copywriter import CopyRequest
        r1 = CopyRequest(title="Yoga Leggings", marketplace="coupang")
        r2 = CopyRequest(title="Yoga Leggings", marketplace="coupang")
        assert r1.cache_key() == r2.cache_key()

    def test_different_marketplace_different_key(self):
        from src.ai.copywriter import CopyRequest
        r1 = CopyRequest(title="Yoga Leggings", marketplace="coupang")
        r2 = CopyRequest(title="Yoga Leggings", marketplace="smartstore")
        assert r1.cache_key() != r2.cache_key()

    def test_key_contains_market(self):
        from src.ai.copywriter import CopyRequest
        r = CopyRequest(title="T-shirt", marketplace="coupang")
        assert "coupang" in r.cache_key()


# ---------------------------------------------------------------------------
# CopyResult.to_dict
# ---------------------------------------------------------------------------

class TestCopyResultDict:
    def test_to_dict_has_all_fields(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.ai.copywriter import AICopywriter
        with patch("src.ai.cache.AICache._get_ws", return_value=None), \
             patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            writer = AICopywriter()
        req = make_request()
        results = writer.generate(req)
        d = results[0].to_dict()
        for key in ["title_ko", "bullet_points", "description_html", "keywords",
                    "seo_meta_title", "seo_meta_desc", "forbidden_terms_warnings",
                    "tokens_used", "cost_usd", "cached", "provider", "variant_index"]:
            assert key in d, f"Missing key: {key}"
