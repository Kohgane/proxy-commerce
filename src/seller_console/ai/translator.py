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

    def generate_description(self, product: dict) -> dict:
        """v39-E2 #3: 상세설명이 없거나 빈약할 때 한국어 상세 '초안'을 생성.

        입력: {title, category, specs:[(label,value)], keywords, brand}
        출력: {"text": str, "provider": "openai"|"stub", "is_draft": True}
        - 큐레이터 톤(건방지지만 공손한 높임말). 없는 수치·허위 스펙 지어내기 금지(확인된 정보만).
        - OPENAI 키 미설정/dry-run/실패 시 provider="stub" — 가짜 상세 생성 금지, 확인된 정보만 구조화.
        """
        title = (product.get("title") or "").strip()
        category = (product.get("category") or "").strip()
        keywords = product.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        specs = product.get("specs") or []
        brand = (product.get("brand") or "").strip()

        if self.provider == "openai" and not _dry_run():
            try:
                return self._describe_openai(title, category, specs, keywords, brand)
            except Exception as exc:
                logger.warning("AI 상세 생성 실패, 정직 구조화로 폴백: %s", exc)

        # 정직 폴백: 확인된 정보(제목/스펙)만 구조화 — 없는 수치 날조 0.
        lines = []
        if title:
            lines.append(title)
        for label, value in specs[:20]:
            lines.append(f"- {label}: {value}")
        if not specs:
            lines.append("· 확인된 상세 정보가 부족합니다. 소재·사이즈·용도 등을 직접 입력해 주세요.")
        return {"text": "\n".join(lines).strip(), "provider": "stub", "is_draft": True}

    def _describe_openai(self, title, category, specs, keywords, brand) -> dict:
        import requests as _req
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        spec_txt = "\n".join(f"- {l}: {v}" for l, v in specs[:20]) or "(스펙 표 없음)"
        kw_txt = ", ".join(keywords[:15]) or "(없음)"
        # v39-E2 #3 + CLAUDE.md: humanizer 의도 적용 — 사람이 직접 쓴 것처럼(AI 티·번역체·과장 금지).
        prompt = (
            "다음 상품의 한국어 상세설명 '초안'을 작성하세요. "
            "사람이 직접 쓴 것처럼 자연스럽게 — AI 특유의 정형 문장·번역체·진부한 도입(\"여러분~\", \"~를 소개합니다\")·"
            "감탄 남발을 피하고, 짧고 구체적인 문장으로. "
            "톤: 건방지지 않게 공손하되 군더더기 없는 큐레이터 높임말. "
            "확인된 정보만 사용하고, 없는 수치·소재·인증·원산지 등은 절대 지어내지 마세요(모르면 쓰지 않음). "
            "구성: 도입 1문장 → 특징 3~5(불릿) → 사용/주의 1~2 → 마무리 1문장. "
            "마켓 금지어(최고/최상/유일/100%/완벽/의학·과학 효능 단정 등) 회피. "
            "이모지·해시태그 금지.\n\n"
            f"상품명: {title}\n브랜드: {brand or '(미상)'}\n카테고리: {category or '(미상)'}\n"
            f"스펙:\n{spec_txt}\n키워드: {kw_txt}\n"
        )
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.5},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return {"text": text, "provider": "openai", "is_draft": True}

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
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
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
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
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
