from __future__ import annotations
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_get_embedding_disabled(monkeypatch):
    monkeypatch.setenv("CS_EMBEDDING_PROVIDER", "disabled")
    from src.cs_bot.embeddings import get_embedding
    result = get_embedding("테스트")
    assert result is None


def test_cosine_similarity_basic():
    from src.cs_bot.embeddings import cosine_similarity
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    from src.cs_bot.embeddings import cosine_similarity
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_empty():
    from src.cs_bot.embeddings import cosine_similarity
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], []) == 0.0
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_cosine_similarity_negative():
    from src.cs_bot.embeddings import cosine_similarity
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6


def test_get_embedding_openai_success(monkeypatch):
    monkeypatch.setenv("CS_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}],
        "usage": {"total_tokens": 10}
    }
    with patch("requests.post", return_value=mock_resp):
        with patch("src.ai.budget.BudgetGuard.can_spend", return_value=True):
            with patch("src.ai.budget.BudgetGuard.record"):
                from src.cs_bot import embeddings as emb_mod
                import importlib
                importlib.reload(emb_mod)
                result = emb_mod.get_embedding("hello")
                assert result == [0.1, 0.2, 0.3]


def test_get_embedding_openai_failure(monkeypatch):
    monkeypatch.setenv("CS_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with patch("requests.post", side_effect=Exception("network error")):
        with patch("src.ai.budget.BudgetGuard.can_spend", return_value=True):
            from src.cs_bot import embeddings as emb_mod
            import importlib
            importlib.reload(emb_mod)
            result = emb_mod.get_embedding("hello")
            assert result is None


def test_rebuild_faq_embeddings_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_EMBEDDING_PROVIDER", "disabled")
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "faq.jsonl"))
    from src.cs_bot.faq_store import FAQStore
    from src.cs_bot.embeddings import rebuild_faq_embeddings
    store = FAQStore()
    result = rebuild_faq_embeddings(store)
    assert result == 0
