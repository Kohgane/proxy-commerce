from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from src.ai.forbidden_terms import apply_suggestions, check_forbidden_terms


@dataclass
class LocalizationResult:
    locale: str
    translated: dict[str, Any]
    translated_count: int = 0
    cache_hits: int = 0
    untranslated: bool = False
    status: str = "translated"


class LocalizationService:
    """상품 필드를 타깃 locale로 현지화한다.

    원문은 유지하고 번역본만 별도 결과로 반환한다.
    """

    _cache: dict[tuple[str, str, str], str] = {}

    def __init__(self) -> None:
        self._openai = bool(os.getenv("OPENAI_API_KEY"))
        self._deepl = bool(os.getenv("DEEPL_API_KEY"))

    def is_configured(self) -> bool:
        return self._openai or self._deepl

    def localize_product(self, product: dict[str, Any], target_locale: str, source_lang: str | None = None) -> LocalizationResult:
        locale = (target_locale or "ko-KR").strip() or "ko-KR"
        target_lang = self._locale_to_lang(locale)
        src_lang = self._locale_to_lang(source_lang or "ko-KR")
        untranslated = not self.is_configured()

        title = str(product.get("title") or product.get("title_ko") or product.get("title_en") or "").strip()
        description = str(product.get("description") or "").strip()
        keywords = self._normalize_keywords(product.get("keywords"))
        options = self._normalize_options(product.get("options"))

        translated_count = 0
        cache_hits = 0

        localized_title, used_cache = self._translate_text(title, src_lang, target_lang, untranslated=untranslated)
        translated_count += int(bool(title and localized_title != title))
        cache_hits += int(used_cache)

        localized_description, used_cache = self._translate_text(description, src_lang, target_lang, untranslated=untranslated)
        translated_count += int(bool(description and localized_description != description))
        cache_hits += int(used_cache)

        localized_keywords: list[str] = []
        for keyword in keywords:
            value, used_cache = self._translate_text(keyword, src_lang, target_lang, untranslated=untranslated)
            localized_keywords.append(value)
            translated_count += int(bool(keyword and value != keyword))
            cache_hits += int(used_cache)

        localized_options: list[dict[str, Any]] = []
        for row in options:
            name, used_cache = self._translate_text(str(row.get("name") or ""), src_lang, target_lang, untranslated=untranslated)
            cache_hits += int(used_cache)
            translated_count += int(bool(row.get("name") and name != row.get("name")))

            values = []
            for value in row.get("values", []):
                translated_value, used_cache = self._translate_text(str(value), src_lang, target_lang, untranslated=untranslated)
                values.append(translated_value)
                cache_hits += int(used_cache)
                translated_count += int(bool(value and translated_value != value))
            localized_options.append({"name": name, "values": values})

        status = "translated"
        if untranslated:
            status = "untranslated_not_configured"
        elif translated_count == 0:
            status = "unchanged"

        localized_payload = {
            "locale": locale,
            "language": target_lang,
            "title": self._apply_forbidden_rules(localized_title),
            "description": self._apply_forbidden_rules(localized_description),
            "keywords": [self._apply_forbidden_rules(k) for k in localized_keywords],
            "options": localized_options,
            "status": status,
            "untranslated": untranslated,
        }
        return LocalizationResult(
            locale=locale,
            translated=localized_payload,
            translated_count=translated_count,
            cache_hits=cache_hits,
            untranslated=untranslated,
            status=status,
        )

    def _translate_text(self, text: str, source_lang: str, target_lang: str, *, untranslated: bool) -> tuple[str, bool]:
        value = (text or "").strip()
        if not value or source_lang == target_lang:
            return value, False
        provider = "openai" if self._openai else "deepl"
        cache_key = (provider, value, target_lang)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached, True
        if untranslated:
            self._cache[cache_key] = value
            return value, False

        translated = value
        if provider == "openai":
            translated = self._translate_openai(value, source_lang, target_lang) or value
        else:
            translated = self._translate_deepl(value, source_lang, target_lang) or value
        self._cache[cache_key] = translated
        return translated, False

    @staticmethod
    def _translate_openai(text: str, source_lang: str, target_lang: str) -> str:
        from src.cs_bot.translator import _call_openai_translate

        translated, _cost, _tokens = _call_openai_translate(text, source_lang, target_lang)
        return translated

    @staticmethod
    def _translate_deepl(text: str, source_lang: str, target_lang: str) -> str:
        from src.cs_bot.translator import _call_deepl_translate

        translated, _cost, _chars = _call_deepl_translate(text, source_lang, target_lang)
        return translated

    @staticmethod
    def _normalize_keywords(raw: Any) -> list[str]:
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str):
            return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]
        return []

    @staticmethod
    def _normalize_options(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            values_raw = row.get("values") if isinstance(row.get("values"), list) else []
            values = [str(v).strip() for v in values_raw if str(v).strip()]
            out.append({"name": name, "values": values})
        return out

    @staticmethod
    def _locale_to_lang(locale: str) -> str:
        token = (locale or "ko").replace("_", "-").split("-")[0].strip().lower()
        if token.startswith("zh"):
            return "zh"
        if token.startswith("ja"):
            return "ja"
        if token.startswith("de"):
            return "de"
        if token.startswith("es"):
            return "es"
        if token.startswith("en"):
            return "en"
        return "ko"

    @staticmethod
    def _apply_forbidden_rules(text: str) -> str:
        if not text:
            return text
        matches = check_forbidden_terms(text)
        if not matches:
            return text
        return apply_suggestions(text, matches)
