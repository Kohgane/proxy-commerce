"""src/ai_listing/generator.py — 제목/설명/태그 생성 (Phase 149).

마켓별 제약 준수:
  - 제목 글자수: 쿠팡 50자 / 스마트스토어 100자 등
  - 금칙어 필터링
  - 한/일 다국어 옵션
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from src.ai_listing.category_mapper import normalize_display_category
from src.ai_listing.jsonld_parser import extract_material, extract_variants

logger = logging.getLogger(__name__)

_DEFAULT_LANGUAGE = os.getenv("AI_LISTING_LANG_DEFAULT", "kr")
_JSONLD_PRIORITY = os.getenv("AI_LISTING_JSONLD_PRIORITY", "1") == "1"
_TRANSLATE_DESCRIPTION = os.getenv("AI_LISTING_TRANSLATE_DESCRIPTION", "1") == "1"


# ── 금칙어 필터 ──────────────────────────────────────────────────────────────

def _filter_forbidden_terms(text: str, forbidden: List[str]) -> str:
    """금칙어를 텍스트에서 제거한다."""
    for term in forbidden:
        text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
    # 중복 공백 정리
    text = re.sub(r" {2,}", " ", text).strip()
    return text


def _trim_to_max_len(text: str, max_len: int) -> str:
    """최대 글자수 초과 시 트림."""
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip()


def _translate_to_korean(text: str) -> str:
    text = str(text or "").strip()
    if not text or not _TRANSLATE_DESCRIPTION:
        return text
    deepl_key = os.getenv("DEEPL_API_KEY")
    if not deepl_key:
        return text
    try:
        import requests

        resp = requests.post(
            os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate"),
            data={"text": text[:4000], "source_lang": "EN", "target_lang": "KO"},
            headers={"Authorization": f"DeepL-Auth-Key {deepl_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        translations = (resp.json() or {}).get("translations") or []
        if translations:
            return str(translations[0].get("text") or text)
    except Exception as exc:
        logger.debug("DeepL 설명 번역 실패: %s", exc)
    return text


def _json_ld(analysis: Dict[str, Any]) -> Dict[str, Any]:
    if not _JSONLD_PRIORITY:
        return {}
    return analysis.get("json_ld_normalized") or {}


def _sorted_unique(values: List[str]) -> List[str]:
    return sorted(dict.fromkeys(v for v in values if v))


def build_listing_content(
    analysis: Dict[str, Any],
    market: str,
    language: str = _DEFAULT_LANGUAGE,
) -> Dict[str, Any]:
    json_ld = _json_ld(analysis)
    og_tags = ((analysis.get("_debug") or {}).get("og_tags") or {})
    variants = extract_variants(json_ld.get("hasVariant", [])) or analysis.get("variants") or []
    colors = _sorted_unique(
        [str(v.get("color") or "").strip() for v in variants] + list(analysis.get("colors") or [])
    )
    sizes = _sorted_unique(
        [str(v.get("size") or "").strip() for v in variants] + list(analysis.get("size_options") or [])
    )
    category_text = normalize_display_category(
        str(json_ld.get("category") or analysis.get("category") or "").strip()
    )
    description_source = str(
        json_ld.get("description") or analysis.get("source_description") or analysis.get("description") or ""
    ).strip()
    description_kr = _translate_to_korean(description_source)
    title_source = str(
        json_ld.get("name") or og_tags.get("title") or analysis.get("_scraped_title") or analysis.get("title") or ""
    ).strip()
    if not title_source:
        title_source = _generate_title_mock(analysis, market, 300, language)
    brand_source = str(
        (json_ld.get("brand") or {}).get("name") or analysis.get("brand") or ""
    ).strip()
    material = extract_material(description_source) or ", ".join(analysis.get("materials") or [])
    tags = list(analysis.get("keywords") or [])
    for extra in [category_text, brand_source, material] + colors + sizes:
        if extra and extra not in tags and len(tags) < 10:
            tags.append(extra)
    return {
        "title": title_source,
        "brand": brand_source,
        "category_text": category_text,
        "variants": variants,
        "colors": colors,
        "sizes": sizes,
        "material": material,
        "description_original": description_source,
        "description_kr": description_kr,
        "description": description_kr if language == "kr" else description_source,
        "tags": tags[:10],
        "title_source": "jsonld" if json_ld.get("name") else ("og" if og_tags.get("title") else "ai"),
        "description_source": "jsonld" if json_ld.get("description") else "ai",
    }


# ── AI 제목 생성 ─────────────────────────────────────────────────────────────

def _generate_title_mock(analysis: dict, market: str, max_len: int, language: str) -> str:
    """mock 제목 생성 (API 미설정 시)."""
    brand = analysis.get("brand") or ""
    product_type = analysis.get("product_type", "상품")
    colors = "/".join(analysis.get("colors", [])[:2])
    kw = analysis.get("keywords", [])
    first_kw = kw[0] if kw else ""

    parts = [brand, product_type, colors, first_kw]
    title = " ".join(p for p in parts if p).strip()
    if language == "jp":
        title = f"{brand} {product_type} {colors}".strip() if brand else f"{product_type} {colors}".strip()

    return _trim_to_max_len(title or product_type, max_len)


def _call_llm_title(prompt: str) -> str:
    """LLM 호출해서 제목 생성."""
    provider = os.getenv("AI_LISTING_VISION_PROVIDER", "mock")
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        try:
            import openai  # type: ignore
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            resp = client.chat.completions.create(
                model=os.getenv("AI_LISTING_VISION_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("OpenAI 제목 생성 실패: %s", exc)
    elif provider == "claude" and os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model=os.getenv("AI_LISTING_CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip() if resp.content else ""
        except Exception as exc:
            logger.warning("Claude 제목 생성 실패: %s", exc)
    return ""


# ── 퍼블릭 API ───────────────────────────────────────────────────────────────

def generate_title(
    analysis: Dict[str, Any],
    market: str,
    language: str = _DEFAULT_LANGUAGE,
) -> str:
    """마켓별 상품 제목 생성.

    Args:
        analysis:  analyzer.analyze_image() 반환 결과
        market:    대상 마켓 (coupang | smartstore | 11st | gmarket)
        language:  언어 (kr | jp | both)

    Returns:
        제목 문자열 (글자수 제한 준수 + 금칙어 제거)
    """
    from src.ai_listing.templates_prompts import get_market_config, build_title_prompt

    config = get_market_config(market, language)
    max_len = config.title_max_len
    forbidden = config.forbidden_terms

    listing = build_listing_content(analysis, market, language)
    if listing.get("title"):
        return _filter_forbidden_terms(
            _trim_to_max_len(str(listing["title"]), max_len),
            forbidden,
        )

    provider = os.getenv("AI_LISTING_VISION_PROVIDER", "mock")
    if provider != "mock" and (
        os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    ):
        prompt = build_title_prompt(analysis, market, max_len, language)
        raw = _call_llm_title(prompt)
        if raw:
            cleaned = _filter_forbidden_terms(raw, forbidden)
            return _trim_to_max_len(cleaned, max_len)

    # fallback: mock
    title = _generate_title_mock(analysis, market, max_len, language)
    return _filter_forbidden_terms(title, forbidden)


def generate_titles_for_markets(
    analysis: Dict[str, Any],
    markets: List[str],
    language: str = _DEFAULT_LANGUAGE,
) -> Dict[str, str]:
    """여러 마켓에 대한 제목 일괄 생성."""
    return {market: generate_title(analysis, market, language) for market in markets}


def generate_description(
    analysis: Dict[str, Any],
    market: str,
    language: str = _DEFAULT_LANGUAGE,
) -> str:
    """마켓별 상품 설명 생성."""
    listing = build_listing_content(analysis, market, language)
    if listing.get("description"):
        return str(listing["description"])

    from src.ai_listing.templates_prompts import build_description_prompt

    provider = os.getenv("AI_LISTING_VISION_PROVIDER", "mock")
    if provider != "mock" and (
        os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    ):
        prompt = build_description_prompt(analysis, market, language)
        text = _call_llm_title(prompt)
        if text:
            return text

    # mock 설명
    features = analysis.get("features", [])
    materials = ", ".join(analysis.get("materials", []))
    product_type = analysis.get("product_type", "상품")
    desc_parts = [f"✨ {product_type}"]
    if materials:
        desc_parts.append(f"소재: {materials}")
    for f in features[:3]:
        desc_parts.append(f"✔ {f}")
    if language == "jp":
        desc_parts = [f"✨ {product_type}（{market}）"] + [
            f"✔ {f}" for f in features[:3]
        ]
    return "\n".join(desc_parts)


def generate_tags(
    analysis: Dict[str, Any],
    language: str = _DEFAULT_LANGUAGE,
    max_tags: int = 10,
) -> List[str]:
    """태그/키워드 생성."""
    listing = build_listing_content(analysis, "coupang", language)
    if listing.get("tags"):
        return list(listing["tags"])[:max_tags]

    keywords = analysis.get("keywords", [])
    category = analysis.get("category", "")
    product_type = analysis.get("product_type", "")
    colors = analysis.get("colors", [])

    tags: List[str] = list(keywords[:max_tags])

    # 부족하면 카테고리/색상/상품유형으로 보충
    extras = [category, product_type] + colors
    for extra in extras:
        if extra and extra not in tags and len(tags) < max_tags:
            tags.append(extra)

    return tags[:max_tags]
