"""src/ai_listing/templates_prompts.py — 프롬프트 템플릿 (Phase 149/150).

마켓별 제목/설명 생성 제약조건 및 Vision 분석 프롬프트.
Phase 150: v2 명시적 필드 추출 프롬프트 + 스크래핑 컨텍스트 주입.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── 마켓별 제목 글자수 제한 ──────────────────────────────────────────────────

MARKET_TITLE_MAX_LEN: Dict[str, int] = {
    "coupang": 50,
    "smartstore": 100,
    "11st": 100,
    "gmarket": 80,
}

# ── 마켓별 금칙어 목록 (기본) ────────────────────────────────────────────────

MARKET_FORBIDDEN_TERMS: Dict[str, List[str]] = {
    "coupang": ["최저가", "100%", "무조건", "보장"],
    "smartstore": ["최저가", "최고", "1위", "보장"],
    "11st": ["최저가", "보장", "무조건"],
    "gmarket": ["최저가", "100%"],
}


@dataclass
class MarketPromptConfig:
    """마켓별 프롬프트 설정."""

    market: str
    title_max_len: int
    forbidden_terms: List[str] = field(default_factory=list)
    language: str = "kr"  # kr | jp | both


def get_market_config(market: str, language: str = "kr") -> MarketPromptConfig:
    """마켓 설정 반환."""
    return MarketPromptConfig(
        market=market,
        title_max_len=MARKET_TITLE_MAX_LEN.get(market, 100),
        forbidden_terms=MARKET_FORBIDDEN_TERMS.get(market, []),
        language=language,
    )


# ── Vision 분석 프롬프트 ─────────────────────────────────────────────────────

VISION_ANALYSIS_PROMPT = """
이 상품 이미지를 분석해서 다음 정보를 JSON으로 반환하세요:

{
  "category": "상품 카테고리 (예: 전자기기, 패션, 뷰티, 식품, 스포츠, 가구/인테리어, 주방용품, 반려동물, 건강식품)",
  "brand": "브랜드명 (알 수 없으면 null)",
  "colors": ["주요 색상 목록"],
  "materials": ["소재 목록 (알 수 없으면 빈 리스트)"],
  "keywords": ["핵심 키워드 5~10개"],
  "estimated_price_range": {"min": 최저가(원), "max": 최고가(원)},
  "product_type": "상품 유형 (예: 티셔츠, 스마트폰 케이스, 스킨케어 세트 등)",
  "features": ["주요 특징 3~5개"]
}

응답은 JSON만 반환하세요.
""".strip()


VISION_ANALYSIS_PROMPT_JP = """
この商品画像を分析して、以下の情報をJSONで返してください:

{
  "category": "商品カテゴリ",
  "brand": "ブランド名 (不明の場合はnull)",
  "colors": ["主な色のリスト"],
  "materials": ["素材リスト"],
  "keywords": ["キーワード5~10個"],
  "estimated_price_range": {"min": 最低価格(円), "max": 最高価格(円)},
  "product_type": "商品タイプ",
  "features": ["主な特徴3~5個"]
}

JSONのみ返してください。
""".strip()


# ── v2 프롬프트 (Phase 150: 명시적 필드 + 스크래핑 컨텍스트) ────────────────

VISION_ANALYSIS_PROMPT_V2 = """
다음 정보를 JSON으로 추출하라:

{{
  "title": "상품 제목 (50자 이내, 마켓 등록용)",
  "brand": "브랜드명 (없으면 빈 문자열)",
  "material": "소재 (예: 면100%, 폴리에스터65%+면35%)",
  "colors": ["색상 리스트"],
  "size_options": ["사이즈 옵션 리스트"],
  "origin_country": "원산지 (없으면 null)",
  "category_path": "카테고리 경로 (예: 패션 > 남성의류 > 티셔츠)",
  "target_audience": "타겟 고객 (예: 20-30대 남성)",
  "suggested_price_krw": 추천 가격 정수 (원화),
  "description": "상품 설명 200자 이내 마케팅 카피",
  "keywords": ["검색 키워드 10개"],
  "category": "상위 카테고리",
  "estimated_price_range": {{"min": 최저가, "max": 최고가}},
  "product_type": "상품 유형",
  "features": ["주요 특징 3~5개"]
}}

스크래핑된 정보:
{scraper_output}

이미지: [첨부]

응답은 JSON만 반환하세요.
""".strip()

VISION_ANALYSIS_PROMPT_V2_JP = """
以下の情報をJSONで抽出してください:

{{
  "title": "商品タイトル（50文字以内）",
  "brand": "ブランド名（なければ空文字）",
  "material": "素材",
  "colors": ["色リスト"],
  "size_options": ["サイズオプション"],
  "origin_country": "原産国（なければnull）",
  "category_path": "カテゴリパス（例: ファッション > メンズ > Tシャツ）",
  "target_audience": "ターゲット顧客",
  "suggested_price_jpy": 推奨価格（整数、円）,
  "description": "商品説明200文字以内",
  "keywords": ["キーワード10個"],
  "category": "上位カテゴリ",
  "estimated_price_range": {{"min": 最低価格, "max": 最高価格}},
  "product_type": "商品タイプ",
  "features": ["主な特徴3~5個"]
}}

スクレイピング情報:
{scraper_output}

画像: [添付]

JSONのみ返してください。
""".strip()


def build_v2_analysis_prompt(
    language: str = "kr",
    scrape_data: Optional[dict] = None,
) -> str:
    """v2 분석 프롬프트 생성 (스크래핑 컨텍스트 포함).

    Args:
        language:    분석 언어 kr | jp | both
        scrape_data: url_scraper 결과 dict (없으면 빈 컨텍스트)

    Returns:
        완성된 프롬프트 문자열
    """
    import json as _json

    if scrape_data:
        # AI 프롬프트에 전달할 컨텍스트만 추려서 직렬화
        context = {
            "title": scrape_data.get("title", ""),
            "description": scrape_data.get("description", ""),
            "price_candidates": scrape_data.get("price_candidates", []),
            "brand_candidates": scrape_data.get("brand_candidates", []),
            "material_candidates": scrape_data.get("material_candidates", []),
            "size_candidates": scrape_data.get("size_candidates", []),
            "color_candidates": scrape_data.get("color_candidates", []),
            "origin_country": scrape_data.get("origin_country"),
            "raw_text": scrape_data.get("raw_text_truncated", "")[:1000],
        }
        scraper_output = _json.dumps(context, ensure_ascii=False, indent=2)
    else:
        scraper_output = "(스크래핑 없음 — 이미지만으로 분석)"

    if language == "jp":
        return VISION_ANALYSIS_PROMPT_V2_JP.format(scraper_output=scraper_output)
    return VISION_ANALYSIS_PROMPT_V2.format(scraper_output=scraper_output)


# ── 제목/설명 생성 프롬프트 ──────────────────────────────────────────────────

def build_title_prompt(
    analysis: dict,
    market: str,
    max_len: int,
    language: str = "kr",
) -> str:
    """마켓별 제목 생성 프롬프트."""
    category = analysis.get("category", "")
    product_type = analysis.get("product_type", "")
    keywords = ", ".join(analysis.get("keywords", [])[:5])
    colors = ", ".join(analysis.get("colors", [])[:3])
    brand = analysis.get("brand") or ""
    forbidden = ", ".join(MARKET_FORBIDDEN_TERMS.get(market, []))

    lang_instruction = "한국어로" if language in ("kr", "both") else "日本語で"

    return (
        f"{lang_instruction} {market} 마켓용 상품 제목을 생성하세요.\n"
        f"- 카테고리: {category}\n"
        f"- 상품 유형: {product_type}\n"
        f"- 브랜드: {brand}\n"
        f"- 색상: {colors}\n"
        f"- 키워드: {keywords}\n"
        f"- 최대 글자수: {max_len}자\n"
        f"- 금칙어(사용금지): {forbidden}\n"
        "제목 텍스트만 반환하세요."
    )


def build_description_prompt(
    analysis: dict,
    market: str,
    language: str = "kr",
) -> str:
    """마켓별 상세설명 생성 프롬프트."""
    category = analysis.get("category", "")
    product_type = analysis.get("product_type", "")
    features = "\n".join(f"- {f}" for f in analysis.get("features", []))
    materials = ", ".join(analysis.get("materials", []))
    keywords = ", ".join(analysis.get("keywords", []))

    lang_instruction = "한국어로" if language in ("kr", "both") else "日本語で"

    return (
        f"{lang_instruction} {market} 마켓용 상품 상세 설명을 500자 이내로 생성하세요.\n"
        f"- 카테고리: {category}\n"
        f"- 상품 유형: {product_type}\n"
        f"- 소재: {materials}\n"
        f"- 특징:\n{features}\n"
        f"- 키워드: {keywords}\n"
        "설명 텍스트만 반환하세요."
    )


def build_tags_prompt(analysis: dict, language: str = "kr") -> str:
    """태그/키워드 최적화 프롬프트."""
    keywords = ", ".join(analysis.get("keywords", []))
    category = analysis.get("category", "")
    lang_instruction = "한국어로" if language in ("kr", "both") else "日本語で"
    return (
        f"{lang_instruction} 상품 태그 10개를 쉼표로 구분해서 반환하세요.\n"
        f"- 카테고리: {category}\n"
        f"- 기존 키워드: {keywords}\n"
        "태그 목록만 반환하세요."
    )
