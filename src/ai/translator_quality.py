"""src/ai/translator_quality.py — 번역 품질 향상 (Phase 143).

기능:
  - 상품명: DeepL + GPT 후처리 (한국 쇼핑몰 톤)
  - 설명: 단락 단위 번역 + 키워드 보존
  - 사이즈/소재 등 사양 정규식 추출 → 한국어 표준 용어 매핑
  - 금칙어 검사 (의약품/허위과대 표현)

환경변수:
  TRANSLATION_QUALITY_TIER=high  품질 티어 (high/standard/fast)
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_QUALITY_TIER = os.getenv("TRANSLATION_QUALITY_TIER", "high")

# ---------------------------------------------------------------------------
# 사양 정규식 + 한국어 표준 용어 매핑
# ---------------------------------------------------------------------------

# 사이즈 패턴 → 한국어 레이블
_SPEC_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'(?i)size[:\s]*([A-Z0-9/\-\s,×x]+)'), "사이즈"),
    (re.compile(r'(?i)weight[:\s]*([\d.,]+\s*(?:kg|g|lb|oz))'), "무게"),
    (re.compile(r'(?i)material[:\s]*([^\n.;,]{3,50})'), "소재"),
    (re.compile(r'(?i)color[:\s]*([^\n.;,]{2,30})'), "색상"),
    (re.compile(r'(?i)dimensions?[:\s]*([\d.,]+\s*[×x]\s*[\d.,]+(?:\s*[×x]\s*[\d.,]+)?\s*(?:cm|mm|inch|in)?)'), "크기"),
    (re.compile(r'(?i)capacity[:\s]*([\d.,]+\s*(?:ml|l|L|mL))'), "용량"),
    (re.compile(r'(?i)voltage[:\s]*([\d.,]+\s*[Vv])'), "전압"),
    (re.compile(r'(?i)watts?[:\s]*([\d.,]+\s*[Ww])'), "와트"),
]

# 소재명 영어 → 한국어
_MATERIAL_MAP: Dict[str, str] = {
    "cotton": "면",
    "polyester": "폴리에스터",
    "nylon": "나일론",
    "wool": "울",
    "cashmere": "캐시미어",
    "silk": "실크",
    "linen": "리넨",
    "leather": "가죽",
    "suede": "스웨이드",
    "stainless steel": "스테인레스 스틸",
    "aluminum": "알루미늄",
    "aluminium": "알루미늄",
    "plastic": "플라스틱",
    "rubber": "고무",
    "silicone": "실리콘",
    "glass": "유리",
    "ceramic": "세라믹",
    "canvas": "캔버스",
    "denim": "데님",
    "fleece": "플리스",
    "down": "다운",
    "spandex": "스판덱스",
}

# 색상명 영어 → 한국어
_COLOR_MAP: Dict[str, str] = {
    "black": "블랙",
    "white": "화이트",
    "red": "레드",
    "blue": "블루",
    "navy": "네이비",
    "green": "그린",
    "yellow": "옐로우",
    "pink": "핑크",
    "purple": "퍼플",
    "gray": "그레이",
    "grey": "그레이",
    "brown": "브라운",
    "beige": "베이지",
    "orange": "오렌지",
    "gold": "골드",
    "silver": "실버",
    "ivory": "아이보리",
    "khaki": "카키",
    "mint": "민트",
    "coral": "코럴",
    "burgundy": "버건디",
    "charcoal": "차콜",
}

# 일본어 → 한국어 쇼핑몰 용어 변환
_JA_KO_SHOPPING_MAP: Dict[str, str] = {
    "セール": "세일",
    "送料無料": "무료배송",
    "新品": "신품",
    "限定": "한정",
    "人気": "인기",
    "おすすめ": "추천",
    "高品質": "고품질",
    "大人気": "대인기",
    "特価": "특가",
    "割引": "할인",
    "ポイント": "포인트",
    "サイズ": "사이즈",
    "カラー": "컬러",
    "素材": "소재",
    "重量": "무게",
}


# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------

@dataclass
class TranslationResult:
    """번역 결과."""

    original: str
    translated: str
    source_lang: str
    quality_tier: str
    method: str   # "deepl" / "gpt" / "stub"
    forbidden_matches: List[Dict[str, str]] = field(default_factory=list)
    has_forbidden: bool = False
    spec: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original,
            "translated": self.translated,
            "source_lang": self.source_lang,
            "quality_tier": self.quality_tier,
            "method": self.method,
            "forbidden_matches": self.forbidden_matches,
            "has_forbidden": self.has_forbidden,
            "spec": self.spec,
        }


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------

def _extract_spec(text: str) -> Dict[str, str]:
    """정규식으로 사양 추출 → 한국어 표준 용어 매핑."""
    spec: Dict[str, str] = {}
    for pattern, label in _SPEC_PATTERNS:
        m = pattern.search(text)
        if m:
            value = m.group(1).strip()
            if label == "소재":
                lower = value.lower()
                for en, ko in _MATERIAL_MAP.items():
                    lower = lower.replace(en, ko)
                value = lower
            elif label == "색상":
                lower = value.lower()
                for en, ko in _COLOR_MAP.items():
                    lower = lower.replace(en, ko)
                value = lower
            spec[label] = value
    return spec


def _check_forbidden(text: str) -> List[Dict[str, str]]:
    """금칙어 검사."""
    matches: List[Dict[str, str]] = []
    try:
        from src.ai.forbidden_terms import check_forbidden_terms
        result = check_forbidden_terms(text)
        for m in result:
            matches.append({
                "term": m.term,
                "category": m.category,
                "suggestion": m.suggestion,
            })
    except Exception as exc:
        logger.debug("금칙어 검사 스킵: %s", exc)
    return matches


def _apply_ja_ko_shopping_map(text: str) -> str:
    """일본어 쇼핑몰 용어 직접 치환."""
    for ja, ko in _JA_KO_SHOPPING_MAP.items():
        text = text.replace(ja, ko)
    return text


def _call_deepl(text: str, source_lang: str = "JA", target_lang: str = "KO") -> Optional[str]:
    """DeepL API 호출 (DEEPL_API_KEY 없으면 None 반환)."""
    api_key = os.getenv("DEEPL_API_KEY", "")
    if not api_key:
        return None
    try:
        import urllib.request
        import urllib.parse
        import json
        params = urllib.parse.urlencode({
            "auth_key": api_key,
            "text": text,
            "source_lang": source_lang.upper(),
            "target_lang": target_lang.upper(),
        }).encode()
        req = urllib.request.Request(
            "https://api-free.deepl.com/v2/translate",
            data=params,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data["translations"][0]["text"]
    except Exception as exc:
        logger.debug("DeepL 호출 실패: %s", exc)
        return None


def _call_gpt_postprocess(text_ko: str, original_title: str) -> Optional[str]:
    """GPT 후처리 — 한국 쇼핑몰 톤으로 다듬기 (OPENAI_API_KEY 없으면 None 반환)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    try:
        import urllib.request
        import json
        payload = json.dumps({
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "당신은 한국 온라인 쇼핑몰 상품 제목/설명 전문가입니다. "
                        "번역된 상품 제목을 한국 쇼핑몰 감성에 맞게 간결하게 다듬어 주세요. "
                        "브랜드명은 영문 유지, 불필요한 조사/어미 제거, SEO 키워드 포함."
                    ),
                },
                {
                    "role": "user",
                    "content": f"원본: {original_title}\n번역: {text_ko}\n\n한국 쇼핑몰 제목으로 다듬기 (50자 이내):",
                },
            ],
            "max_tokens": 100,
            "temperature": 0.3,
        }).encode()

        from decimal import Decimal as _Decimal
        from src.ai.budget import BudgetGuard
        guard = BudgetGuard()
        if not guard.can_spend(estimated_cost_usd=_Decimal("0.001")):
            logger.debug("GPT 후처리 예산 초과 — 스킵")
            return None

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.debug("GPT 후처리 실패: %s", exc)
        return None


def _stub_translate_title(title: str, source_lang: str) -> str:
    """번역 API 없을 때 사용하는 stub 번역 (일본어 쇼핑몰 키워드 치환)."""
    # 일본어 쇼핑 키워드 치환
    result = _apply_ja_ko_shopping_map(title)
    # 간단한 괄호·슬래시 정제
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def _stub_translate_description(text: str) -> str:
    """설명 stub 번역."""
    if not text:
        return "상품 상세 정보는 이미지를 참고해 주세요."
    result = _apply_ja_ko_shopping_map(text)
    return re.sub(r'\s+', ' ', result).strip()


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def translate_title(title: str, source_lang: str = "JA") -> str:
    """상품명 번역: DeepL → GPT 후처리 → stub 폴백."""
    if not title:
        return ""

    method = "stub"
    translated = _stub_translate_title(title, source_lang)

    # DeepL 시도
    deepl_result = _call_deepl(title, source_lang=source_lang)
    if deepl_result:
        translated = deepl_result
        method = "deepl"

        # GPT 후처리 (high 티어일 때만)
        if _QUALITY_TIER == "high":
            gpt_result = _call_gpt_postprocess(translated, title)
            if gpt_result:
                translated = gpt_result
                method = "gpt"

    # 일본어 쇼핑 키워드 후처리
    translated = _apply_ja_ko_shopping_map(translated)
    logger.debug("translate_title: method=%s original=%s → %s", method, title[:30], translated[:30])
    return translated


def translate_description(text: str, source_lang: str = "JA") -> str:
    """설명 단락 단위 번역."""
    if not text:
        return _stub_translate_description(text)

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    translated_parts: List[str] = []
    for para in paragraphs:
        result = _call_deepl(para, source_lang=source_lang)
        if result:
            translated_parts.append(_apply_ja_ko_shopping_map(result))
        else:
            translated_parts.append(_stub_translate_description(para))

    return "\n\n".join(translated_parts) if translated_parts else _stub_translate_description(text)


def translate_and_check(
    title: str,
    description: str = "",
    source_lang: str = "JA",
) -> TranslationResult:
    """번역 + 사양 추출 + 금칙어 검사 통합 API."""
    translated_title = translate_title(title, source_lang)
    spec = _extract_spec(description or title)
    forbidden = _check_forbidden(translated_title)
    if not forbidden and description:
        forbidden = _check_forbidden(description)

    method = "stub"
    if os.getenv("DEEPL_API_KEY"):
        method = "deepl"
        if os.getenv("OPENAI_API_KEY") and _QUALITY_TIER == "high":
            method = "gpt"

    return TranslationResult(
        original=title,
        translated=translated_title,
        source_lang=source_lang,
        quality_tier=_QUALITY_TIER,
        method=method,
        forbidden_matches=forbidden,
        has_forbidden=bool(forbidden),
        spec=spec,
    )


def translator_stats() -> Dict[str, Any]:
    """번역 모듈 상태 (diagnostics 카드용)."""
    return {
        "quality_tier": _QUALITY_TIER,
        "deepl_configured": bool(os.getenv("DEEPL_API_KEY")),
        "gpt_configured": bool(os.getenv("OPENAI_API_KEY")),
        "material_map_size": len(_MATERIAL_MAP),
        "color_map_size": len(_COLOR_MAP),
        "spec_patterns": len(_SPEC_PATTERNS),
    }
