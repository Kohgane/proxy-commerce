"""src/seller_console/ai/translator.py — 상품 번역 + 마켓별 광고 카피 자동 생성 (Phase 130).

우선순위:
1. OPENAI_API_KEY 활성 → GPT-4o-mini 사용
2. DEEPL_API_KEY 활성 → DeepL (번역만, 카피는 template 기반)
3. 둘 다 없음 → 원본 반환 + warning 로그

ADAPTER_DRY_RUN=1 시 실 API 호출 차단.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 마켓별 카피 톤앤매너 프롬프트 힌트
_MARKET_PROMPTS = {
    "coupang": "핵심 키워드 6개 + bullet list 형식. 간결하고 직접적.",
    "smartstore": "SEO 친화적. 상세 설명. 검색 키워드 포함. 신뢰감 강조.",
    "11st": "짧고 임팩트 있게. 가격 메리트와 특징 강조.",
}


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


class AITranslator:
    """상품 메타데이터 → 한국어 번역 + 마켓별 광고 카피 생성."""

    def __init__(self) -> None:
        self.provider = self._select_provider()
        logger.info("AITranslator 초기화: provider=%s", self.provider)

    def _select_provider(self) -> str:
        """사용 가능한 AI 프로바이더 선택."""
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        if os.getenv("DEEPL_API_KEY"):
            return "deepl"
        return "stub"

    def translate_product(self, source: dict) -> dict:
        """상품 메타데이터를 한국어로 번역하고 마켓별 카피 생성.

        Args:
            source: {"title": str, "description": str, ...}

        Returns:
            {
              "title_ko": str,
              "description_ko": str,
              "copy_coupang": str,
              "copy_smartstore": str,
              "copy_11st": str,
              "provider": str,
            }
        """
        title = source.get("title", "")
        description = source.get("description", "")

        if self.provider == "openai" and not _dry_run():
            return self._translate_openai(title, description)
        if self.provider == "deepl" and not _dry_run():
            return self._translate_deepl(title, description)

        # stub / dry-run
        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — AITranslator stub 모드")
        else:
            logger.warning("AI 번역 키 미설정 — 원본 반환 (stub 모드)")

        return {
            "title_ko": title,
            "description_ko": description,
            "copy_coupang": f"[stub] {title}",
            "copy_smartstore": f"[stub] {title}",
            "copy_11st": f"[stub] {title}",
            "provider": "stub",
        }

    def generate_marketplace_copy(self, product: dict, marketplace: str) -> str:
        """마켓별 톤앤매너에 맞는 광고 카피 생성.

        Args:
            product: {"title": str, "description": str, ...}
            marketplace: "coupang" | "smartstore" | "11st"

        Returns:
            광고 카피 문자열
        """
        title = product.get("title", "")
        hint = _MARKET_PROMPTS.get(marketplace, "간결하게 작성.")

        if self.provider == "openai" and not _dry_run():
            return self._copy_openai(title, marketplace, hint)
        if self.provider == "deepl" and not _dry_run():
            # DeepL은 번역만 지원 — 카피는 template 기반
            return self._copy_template(title, marketplace)

        return self._copy_template(title, marketplace)

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _translate_openai(self, title: str, description: str) -> dict:
        """OpenAI GPT-4o-mini로 번역 + 카피 생성."""
        try:
            import requests as _req
            api_key = os.getenv("OPENAI_API_KEY", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            prompt = (
                "다음 상품 정보를 한국어로 번역하고, 각 마켓용 광고 카피를 생성하세요.\n"
                f"제목: {title}\n설명: {description}\n\n"
                "JSON 형식으로만 답변:\n"
                '{"title_ko":"...","description_ko":"...","copy_coupang":"...","copy_smartstore":"...","copy_11st":"..."}'
            )
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 800,
                "response_format": {"type": "json_object"},
            }
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            import json
            result = json.loads(content)
            result["provider"] = "openai"
            return result
        except Exception as exc:
            logger.warning("OpenAI 번역 실패, stub으로 폴백: %s", exc)
            return {
                "title_ko": title,
                "description_ko": description,
                "copy_coupang": f"[openai-fallback] {title}",
                "copy_smartstore": f"[openai-fallback] {title}",
                "copy_11st": f"[openai-fallback] {title}",
                "provider": "openai-fallback",
            }

    def _translate_deepl(self, title: str, description: str) -> dict:
        """DeepL로 번역 (카피는 template 기반)."""
        try:
            import requests as _req
            api_key = os.getenv("DEEPL_API_KEY", "")
            base_url = (
                "https://api-free.deepl.com/v2/translate"
                if api_key.endswith(":fx")
                else "https://api.deepl.com/v2/translate"
            )
            params = {
                "auth_key": api_key,
                "text": [title, description],
                "target_lang": "KO",
            }
            resp = _req.post(base_url, data=params, timeout=10)
            resp.raise_for_status()
            translations = resp.json().get("translations", [])
            title_ko = translations[0]["text"] if len(translations) > 0 else title
            description_ko = translations[1]["text"] if len(translations) > 1 else description
            return {
                "title_ko": title_ko,
                "description_ko": description_ko,
                "copy_coupang": self._copy_template(title_ko, "coupang"),
                "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                "copy_11st": self._copy_template(title_ko, "11st"),
                "provider": "deepl",
            }
        except Exception as exc:
            logger.warning("DeepL 번역 실패, stub으로 폴백: %s", exc)
            return {
                "title_ko": title,
                "description_ko": description,
                "copy_coupang": f"[deepl-fallback] {title}",
                "copy_smartstore": f"[deepl-fallback] {title}",
                "copy_11st": f"[deepl-fallback] {title}",
                "provider": "deepl-fallback",
            }

    def _copy_openai(self, title: str, marketplace: str, hint: str) -> str:
        """OpenAI로 마켓별 카피 생성."""
        try:
            import requests as _req
            import json
            api_key = os.getenv("OPENAI_API_KEY", "")
            prompt = f"상품명: {title}\n마켓: {marketplace}\n조건: {hint}\n광고 카피 1개만 작성."
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 200,
            }
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OpenAI 카피 생성 실패: %s", exc)
            return self._copy_template(title, marketplace)

    @staticmethod
    def _copy_template(title: str, marketplace: str) -> str:
        """키 없을 때 template 기반 카피 생성."""
        templates = {
            "coupang": f"✅ {title} | 빠른 배송 | 최저가 보장 | 로켓배송 가능",
            "smartstore": (
                f"{title}\n"
                "정품 보장 · 당일 발송 · 무료 교환\n"
                "네이버 쇼핑 최저가 도전"
            ),
            "11st": f"[특가] {title} — 지금 구매하면 최대 할인!",
        }
        return templates.get(marketplace, f"{title} — 구매 추천")
