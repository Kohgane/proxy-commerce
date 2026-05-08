from __future__ import annotations

import logging
import math
import os
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .faq_store import FAQStore

logger = logging.getLogger(__name__)


def get_embedding(text: str, *, language: str = "ko") -> list[float] | None:
    """OpenAI 임베딩 호출. 실패/예산 초과/비활성 시 None."""
    provider = os.getenv("CS_EMBEDDING_PROVIDER", "disabled").lower()
    if provider == "disabled":
        return None

    try:
        from src.ai.budget import BudgetGuard
        guard = BudgetGuard()
        if not guard.can_spend():
            logger.debug("임베딩 예산 초과 — 스킵")
            return None
    except Exception:
        pass

    if provider == "openai":
        return _get_openai_embedding(text)
    return None


def _get_openai_embedding(text: str) -> list[float] | None:
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        return None
    model = os.getenv("CS_EMBEDDING_MODEL", "text-embedding-3-small")
    try:
        import requests
        resp = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            json={"input": text[:8000], "model": model},
            timeout=10,
        )
        if not resp.ok:
            logger.warning("OpenAI 임베딩 실패 %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        embedding = data.get("data", [{}])[0].get("embedding")
        if embedding:
            # Record budget
            usage = data.get("usage", {})
            total_tokens = int(usage.get("total_tokens", 0))
            cost_usd = Decimal(str(total_tokens)) * Decimal("0.00000002")  # $0.02/1M for 3-small
            try:
                from src.ai.budget import BudgetGuard
                BudgetGuard().record(cost_usd=cost_usd, provider="openai", tokens=total_tokens, note="cs_embedding")
            except Exception:
                pass
            return [float(x) for x in embedding]
    except Exception as exc:
        logger.warning("OpenAI 임베딩 오류: %s", exc)
    return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """코사인 유사도 계산."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    n1 = math.sqrt(sum(x * x for x in a))
    n2 = math.sqrt(sum(y * y for y in b))
    if n1 <= 0 or n2 <= 0:
        return 0.0
    return dot / (n1 * n2)


def rebuild_faq_embeddings(faq_store: "FAQStore") -> int:
    """모든 FAQ 임베딩 재계산. /admin/cs/rebuild-embeddings 에서 호출."""
    provider = os.getenv("CS_EMBEDDING_PROVIDER", "disabled").lower()
    if provider == "disabled":
        logger.info("CS_EMBEDDING_PROVIDER=disabled — 임베딩 재계산 스킵")
        return 0

    entries = faq_store.list_all(enabled_only=False)
    updated = 0
    for entry in entries:
        text = f"{entry.question} {' '.join(entry.keywords)} {entry.answer_template}"
        embedding = get_embedding(text, language=entry.language)
        if embedding:
            entry.embedding = embedding
            faq_store.update(entry)
            updated += 1
    logger.info("FAQ 임베딩 재계산 완료: %d/%d", updated, len(entries))
    return updated
