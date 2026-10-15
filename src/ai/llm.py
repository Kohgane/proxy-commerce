"""Y8(오너 2026-10-13) — AI 호출 공급자 한 자리: **Anthropic 우선, OpenAI 폴백**.

- 모델: `ANTHROPIC_MODEL`(기본 claude-sonnet-5) · 번역·짧은 수정은 `ANTHROPIC_MODEL_SMALL`(기본 claude-haiku-4-5).
  OpenAI 폴백은 `OPENAI_MODEL`(기본 gpt-4o-mini).
- 예산: 두 공급자 모두 서버 월 예산 `AI_MONTHLY_BUDGET_USD`(`src.ai.budget.BudgetGuard`) 하나에 묶는다 — 부르기 전 추정치로
  확인, 부른 뒤 실제 토큰으로 기록.
- 로그: 부를 때마다 `[AI] provider=anthropic model=… tokens=입력+출력 usd=… purpose=…` 한 줄(키·본문은 남기지 않는다).
- Anthropic은 공식 SDK(`anthropic`)로 부른다. SDK가 없거나 키가 없으면 그 단을 건너뛴다(OpenAI로).

반환은 늘 dict — 성공이면 `text`, 둘 다 실패면 `error`(마지막 사유)와 `attempts`(공급자별 사유·예외 이름). 예외를 던지지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MODEL_SMALL = "claude-haiku-4-5"

#: USD / 100만 토큰 (입력, 출력). 모르는 모델은 같은 계열 값으로 근사한다(`_price`).
PRICE_PER_MTOK = {
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-4-5": (Decimal("1"), Decimal("5")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}


class LLMError(Exception):
    """두 공급자 모두 실패 — `attempts`에 공급자별 사유. `first`는 첫 공급자(Anthropic) 예외(사유 분류용)."""

    def __init__(self, msg: str, attempts: List[dict], first: Optional[BaseException] = None):
        super().__init__(msg)
        self.attempts = attempts
        self.first = first


def model_for(size: str = "large") -> str:
    if size == "small":
        return (os.getenv("ANTHROPIC_MODEL_SMALL") or DEFAULT_MODEL_SMALL).strip()
    return (os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip()


def _env(name: str) -> str:
    from src.utils.env import env_str
    return env_str(name) or ""


def anthropic_ready() -> bool:
    if not _env("ANTHROPIC_API_KEY"):
        return False
    # Z10-C: 「있나」만 본다 — import하면 SDK(+39MB)가 워커에 눌러앉는다. 실제로 부를 때만 import한다.
    try:
        import importlib.util
        return importlib.util.find_spec("anthropic") is not None
    except Exception:
        return False


def openai_ready() -> bool:
    return bool(_env("OPENAI_API_KEY"))


def any_ready() -> bool:
    return anthropic_ready() or openai_ready()


def _price(model: str) -> tuple:
    m = str(model or "")
    if m in PRICE_PER_MTOK:
        return PRICE_PER_MTOK[m]
    for k in sorted(PRICE_PER_MTOK, key=len, reverse=True):
        if m.startswith(k):
            return PRICE_PER_MTOK[k]
    if "haiku" in m:
        return PRICE_PER_MTOK["claude-haiku-4-5"]
    if "opus" in m:
        return PRICE_PER_MTOK["claude-opus-5-5"]
    if m.startswith("claude"):
        return PRICE_PER_MTOK["claude-sonnet-5"]
    return PRICE_PER_MTOK["gpt-4o-mini"]


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    pin, pout = _price(model)
    return (Decimal(int(tokens_in or 0)) * pin + Decimal(int(tokens_out or 0)) * pout) / Decimal(1_000_000)


def _guard():
    from src.ai.budget import BudgetGuard
    return BudgetGuard()


def _log(provider: str, model: str, tin: int, tout: int, usd: Decimal, purpose: str, ok: bool = True, why: str = "") -> None:
    logger.info("[AI] provider=%s model=%s tokens=%d+%d usd=%.5f purpose=%s%s", provider, model, tin, tout, float(usd),
                purpose or "-", "" if ok else f" fail={why[:120]}")


def _call_anthropic(model: str, system: str, prompt: str, max_tokens: int, timeout: float,
                    images: Optional[List[str]] = None) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=_env("ANTHROPIC_API_KEY"), timeout=timeout, max_retries=1)
    content: Any = prompt
    if images:                                    # Y11-O: 사진 주소(공개 URL)를 같이 — 카테고리 고르기
        content = [{"type": "image", "source": {"type": "url", "url": u}} for u in images] + [{"type": "text", "text": prompt}]
    kw: Dict[str, Any] = {"model": model, "max_tokens": int(max_tokens),
                          "messages": [{"role": "user", "content": content}]}
    if system:
        kw["system"] = system
    # Sonnet 5 계열은 effort를 받는다(짧은 수정 — 낮게). Haiku 4.5는 effort가 없다(넣으면 400).
    if not model.startswith("claude-haiku-4"):
        kw["output_config"] = {"effort": "low"}
    resp = client.messages.create(**kw)
    text = "".join(getattr(b, "text", "") for b in (resp.content or []) if getattr(b, "type", "") == "text").strip()
    u = getattr(resp, "usage", None)
    return {"text": text, "tokens_in": int(getattr(u, "input_tokens", 0) or 0),
            "tokens_out": int(getattr(u, "output_tokens", 0) or 0), "stop_reason": getattr(resp, "stop_reason", "")}


def _call_openai(model: str, system: str, prompt: str, max_tokens: int, timeout: float, json_mode: bool,
                 images: Optional[List[str]] = None) -> dict:
    import requests as _req
    from src.seller_console.ai.translator import _post_with_429_retry
    content: Any = prompt
    if images:
        content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": u}} for u in images]
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    payload: Dict[str, Any] = {"model": model, "messages": msgs, "temperature": 0.2, "max_tokens": int(max_tokens)}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    resp = _post_with_429_retry(_req, "https://api.openai.com/v1/chat/completions",
                                headers={"Authorization": f"Bearer {_env('OPENAI_API_KEY')}",
                                         "Content-Type": "application/json"},
                                json=payload, timeout=timeout)
    j = resp.json()
    u = j.get("usage") or {}
    return {"text": str(j["choices"][0]["message"]["content"] or "").strip(),
            "tokens_in": int(u.get("prompt_tokens") or 0), "tokens_out": int(u.get("completion_tokens") or 0)}


def complete(prompt: str, *, system: str = "", size: str = "large", max_tokens: int = 2000, purpose: str = "",
             timeout: float = 30.0, json_mode: bool = False, providers: Optional[List[str]] = None,
             images: Optional[List[str]] = None) -> dict:
    """한 번 부른다 — Anthropic → OpenAI 순. 실패해도 예외 없이 `{"text": "", "error", "attempts"}`.

    Y11-O: 같은 공급자가 **빈 응답**(글자 0)을 주면 그 공급자에 한 번 더 묻는다(`retried_empty`) — 그래도 비면 다음 공급자.

    성공: `{"text", "provider", "model", "tokens_in", "tokens_out", "usd", "attempts"}`.
    """
    from src.ai.budget import BudgetExceededError
    attempts: List[dict] = []
    first_exc: Optional[BaseException] = None
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        return {"text": "", "error": "dry-run", "attempts": [], "provider": "", "model": ""}
    order = providers or ["anthropic", "openai"]
    for prov in order:
        if prov == "anthropic" and not anthropic_ready():
            continue
        if prov == "openai" and not openai_ready():
            continue
        model = model_for(size) if prov == "anthropic" else (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
        est = cost_usd(model, (len(system) + len(prompt)) // 2 + 1, max_tokens)
        try:
            g = _guard()
            if not g.can_spend(estimated_cost_usd=est):
                raise BudgetExceededError(g.summary())
            for _try in range(2):
                ikw = {"images": images} if images else {}
                r = (_call_anthropic(model, system, prompt, max_tokens, timeout, **ikw) if prov == "anthropic"
                     else _call_openai(model, system, prompt, max_tokens, timeout, json_mode, **ikw))
                usd = cost_usd(model, r["tokens_in"], r["tokens_out"])
                try:
                    g.record(cost_usd=usd, provider=prov, tokens=r["tokens_in"] + r["tokens_out"], note=purpose or "llm")
                except Exception as exc:                              # noqa: BLE001 — 기록 실패는 호출 실패가 아니다
                    logger.warning("[AI] 비용 기록 실패: %s", exc)
                _log(prov, model, r["tokens_in"], r["tokens_out"], usd, purpose)
                if r["text"] or _try:
                    break
                attempts.append({"provider": prov, "model": model, "ok": False, "error": "빈 응답 — 한 번 더",
                                 "status": None})
                logger.info("[AI] 빈 응답 — 같은 공급자에 한 번 더 provider=%s purpose=%s", prov, purpose or "-")
            if not r["text"]:
                raise ValueError("빈 응답" + (f"(stop_reason={r.get('stop_reason')})" if r.get("stop_reason") else ""))
            attempts.append({"provider": prov, "model": model, "ok": True})
            return {**r, "provider": prov, "model": model, "usd": float(usd), "attempts": attempts,
                    "retried_empty": any(a.get("error") == "빈 응답 — 한 번 더" for a in attempts)}
        except Exception as exc:                                      # noqa: BLE001 — 다음 공급자로
            if first_exc is None:
                first_exc = exc
            why = f"{type(exc).__name__}: {str(exc)[:200]}"
            attempts.append({"provider": prov, "model": model, "ok": False, "error": why,
                             "status": getattr(exc, "status_code", None)})
            _log(prov, model, 0, 0, Decimal(0), purpose, ok=False, why=why)
    if not attempts:
        return {"text": "", "error": "AI 키 없음(Anthropic·OpenAI 둘 다 미설정)", "attempts": [], "provider": "", "model": "",
                "no_key": True}
    return {"text": "", "error": attempts[-1].get("error") or "AI 호출 실패", "attempts": attempts, "provider": "",
            "model": "", "first_exc": first_exc}


def complete_or_raise(prompt: str, **kw) -> dict:
    """`complete`와 같고, 실패면 `LLMError`(첫 공급자 예외를 `first`로) — 예외로 사유를 분류하는 호출부용."""
    r = complete(prompt, **kw)
    if r.get("text"):
        return r
    raise LLMError(str(r.get("error") or "AI 호출 실패"), r.get("attempts") or [], r.get("first_exc"))


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_json(text: str) -> Optional[dict]:
    """응답에서 JSON 객체 하나를 꺼낸다(코드 펜스·앞뒤 설명 허용). 못 꺼내면 None."""
    s = str(text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s)
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except Exception:
        pass
    m = _JSON_RE.search(s)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else None
    except Exception:
        return None
