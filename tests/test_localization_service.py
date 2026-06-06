from __future__ import annotations

from src.seller_console.localization_service import LocalizationService


def test_localization_service_honest_untranslated_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)

    service = LocalizationService()
    source = {"title": "테스트 상품", "description": "설명", "keywords": ["최고"], "options": [{"name": "색상", "values": ["블랙"]}]}
    result = service.localize_product(source, "en-US")

    assert result.untranslated is True
    assert result.status == "untranslated_not_configured"
    assert result.translated["title"] == "테스트 상품"
    assert source["title"] == "테스트 상품"


def test_localization_service_uses_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)

    calls = {"count": 0}

    def _fake_translate(text: str, _src: str, _dst: str) -> str:
        calls["count"] += 1
        return f"EN:{text}"

    monkeypatch.setattr(LocalizationService, "_translate_openai", staticmethod(_fake_translate))

    service = LocalizationService()
    source = {"title": "테스트 상품", "description": "간단 설명"}
    first = service.localize_product(source, "en-US")
    second = service.localize_product(source, "en-US")

    assert first.translated["title"] == "EN:테스트 상품"
    assert second.cache_hits >= 1
    assert calls["count"] == 2


def test_localization_service_applies_forbidden_replacements(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)

    monkeypatch.setattr(LocalizationService, "_translate_openai", staticmethod(lambda text, _src, _dst: text))
    service = LocalizationService()

    result = service.localize_product({"title": "최고 상품"}, "ko-KR")
    assert "최고" not in result.translated["title"]
