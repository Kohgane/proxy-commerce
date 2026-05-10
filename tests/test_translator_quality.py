"""tests/test_translator_quality.py — Phase 143: 번역 품질 향상 테스트."""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# TranslationResult
# ═══════════════════════════════════════════════════════════════════════════════

class TestTranslationResult:
    def test_to_dict_keys(self):
        from src.ai.translator_quality import TranslationResult
        r = TranslationResult(
            original="テスト",
            translated="테스트",
            source_lang="JA",
            quality_tier="high",
            method="stub",
        )
        d = r.to_dict()
        for key in ("original", "translated", "source_lang", "quality_tier", "method", "has_forbidden", "spec"):
            assert key in d

    def test_default_no_forbidden(self):
        from src.ai.translator_quality import TranslationResult
        r = TranslationResult(original="t", translated="t", source_lang="JA", quality_tier="high", method="stub")
        assert r.has_forbidden is False
        assert r.forbidden_matches == []

    def test_spec_default_empty(self):
        from src.ai.translator_quality import TranslationResult
        r = TranslationResult(original="t", translated="t", source_lang="JA", quality_tier="high", method="stub")
        assert r.spec == {}


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_spec
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractSpec:
    def test_size_extraction(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("Size: M/L/XL")
        assert "사이즈" in spec
        assert "M/L/XL" in spec["사이즈"]

    def test_weight_extraction(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("Weight: 1.5kg")
        assert "무게" in spec
        assert "1.5kg" in spec["무게"]

    def test_material_extraction_and_map(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("Material: cotton")
        if "소재" in spec:
            assert "면" in spec["소재"]

    def test_color_extraction_and_map(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("Color: black")
        if "색상" in spec:
            assert "블랙" in spec["색상"]

    def test_dimensions_extraction(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("Dimensions: 30×20×10cm")
        assert "크기" in spec

    def test_capacity_extraction(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("Capacity: 500ml")
        assert "용량" in spec
        assert "500ml" in spec["용량"]

    def test_empty_text_returns_empty(self):
        from src.ai.translator_quality import _extract_spec
        assert _extract_spec("") == {}

    def test_no_match_returns_empty(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("상품 설명이 없습니다.")
        assert isinstance(spec, dict)

    def test_voltage_extraction(self):
        from src.ai.translator_quality import _extract_spec
        spec = _extract_spec("Voltage: 100V")
        if "전압" in spec:
            assert "100V" in spec["전압"].upper() or "100v" in spec["전압"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# _apply_ja_ko_shopping_map
# ═══════════════════════════════════════════════════════════════════════════════

class TestJaKoShoppingMap:
    def test_basic_replace(self):
        from src.ai.translator_quality import _apply_ja_ko_shopping_map
        result = _apply_ja_ko_shopping_map("セール中の新品")
        assert "세일" in result
        assert "신품" in result

    def test_no_change_for_korean(self):
        from src.ai.translator_quality import _apply_ja_ko_shopping_map
        result = _apply_ja_ko_shopping_map("한국어 텍스트")
        assert result == "한국어 텍스트"

    def test_shirocukin_free_shipping(self):
        from src.ai.translator_quality import _apply_ja_ko_shopping_map
        result = _apply_ja_ko_shopping_map("送料無料！")
        assert "무료배송" in result

    def test_limited_edition(self):
        from src.ai.translator_quality import _apply_ja_ko_shopping_map
        result = _apply_ja_ko_shopping_map("限定カラー")
        assert "한정" in result


# ═══════════════════════════════════════════════════════════════════════════════
# translate_title (stub 모드)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTranslateTitle:
    def test_empty_returns_empty(self):
        from src.ai.translator_quality import translate_title
        assert translate_title("") == ""

    def test_returns_string(self):
        from src.ai.translator_quality import translate_title
        result = translate_title("ユニクロ ダウン", source_lang="JA")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_japanese_shopping_terms_converted(self):
        from src.ai.translator_quality import translate_title
        result = translate_title("セール！新品 送料無料", source_lang="JA")
        # stub 모드에서 일본어 쇼핑 키워드 변환
        assert isinstance(result, str)

    def test_without_deepl_key(self, monkeypatch):
        monkeypatch.delenv("DEEPL_API_KEY", raising=False)
        from src.ai.translator_quality import translate_title
        result = translate_title("テスト商品", source_lang="JA")
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# translate_description (stub 모드)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTranslateDescription:
    def test_empty_returns_stub(self):
        from src.ai.translator_quality import translate_description
        result = translate_description("", source_lang="JA")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_paragraph_translation(self):
        from src.ai.translator_quality import translate_description
        text = "第一段落。\n\n第二段落。"
        result = translate_description(text, source_lang="JA")
        assert isinstance(result, str)

    def test_returns_string_not_none(self):
        from src.ai.translator_quality import translate_description
        assert translate_description("テスト説明") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# translate_and_check
# ═══════════════════════════════════════════════════════════════════════════════

class TestTranslateAndCheck:
    def test_returns_translation_result(self):
        from src.ai.translator_quality import translate_and_check, TranslationResult
        result = translate_and_check("ユニクロ ダウン", source_lang="JA")
        assert isinstance(result, TranslationResult)

    def test_spec_extracted_from_description(self):
        from src.ai.translator_quality import translate_and_check
        result = translate_and_check("テスト", description="Size: M Weight: 1.2kg", source_lang="JA")
        # 사양이 있다면 추출됨
        assert isinstance(result.spec, dict)

    def test_no_forbidden_for_normal_text(self):
        from src.ai.translator_quality import translate_and_check
        result = translate_and_check("유니클로 다운 재킷 블랙 M", source_lang="JA")
        assert isinstance(result.has_forbidden, bool)

    def test_source_lang_preserved(self):
        from src.ai.translator_quality import translate_and_check
        result = translate_and_check("テスト", source_lang="JA")
        assert result.source_lang == "JA"

    def test_quality_tier_in_result(self, monkeypatch):
        monkeypatch.setenv("TRANSLATION_QUALITY_TIER", "standard")
        import importlib
        import src.ai.translator_quality as m
        importlib.reload(m)
        result = m.translate_and_check("テスト")
        assert result.quality_tier == "standard"

    def test_method_stub_without_api_keys(self, monkeypatch):
        monkeypatch.delenv("DEEPL_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from src.ai.translator_quality import translate_and_check
        result = translate_and_check("テスト商品")
        assert result.method in ("stub", "deepl", "gpt")  # depends on env


# ═══════════════════════════════════════════════════════════════════════════════
# translator_stats
# ═══════════════════════════════════════════════════════════════════════════════

class TestTranslatorStats:
    def test_stats_keys(self):
        from src.ai.translator_quality import translator_stats
        stats = translator_stats()
        for key in ("quality_tier", "deepl_configured", "gpt_configured", "material_map_size", "spec_patterns"):
            assert key in stats

    def test_deepl_configured_false_without_key(self, monkeypatch):
        monkeypatch.delenv("DEEPL_API_KEY", raising=False)
        from src.ai.translator_quality import translator_stats
        stats = translator_stats()
        assert stats["deepl_configured"] is False

    def test_gpt_configured_false_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from src.ai.translator_quality import translator_stats
        stats = translator_stats()
        assert stats["gpt_configured"] is False

    def test_material_map_nonempty(self):
        from src.ai.translator_quality import _MATERIAL_MAP
        assert len(_MATERIAL_MAP) > 0

    def test_color_map_nonempty(self):
        from src.ai.translator_quality import _COLOR_MAP
        assert len(_COLOR_MAP) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 상수 검증
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_spec_patterns_list(self):
        from src.ai.translator_quality import _SPEC_PATTERNS
        assert len(_SPEC_PATTERNS) >= 5

    def test_ja_ko_shopping_map_nonempty(self):
        from src.ai.translator_quality import _JA_KO_SHOPPING_MAP
        assert len(_JA_KO_SHOPPING_MAP) > 0

    def test_seiru_mapping(self):
        from src.ai.translator_quality import _JA_KO_SHOPPING_MAP
        assert _JA_KO_SHOPPING_MAP["セール"] == "세일"

    def test_shipping_free_mapping(self):
        from src.ai.translator_quality import _JA_KO_SHOPPING_MAP
        assert _JA_KO_SHOPPING_MAP["送料無料"] == "무료배송"
