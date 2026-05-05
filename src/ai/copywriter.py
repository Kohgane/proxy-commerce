"""src/ai/copywriter.py — AI 카피라이터 본 구현 (Phase 134).

상품 메타 → 마켓별 한국어 카피 생성.
- OpenAI 우선 (gpt-4o-mini 기본, OPENAI_MODEL env로 변경)
- DeepL 폴백 (번역만)
- 캐시: Sheets `ai_cache` 워크시트
- 예산 관리: AI_MONTHLY_BUDGET_USD 초과 시 차단 + 텔레그램 알림
- ADAPTER_DRY_RUN=1 시 샘플 응답 반환
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# 마켓별 프롬프트 파일 이름
_MARKET_PROMPT_FILES = {
    "coupang": "coupang.txt",
    "smartstore": "smartstore.txt",
    "11st": "11st.txt",
    "wc": "wc.txt",
    "woocommerce": "wc.txt",
    "default": "default.txt",
}


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _load_prompt(marketplace: Optional[str]) -> str:
    """마켓별 프롬프트 파일 로드."""
    fname = _MARKET_PROMPT_FILES.get(marketplace or "default", "default.txt")
    prompt_file = _PROMPTS_DIR / fname
    try:
        return prompt_file.read_text(encoding="utf-8")
    except Exception:
        default_file = _PROMPTS_DIR / "default.txt"
        try:
            return default_file.read_text(encoding="utf-8")
        except Exception:
            return "상품 카피를 작성해주세요. JSON 형식으로 반환."


@dataclass
class CopyRequest:
    """카피 생성 요청."""

    title: str
    source_lang: str = "en"
    target_lang: str = "ko"
    description: str = ""
    images: List[str] = field(default_factory=list)
    brand: Optional[str] = None
    category: Optional[str] = None
    marketplace: Optional[str] = None  # coupang/smartstore/11st/wc
    price_krw: Optional[int] = None
    variants: int = 1  # A/B 카피 변형 수

    def cache_key(self) -> str:
        """캐시 키 생성 (요청 내용 해시)."""
        raw = json.dumps({
            "title": self.title,
            "description": self.description[:200],
            "brand": self.brand,
            "marketplace": self.marketplace,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
        }, ensure_ascii=False, sort_keys=True)
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        market = self.marketplace or "default"
        return f"copy_{market}_{h}"


@dataclass
class CopyResult:
    """카피 생성 결과."""

    title_ko: str
    bullet_points: List[str]
    description_html: str
    keywords: List[str]
    seo_meta_title: str
    seo_meta_desc: str
    forbidden_terms_warnings: List[str]
    tokens_used: int
    cost_usd: Decimal
    cached: bool
    provider: str  # openai / deepl / stub
    variant_index: int = 0

    def to_dict(self) -> dict:
        return {
            "title_ko": self.title_ko,
            "bullet_points": self.bullet_points,
            "description_html": self.description_html,
            "keywords": self.keywords,
            "seo_meta_title": self.seo_meta_title,
            "seo_meta_desc": self.seo_meta_desc,
            "forbidden_terms_warnings": self.forbidden_terms_warnings,
            "tokens_used": self.tokens_used,
            "cost_usd": str(self.cost_usd),
            "cached": self.cached,
            "provider": self.provider,
            "variant_index": self.variant_index,
        }


# ---------------------------------------------------------------------------
# 스텁 결과 생성 (dry-run 또는 키 없음)
# ---------------------------------------------------------------------------

def _stub_result(req: CopyRequest, variant_index: int = 0) -> CopyResult:
    title = req.title
    market = req.marketplace or "default"
    return CopyResult(
        title_ko=f"[stub] {title}",
        bullet_points=[
            f"[stub] {title} - 핵심 특징 1",
            f"[stub] {title} - 핵심 특징 2",
            f"[stub] {title} - 핵심 특징 3",
        ],
        description_html=f"<p>[stub] {title} 상품 설명입니다. 마켓: {market}</p>",
        keywords=[title, market, "상품", "추천"],
        seo_meta_title=f"[stub] {title} | {market}",
        seo_meta_desc=f"[stub] {title} 구매하기. 최고의 가격과 품질.",
        forbidden_terms_warnings=[],
        tokens_used=0,
        cost_usd=Decimal("0"),
        cached=False,
        provider="stub",
        variant_index=variant_index,
    )


# ---------------------------------------------------------------------------
# OpenAI 호출
# ---------------------------------------------------------------------------

def _call_openai(req: CopyRequest, variant_index: int = 0) -> CopyResult:
    """OpenAI API로 카피 생성."""
    import requests as _req

    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt_instructions = _load_prompt(req.marketplace)

    system_prompt = (
        "당신은 한국 이커머스 전문 카피라이터입니다. "
        "상품 정보를 받아 지정된 마켓에 최적화된 한국어 카피를 작성합니다. "
        "반드시 JSON 형식으로만 응답하세요.\n\n"
        f"마켓별 작성 지침:\n{prompt_instructions}"
    )

    variant_hint = f"\n\n※ 변형 #{variant_index + 1}: 다른 표현 방식으로 작성해주세요." if variant_index > 0 else ""

    brand_info = f"브랜드: {req.brand}\n" if req.brand else ""
    category_info = f"카테고리: {req.category}\n" if req.category else ""
    price_info = f"가격: {req.price_krw:,}원\n" if req.price_krw else ""

    user_content = (
        f"원문 언어: {req.source_lang}\n"
        f"{brand_info}{category_info}{price_info}"
        f"상품명: {req.title}\n"
        f"상품 설명: {req.description[:500] if req.description else '없음'}\n"
        f"마켓: {req.marketplace or 'default'}{variant_hint}\n\n"
        "위 상품 정보로 한국어 카피를 작성해주세요."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7 + variant_index * 0.1,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }

    resp = _req.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    tokens = usage.get("total_tokens", 0)
    # gpt-4o-mini 가격: input $0.15/1M, output $0.60/1M (2024년 기준 근사치)
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    cost_usd = Decimal(str(input_tokens)) * Decimal("0.00000015") + Decimal(str(output_tokens)) * Decimal("0.0000006")

    content = data["choices"][0]["message"]["content"]
    try:
        result_data = json.loads(content)
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 부분 파싱 시도
        result_data = {}

    title_ko = result_data.get("title_ko") or f"[번역] {req.title}"
    bullet_points = result_data.get("bullet_points") or []
    if isinstance(bullet_points, list):
        bullet_points = [str(b) for b in bullet_points[:6]]
    else:
        bullet_points = []

    return CopyResult(
        title_ko=title_ko,
        bullet_points=bullet_points,
        description_html=result_data.get("description_html") or f"<p>{title_ko}</p>",
        keywords=result_data.get("keywords") or [],
        seo_meta_title=result_data.get("seo_meta_title") or title_ko,
        seo_meta_desc=result_data.get("seo_meta_desc") or "",
        forbidden_terms_warnings=[],
        tokens_used=tokens,
        cost_usd=cost_usd,
        cached=False,
        provider="openai",
        variant_index=variant_index,
    )


# ---------------------------------------------------------------------------
# DeepL 폴백 (번역만)
# ---------------------------------------------------------------------------

def _call_deepl(req: CopyRequest, variant_index: int = 0) -> CopyResult:
    """DeepL로 번역 (카피는 template 기반)."""
    import requests as _req

    api_key = os.getenv("DEEPL_API_KEY", "")
    base_url = (
        "https://api-free.deepl.com/v2/translate"
        if api_key.endswith(":fx")
        else "https://api.deepl.com/v2/translate"
    )

    texts = [req.title]
    if req.description:
        texts.append(req.description[:300])

    params = {
        "auth_key": api_key,
        "text": texts,
        "source_lang": req.source_lang.upper(),
        "target_lang": "KO",
    }
    resp = _req.post(base_url, data=params, timeout=10)
    resp.raise_for_status()
    translations = resp.json().get("translations", [])
    title_ko = translations[0]["text"] if translations else req.title
    desc_ko = translations[1]["text"] if len(translations) > 1 else req.description

    market = req.marketplace or "default"
    return CopyResult(
        title_ko=title_ko,
        bullet_points=[
            f"{title_ko} - 특징 1",
            f"{title_ko} - 특징 2",
            f"{title_ko} - 특징 3",
        ],
        description_html=f"<p>{desc_ko}</p>" if desc_ko else f"<p>{title_ko}</p>",
        keywords=[title_ko, market],
        seo_meta_title=f"{title_ko} | {market}",
        seo_meta_desc=f"{title_ko} 구매하기.",
        forbidden_terms_warnings=[],
        tokens_used=0,
        cost_usd=Decimal("0.002"),  # DeepL 근사 비용
        cached=False,
        provider="deepl",
        variant_index=variant_index,
    )


# ---------------------------------------------------------------------------
# 메인 클래스
# ---------------------------------------------------------------------------

class AICopywriter:
    """AI 카피라이터 메인 클래스."""

    def __init__(self) -> None:
        from src.ai.cache import AICache
        from src.ai.budget import BudgetGuard

        self.cache = AICache()
        self.budget = BudgetGuard()
        self.provider = self._select_provider()
        logger.info("AICopywriter 초기화: provider=%s", self.provider)

    def _select_provider(self) -> str:
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        if os.getenv("DEEPL_API_KEY"):
            return "deepl_only"
        return "stub"

    def generate(self, req: CopyRequest) -> List[CopyResult]:
        """A/B 변형 N개 생성.

        캐시 hit 시 재호출 없이 즉시 반환.

        Args:
            req: CopyRequest 객체

        Returns:
            CopyResult 목록 (req.variants 개수)

        Raises:
            BudgetExceededError: 월 예산 초과
        """
        cache_key = req.cache_key()

        # 캐시 조회
        cached_raw = self.cache.get(cache_key)
        if cached_raw:
            logger.info("ai_cache hit: %s", cache_key)
            try:
                results = []
                for item in cached_raw:
                    r = CopyResult(
                        title_ko=item["title_ko"],
                        bullet_points=item.get("bullet_points", []),
                        description_html=item.get("description_html", ""),
                        keywords=item.get("keywords", []),
                        seo_meta_title=item.get("seo_meta_title", ""),
                        seo_meta_desc=item.get("seo_meta_desc", ""),
                        forbidden_terms_warnings=item.get("forbidden_terms_warnings", []),
                        tokens_used=int(item.get("tokens_used", 0)),
                        cost_usd=Decimal(str(item.get("cost_usd", "0"))),
                        cached=True,
                        provider=item.get("provider", "cached"),
                        variant_index=int(item.get("variant_index", 0)),
                    )
                    results.append(r)
                if results:
                    return results
            except Exception as exc:
                logger.warning("캐시 파싱 오류, 재생성: %s", exc)

        # dry-run 처리
        if _dry_run():
            results = [_stub_result(req, v) for v in range(req.variants)]
            return results

        # 예산 확인
        estimated = Decimal("0.05") * req.variants
        if not self.budget.can_spend(estimated):
            from src.ai.budget import BudgetExceededError
            raise BudgetExceededError(self.budget.summary())

        # 생성
        results = []
        total_cost = Decimal("0")
        total_tokens = 0

        for v in range(req.variants):
            try:
                if self.provider == "openai":
                    r = _call_openai(req, variant_index=v)
                elif self.provider == "deepl_only":
                    r = _call_deepl(req, variant_index=v)
                else:
                    r = _stub_result(req, variant_index=v)
            except Exception as exc:
                logger.warning("카피 생성 오류 (variant=%d): %s", v, exc)
                # 실패 시 DeepL 폴백
                if self.provider == "openai" and os.getenv("DEEPL_API_KEY"):
                    try:
                        r = _call_deepl(req, variant_index=v)
                    except Exception as exc2:
                        logger.warning("DeepL 폴백도 실패: %s", exc2)
                        r = _stub_result(req, variant_index=v)
                else:
                    r = _stub_result(req, variant_index=v)

            # 금지어 검사
            r = self._check_forbidden(r)
            results.append(r)
            total_cost += r.cost_usd
            total_tokens += r.tokens_used

        # 예산 기록
        if total_cost > 0:
            self.budget.record(
                total_cost,
                provider=results[0].provider if results else "",
                tokens=total_tokens,
                note=f"req={cache_key[:16]}",
            )

        # 캐시 저장
        self.cache.set(
            cache_key,
            [r.to_dict() for r in results],
            provider=results[0].provider if results else "",
            tokens=total_tokens,
            cost_usd=float(total_cost),
        )

        return results

    def _check_forbidden(self, result: CopyResult) -> CopyResult:
        """금지어 검사 및 경고 추가."""
        try:
            from src.ai.forbidden_terms import check_forbidden_terms, warnings_to_list
            all_text = " ".join([
                result.title_ko,
                " ".join(result.bullet_points),
                result.description_html,
            ])
            matches = check_forbidden_terms(all_text)
            if matches:
                result.forbidden_terms_warnings = warnings_to_list(matches)
        except Exception as exc:
            logger.warning("금지어 검사 오류: %s", exc)
        return result
