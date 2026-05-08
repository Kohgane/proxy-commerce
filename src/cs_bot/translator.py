from __future__ import annotations

import logging
import os
import re
from decimal import Decimal

from src.ai.budget import BudgetGuard
from src.cs_bot.faq_store import FAQEntry, FAQStore

logger = logging.getLogger(__name__)

_LANG_MAP = {"ko": "KO", "en": "EN", "ja": "JA", "zh": "ZH"}
_PLACEHOLDER_RE = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")
_FAIL_MARKER = "\n\n[번역 검수 필요]"


def translate_answer(answer_text: str, source_lang: str, target_lang: str) -> str:
    """
    DeepL 우선, OpenAI 폴백.
    BudgetGuard 통과 시에만.
    실패 시 원문 + 알림 마커.
    """
    provider = (os.getenv("CS_TRANSLATE_PROVIDER", "deepl") or "deepl").strip().lower()
    if os.getenv("CS_AUTO_TRANSLATE", "1") != "1" or provider == "disabled":
        return answer_text
    if not answer_text or source_lang == target_lang:
        return answer_text

    guard = BudgetGuard()
    if not guard.can_spend(Decimal("0.01")):
        return f"{answer_text}{_FAIL_MARKER}"

    frozen, token_map = _freeze_placeholders(answer_text)
    try:
        if provider == "openai":
            translated, cost_usd, tokens = _call_openai_translate(frozen, source_lang, target_lang)
            if translated:
                guard.record(cost_usd=cost_usd, provider="openai", tokens=tokens, note="cs_bot_translate")
                return _restore_placeholders(translated, token_map)
            translated, cost_usd, chars = _call_deepl_translate(frozen, source_lang, target_lang)
            if translated:
                guard.record(cost_usd=cost_usd, provider="deepl", tokens=chars, note="cs_bot_translate")
                return _restore_placeholders(translated, token_map)
        else:
            translated, cost_usd, chars = _call_deepl_translate(frozen, source_lang, target_lang)
            if translated:
                guard.record(cost_usd=cost_usd, provider="deepl", tokens=chars, note="cs_bot_translate")
                return _restore_placeholders(translated, token_map)
            translated, cost_usd, tokens = _call_openai_translate(frozen, source_lang, target_lang)
            if translated:
                guard.record(cost_usd=cost_usd, provider="openai", tokens=tokens, note="cs_bot_translate")
                return _restore_placeholders(translated, token_map)
    except Exception as exc:
        logger.warning("CS 번역 실패: %s", exc)
    return f"{answer_text}{_FAIL_MARKER}"


def get_or_translate_faq(faq: FAQEntry, target_lang: str, faq_store: FAQStore) -> str:
    """
    1) target_lang FAQ 있으면 그대로
    2) 없으면 source_lang FAQ를 번역 → 캐시(FAQEntry.translations[target_lang])
    3) 변수 치환은 번역 후 다시 적용
    """
    if not faq:
        return ""
    if faq.language == target_lang:
        return faq.answer_template
    translations = faq.translations or {}
    if target_lang in translations and translations[target_lang]:
        return str(translations[target_lang])
    translated = translate_answer(faq.answer_template, faq.language, target_lang)
    updated = FAQEntry.from_dict(faq.to_dict())
    updated.translations = {**translations, target_lang: translated}
    faq_store.update(updated)
    return translated


def _freeze_placeholders(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    frozen = text
    for idx, placeholder in enumerate(_PLACEHOLDER_RE.findall(text)):
        key = f"__CS_VAR_{idx}__"
        mapping[key] = placeholder
        frozen = frozen.replace(placeholder, key)
    return frozen, mapping


def _restore_placeholders(text: str, mapping: dict[str, str]) -> str:
    rendered = text
    for key, placeholder in mapping.items():
        rendered = rendered.replace(key, placeholder)
    return rendered


def _call_deepl_translate(text: str, source_lang: str, target_lang: str) -> tuple[str, Decimal, int]:
    import requests

    key = os.getenv("DEEPL_API_KEY", "")
    if not key:
        return "", Decimal("0"), 0
    endpoint = "https://api-free.deepl.com/v2/translate" if key.endswith(":fx") else "https://api.deepl.com/v2/translate"
    payload = {
        "auth_key": key,
        "text": text,
        "source_lang": _LANG_MAP.get(source_lang, "").upper(),
        "target_lang": _LANG_MAP.get(target_lang, "KO"),
    }
    if not payload["source_lang"]:
        payload.pop("source_lang")
    resp = requests.post(endpoint, data=payload, timeout=8)
    if not resp.ok:
        return "", Decimal("0"), 0
    data = resp.json()
    translations = data.get("translations") or []
    if not translations:
        return "", Decimal("0"), 0
    translated = str(translations[0].get("text") or "").strip()
    used_chars = len(text)
    per_char_usd = Decimal(os.getenv("DEEPL_COST_PER_CHAR_USD", "0.000025"))
    return translated, (per_char_usd * Decimal(str(used_chars))), used_chars


def _call_openai_translate(text: str, source_lang: str, target_lang: str) -> tuple[str, Decimal, int]:
    import requests

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "", Decimal("0"), 0
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "Translate customer support reply. Keep placeholders like __CS_VAR_0__ unchanged."},
                {"role": "user", "content": f"source={source_lang}, target={target_lang}\n{text}"},
            ],
            "temperature": 0.0,
            "max_tokens": 400,
        },
        timeout=8,
    )
    if not resp.ok:
        return "", Decimal("0"), 0
    data = resp.json()
    usage = data.get("usage", {}) or {}
    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    cost_usd = Decimal(str(input_tokens)) * Decimal("0.00000015") + Decimal(str(output_tokens)) * Decimal("0.0000006")
    content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    return content, cost_usd, total_tokens
