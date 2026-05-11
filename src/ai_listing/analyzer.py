"""src/ai_listing/analyzer.py — 이미지 Vision API 분석 (Phase 149).

입력: 이미지 URL 또는 업로드 bytes
호출: OpenAI Vision (gpt-4o-mini) 또는 Claude Sonnet (fallback)
출력: 카테고리, 색상, 소재, 추정 가격대, 키워드 리스트
캐시: 동일 이미지 해시 24h 재사용
비용 가드: BudgetGuard 통과 필수

환경변수:
  AI_LISTING_VISION_PROVIDER  openai | claude | mock
  AI_LISTING_VISION_MODEL     gpt-4o-mini
  AI_LISTING_CACHE_TTL_HOURS  24
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_VISION_PROVIDER = os.getenv("AI_LISTING_VISION_PROVIDER", "mock")
_VISION_MODEL = os.getenv("AI_LISTING_VISION_MODEL", "gpt-4o-mini")
_CACHE_TTL_SEC = int(os.getenv("AI_LISTING_CACHE_TTL_HOURS", "24")) * 3600

# 인메모리 캐시 (동일 프로세스 내)
_analysis_cache: Dict[str, Dict[str, Any]] = {}


def _compute_image_hash(image_url: str = "", image_bytes: bytes = b"") -> str:
    """이미지 해시 (URL 또는 bytes)."""
    if image_bytes:
        return hashlib.sha256(image_bytes).hexdigest()
    return hashlib.sha256(image_url.encode()).hexdigest()


def _mock_analysis() -> Dict[str, Any]:
    """Vision API 미설정 시 반환하는 mock 분석 결과."""
    return {
        "category": "패션",
        "brand": None,
        "colors": ["화이트", "블랙"],
        "materials": ["면", "폴리에스터"],
        "keywords": ["티셔츠", "기본", "데일리", "루즈핏", "캐주얼"],
        "estimated_price_range": {"min": 15000, "max": 45000},
        "product_type": "티셔츠",
        "features": ["기본 라운드넥", "루즈핏 실루엣", "올데이 착용 가능"],
        "_mock": True,
    }


def _call_openai_vision(image_url: str, prompt: str) -> Dict[str, Any]:
    """OpenAI Vision API 호출."""
    try:
        import openai  # type: ignore

        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            max_tokens=800,
        )
        text = resp.choices[0].message.content or "{}"
        # JSON 파싱
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return json.loads(text)
    except Exception as exc:
        logger.warning("OpenAI Vision 호출 실패: %s", exc)
        raise


def _call_claude_vision(image_url: str, prompt: str) -> Dict[str, Any]:
    """Anthropic Claude Vision API 호출 (fallback)."""
    try:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model=os.getenv("AI_LISTING_CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
            max_tokens=800,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": image_url},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text = resp.content[0].text if resp.content else "{}"
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return json.loads(text)
    except Exception as exc:
        logger.warning("Claude Vision 호출 실패: %s", exc)
        raise


def analyze_image(
    image_url: str = "",
    image_bytes: bytes = b"",
    language: str = "kr",
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """이미지 분석 진입점.

    Args:
        image_url:     분석할 이미지 URL
        image_bytes:   업로드된 이미지 bytes (URL 대신 사용)
        language:      분석 언어 kr | jp | both
        force_refresh: True 시 캐시 무시

    Returns:
        분석 결과 dict (category, brand, colors, materials, keywords 등)
    """
    from src.ai.budget import BudgetGuard, BudgetExceededError

    if not image_url and not image_bytes:
        return {"error": "이미지 URL 또는 bytes 필요", "category": "기타"}

    img_hash = _compute_image_hash(image_url=image_url, image_bytes=image_bytes)

    # 캐시 확인
    if not force_refresh and img_hash in _analysis_cache:
        cached = _analysis_cache[img_hash]
        if time.time() - cached.get("_cached_at", 0) < _CACHE_TTL_SEC:
            logger.debug("이미지 분석 캐시 히트: %s", img_hash[:8])
            return cached["result"]

    # mock 모드
    if _VISION_PROVIDER == "mock" or (
        not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY")
    ):
        result = _mock_analysis()
        _analysis_cache[img_hash] = {"result": result, "_cached_at": time.time()}
        return result

    # 예산 가드
    try:
        guard = BudgetGuard()
        guard.check()
    except BudgetExceededError as exc:
        logger.warning("AI Vision 예산 초과 — mock 반환: %s", exc)
        return {**_mock_analysis(), "_budget_exceeded": True}
    except Exception as exc:
        logger.debug("BudgetGuard 확인 실패 (무시): %s", exc)

    from src.ai_listing.templates_prompts import VISION_ANALYSIS_PROMPT, VISION_ANALYSIS_PROMPT_JP

    prompt = VISION_ANALYSIS_PROMPT_JP if language == "jp" else VISION_ANALYSIS_PROMPT

    # image_bytes → data URI 변환 (URL이 없으면)
    if image_bytes and not image_url:
        import base64
        b64 = base64.b64encode(image_bytes).decode()
        image_url = f"data:image/jpeg;base64,{b64}"

    result: Optional[Dict[str, Any]] = None

    if _VISION_PROVIDER == "openai":
        try:
            result = _call_openai_vision(image_url, prompt)
        except Exception:
            if os.getenv("ANTHROPIC_API_KEY"):
                try:
                    result = _call_claude_vision(image_url, prompt)
                except Exception:
                    pass
    elif _VISION_PROVIDER == "claude":
        try:
            result = _call_claude_vision(image_url, prompt)
        except Exception:
            if os.getenv("OPENAI_API_KEY"):
                try:
                    result = _call_openai_vision(image_url, prompt)
                except Exception:
                    pass

    if result is None:
        result = _mock_analysis()

    # 캐시 저장
    _analysis_cache[img_hash] = {"result": result, "_cached_at": time.time()}
    return result


def cache_stats() -> Dict[str, Any]:
    """캐시 통계 반환."""
    now = time.time()
    total = len(_analysis_cache)
    active = sum(
        1
        for v in _analysis_cache.values()
        if now - v.get("_cached_at", 0) < _CACHE_TTL_SEC
    )
    return {"total": total, "active": active, "ttl_hours": _CACHE_TTL_SEC // 3600}
