from __future__ import annotations

import logging
import math
import os
from decimal import Decimal
from typing import Optional

from src.ai.budget import BudgetGuard
from src.cs_bot.faq_store import FAQEntry, FAQStore
from src.cs_bot.inbox_store import CSMessage

logger = logging.getLogger(__name__)


def render_template(template: str, msg: CSMessage, order_info: dict | None) -> str:
    context = {
        "customer_name": msg.customer_name or "고객님",
        "order_no": msg.order_no or (order_info or {}).get("order_no", ""),
        "tracking_no": (order_info or {}).get("tracking_no", ""),
        "eta": (order_info or {}).get("eta", ""),
    }
    rendered = template or ""
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value or ""))
    return rendered


def suggest_reply(msg: CSMessage, faq_store: FAQStore) -> str:
    candidates = faq_store.list_all(language=msg.language, category=msg.category or None, enabled_only=True)
    if not candidates:
        candidates = faq_store.search_by_keywords(msg.body, language=msg.language)
    scored = _rank_candidates(msg, candidates)
    if not scored:
        fallback = "문의 주셔서 감사합니다. 확인 후 빠르게 안내드리겠습니다."
        return _polish_with_ai(fallback, msg.language)

    top = scored[:3]
    draft = render_template(top[0].answer_template, msg, order_info={"order_no": msg.order_no})
    return _polish_with_ai(draft, msg.language)


def _rank_candidates(msg: CSMessage, candidates: list[FAQEntry]) -> list[FAQEntry]:
    body = (msg.body or "").lower()
    tokens = [t for t in body.replace("\n", " ").split(" ") if t]
    rows: list[tuple[float, FAQEntry]] = []
    for entry in candidates:
        score = 0.0
        source = f"{entry.question} {' '.join(entry.keywords)}".lower()
        for token in tokens:
            if token and token in source:
                score += 1.0
        for keyword in entry.keywords:
            if keyword.lower() in body:
                score += 2.0
        if msg.category and entry.category == msg.category:
            score += 1.0
        if msg.language and entry.language == msg.language:
            score += 0.5
        score += max(0, entry.priority) * 0.2
        if entry.embedding:
            score += _cosine_bonus(entry.embedding, None)
        if score > 0:
            rows.append((score, entry))
    rows.sort(key=lambda x: (-x[0], -x[1].priority, x[1].faq_id))
    return [entry for _, entry in rows]


def _cosine_bonus(entry_embedding: list[float], query_embedding: Optional[list[float]]) -> float:
    if not entry_embedding or not query_embedding:
        return 0.0
    if len(entry_embedding) != len(query_embedding):
        return 0.0
    dot = sum(a * b for a, b in zip(entry_embedding, query_embedding))
    n1 = math.sqrt(sum(a * a for a in entry_embedding))
    n2 = math.sqrt(sum(b * b for b in query_embedding))
    if n1 <= 0 or n2 <= 0:
        return 0.0
    return dot / (n1 * n2)


def _polish_with_ai(text: str, language: str) -> str:
    if not text.strip():
        return text
    guard = BudgetGuard()
    if not guard.can_spend():
        return text

    openai_key = os.getenv("OPENAI_API_KEY", "")
    deepl_key = os.getenv("DEEPL_API_KEY", "")
    if not (openai_key or deepl_key):
        return text

    try:
        if openai_key:
            polished, cost_usd, tokens = _call_openai_polish(text, language)
            if polished:
                guard.record(cost_usd=cost_usd, provider="openai", tokens=tokens, note="cs_bot_polish")
                return polished
        if deepl_key:
            polished, cost_usd, chars = _call_deepl_polish(text, language)
            if polished:
                guard.record(cost_usd=cost_usd, provider="deepl", tokens=chars, note="cs_bot_polish")
                return polished
    except Exception as exc:
        logger.warning("CS AI 답변 다듬기 실패: %s", exc)
    return text


def _call_openai_polish(text: str, language: str) -> tuple[str, Decimal, int]:
    import requests

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "고객 CS 답변을 간결하고 공손하게 다듬어 주세요."},
            {"role": "user", "content": f"언어={language}\n원문={text}"},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=8,
    )
    if not resp.ok:
        return text, Decimal("0"), 0
    data = resp.json()
    usage = data.get("usage", {}) or {}
    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    # gpt-4o-mini 기준(기존 copywriter와 동일 추정)
    cost_usd = Decimal(str(input_tokens)) * Decimal("0.00000015") + Decimal(str(output_tokens)) * Decimal("0.0000006")
    content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or text).strip()
    return content, cost_usd, total_tokens


def _call_deepl_polish(text: str, language: str) -> tuple[str, Decimal, int]:
    import requests

    key = os.getenv("DEEPL_API_KEY", "")
    if not key:
        return text, Decimal("0"), 0
    endpoint = "https://api-free.deepl.com/v2/translate" if key.endswith(":fx") else "https://api.deepl.com/v2/translate"
    target = {"ko": "KO", "en": "EN", "ja": "JA", "zh": "ZH"}.get(language, "KO")
    resp = requests.post(
        endpoint,
        data={"auth_key": key, "text": text, "target_lang": target},
        timeout=8,
    )
    if not resp.ok:
        return text, Decimal("0"), 0
    payload = resp.json()
    translations = payload.get("translations") or []
    if not translations:
        return text, Decimal("0"), 0
    translated = str(translations[0].get("text") or text).strip()
    used_chars = len(text)
    per_char_usd = Decimal(os.getenv("DEEPL_COST_PER_CHAR_USD", "0.000025"))
    return translated, (per_char_usd * Decimal(str(used_chars))), used_chars
