"""tests/test_ai_translator.py — AITranslator 테스트 (Phase 130)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_import():
    """모듈 임포트 성공."""
    from src.seller_console.ai.translator import AITranslator
    assert AITranslator is not None


def test_stub_provider_when_no_keys(monkeypatch):
    """API 키 없으면 stub provider 선택."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.seller_console.ai.translator import AITranslator
    translator = AITranslator()
    assert translator.provider == "stub"


def test_openai_provider_when_key_set(monkeypatch):
    """OPENAI_API_KEY 설정 시 openai provider 선택."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test_openai_key_value")
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.seller_console.ai import translator as t_mod
    import importlib
    importlib.reload(t_mod)
    translator = t_mod.AITranslator()
    assert translator.provider == "openai"


def test_deepl_provider_when_only_deepl(monkeypatch):
    """DEEPL_API_KEY만 설정 시 deepl provider 선택."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPL_API_KEY", "deepl-test-key-value:fx")
    from src.seller_console.ai import translator as t_mod
    import importlib
    importlib.reload(t_mod)
    translator = t_mod.AITranslator()
    assert translator.provider == "deepl"


def test_stub_translate_returns_original(monkeypatch):
    """stub 모드: 원본 제목/설명 그대로 반환."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.seller_console.ai.translator import AITranslator
    translator = AITranslator()
    result = translator.translate_product({
        "title": "Alo Yoga Leggings",
        "description": "Premium yoga pants",
    })
    assert result["title_ko"] == "Alo Yoga Leggings"
    assert result["description_ko"] == "Premium yoga pants"
    assert result["provider"] == "stub"
    assert "copy_coupang" in result
    assert "copy_smartstore" in result
    assert "copy_11st" in result


def test_stub_translate_empty_input(monkeypatch):
    """stub 모드: 빈 입력 처리."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.seller_console.ai.translator import AITranslator
    translator = AITranslator()
    result = translator.translate_product({})
    assert result["title_ko"] == ""
    assert result["provider"] == "stub"


def test_dry_run_returns_stub(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 stub 반환."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test_key_value")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.ai.translator import AITranslator
    translator = AITranslator()
    result = translator.translate_product({"title": "Test Product", "description": "desc"})
    assert result["provider"] == "stub"


def test_generate_marketplace_copy_stub(monkeypatch):
    """stub 모드: generate_marketplace_copy 반환."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.seller_console.ai.translator import AITranslator
    translator = AITranslator()
    copy = translator.generate_marketplace_copy(
        {"title": "요가 레깅스", "description": "프리미엄 제품"},
        marketplace="coupang",
    )
    assert isinstance(copy, str)
    assert len(copy) > 0


def test_generate_copy_all_marketplaces_stub(monkeypatch):
    """stub 모드: 모든 마켓 카피 생성."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.seller_console.ai.translator import AITranslator
    translator = AITranslator()
    for market in ["coupang", "smartstore", "11st"]:
        copy = translator.generate_marketplace_copy({"title": "테스트 상품"}, marketplace=market)
        assert isinstance(copy, str)
        assert len(copy) > 0
