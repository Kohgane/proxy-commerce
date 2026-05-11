"""src/ai_listing — AI 상품등록 자동화 패키지 (Phase 149).

이미지 1~5장 → Vision AI 분석 → 마켓별 제목/설명/카테고리/가격/태그 생성 → 동시 등록.

서브모듈:
  analyzer          — 이미지 Vision API 분석
  generator         — 제목/설명/태그 생성 (마켓별 제약)
  category_mapper   — 마켓별 카테고리 코드 매핑
  price_suggester   — Phase 140/142 연동 가격 제안
  multi_publisher   — 멀티마켓 동시 등록
  templates_prompts — 프롬프트 템플릿
  routes            — Flask Blueprint (/seller/listing/ai-create, /api/ai-listing/*)
"""
from __future__ import annotations

AI_LISTING_VERSION = "149.0.0"
