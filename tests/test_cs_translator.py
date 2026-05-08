from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_translate_answer_deepl_primary(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "faq.jsonl"))
    monkeypatch.setenv("CS_AUTO_TRANSLATE", "1")
    monkeypatch.setenv("CS_TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setenv("DEEPL_API_KEY", "test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.cs_bot.translator import translate_answer

    with patch("src.cs_bot.translator.BudgetGuard.can_spend", return_value=True), \
         patch("src.cs_bot.translator._call_deepl_translate", return_value=("こんにちは", Decimal("0.001"), 10)):
        assert translate_answer("안녕하세요", "ko", "ja") == "こんにちは"


def test_translate_answer_openai_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_AUTO_TRANSLATE", "1")
    monkeypatch.setenv("CS_TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setenv("DEEPL_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    from src.cs_bot.translator import translate_answer

    with patch("src.cs_bot.translator.BudgetGuard.can_spend", return_value=True), \
         patch("src.cs_bot.translator._call_deepl_translate", return_value=("", Decimal("0"), 0)), \
         patch("src.cs_bot.translator._call_openai_translate", return_value=("hello", Decimal("0.001"), 10)):
        assert translate_answer("안녕하세요", "ko", "en") == "hello"


def test_translate_answer_preserves_variables(monkeypatch):
    monkeypatch.setenv("CS_AUTO_TRANSLATE", "1")
    monkeypatch.setenv("CS_TRANSLATE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    from src.cs_bot.translator import translate_answer

    with patch("src.cs_bot.translator.BudgetGuard.can_spend", return_value=True), \
         patch("src.cs_bot.translator._call_openai_translate", return_value=("Hi __CS_VAR_0__", Decimal("0.001"), 10)):
        out = translate_answer("안녕하세요 {{customer_name}}", "ko", "en")
    assert "{{customer_name}}" in out


def test_get_or_translate_faq_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "faq.jsonl"))
    monkeypatch.setenv("CS_AUTO_TRANSLATE", "1")
    monkeypatch.setenv("CS_TRANSLATE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    from src.cs_bot.faq_store import FAQEntry, FAQStore
    from src.cs_bot.translator import get_or_translate_faq

    store = FAQStore(str(tmp_path / "faq.jsonl"))
    faq = FAQEntry(
        faq_id="f1",
        category="general",
        language="ko",
        question="문의",
        keywords=["문의"],
        answer_template="안녕하세요 {{customer_name}}",
    )
    store.create(faq)
    with patch("src.cs_bot.translator.BudgetGuard.can_spend", return_value=True), \
         patch("src.cs_bot.translator._call_openai_translate", return_value=("Hello __CS_VAR_0__", Decimal("0.001"), 10)):
        out = get_or_translate_faq(faq, "en", store)
    assert "{{customer_name}}" in out
    saved = store.get("f1")
    assert saved is not None
    assert "en" in (saved.translations or {})
