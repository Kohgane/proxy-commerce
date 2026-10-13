"""src/ai/claude_client.py — AF1(오너 2026-10-13): Claude(Anthropic Messages API) 한 자리.

오너가 Render 「고가네프록시(싱가포르)」에 `ANTHROPIC_API_KEY`를 넣었다(키 값은 어디에도 적지 않는다).
SDK 없이 `requests`로 부른다 — 새 의존성 0([[requirements 누락 무증상 롤백]]).

- 모델 `ANTHROPIC_MODEL`(기본 `claude-sonnet-5-5`) · 노력 `ANTHROPIC_EFFORT`(기본 `low` — 짧고 범위가 정해진 고치기).
- 응답은 **JSON 스키마로만**(`output_config.format`) — 글을 파싱해 짐작하지 않는다.
- 서버 월 예산(`AI_MONTHLY_BUDGET_USD`)에 묶는다 — OpenAI 호출과 같은 가드. 넘으면 「서버 월 예산」으로 실패.
- 429·529·5xx는 짧게 1회만 다시. 그래도 실패면 예외 그대로(가짜 성공 0).
- 키 없음·`ADAPTER_DRY_RUN=1` → `ClaudeUnavailable`(부른 척하지 않는다).
"""
from __future__ import annotations

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "low"

#: USD / 토큰(입력·출력) — 공식 가격표(platform.claude.com/docs/en/models/overview, 2026-10-13 확인).
#:   모르는 모델은 Sonnet 값으로 센다(예산 가드가 덜 세는 쪽으로 틀리지 않게 — Haiku보다 비싸게 셈).
PRICES_PER_MTOK = {
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-fable-5-1": (Decimal("10"), Decimal("50")),
}


class ClaudeUnavailable(RuntimeError):
    """키가 없거나(또는 DRY_RUN) 예산이 막아 부르지 않았다 — 호출 실패와 구분한다."""


class ClaudeError(RuntimeError):
    """불렀는데 실패(HTTP·형식·거절). `status`·`body` 앞부분을 싣는다(키는 싣지 않는다)."""

    def __init__(self, msg: str, *, status: Optional[int] = None, body: str = "") -> None:
        super().__init__(msg)
        self.status = status
        self.body = body


def _key() -> str:
    from src.utils.env import env_str
    return env_str("ANTHROPIC_API_KEY")


def model() -> str:
    from src.utils.env import env_str
    return env_str("ANTHROPIC_MODEL", DEFAULT_MODEL)


def configured() -> bool:
    return bool(_key()) and os.getenv("ADAPTER_DRY_RUN", "0") != "1"


def cost_usd(model_id: str, in_tok: int, out_tok: int) -> Decimal:
    pin, pout = PRICES_PER_MTOK.get(model_id, PRICES_PER_MTOK[DEFAULT_MODEL])
    return (Decimal(int(in_tok or 0)) * pin + Decimal(int(out_tok or 0)) * pout) / Decimal(1_000_000)


def _post(body: dict, timeout: float):
    import requests
    headers = {"x-api-key": _key(), "anthropic-version": API_VERSION, "content-type": "application/json"}
    last = None
    for attempt in (1, 2):
        r = requests.post(API_URL, headers=headers, json=body, timeout=timeout)
        if r.status_code in (429, 529) or r.status_code >= 500:
            last = r
            if attempt == 1:
                try:
                    wait = float(os.getenv("ANTHROPIC_RETRY_BACKOFF_SEC", "1.5") or 0)
                except (TypeError, ValueError):
                    wait = 1.5
                if wait > 0:
                    time.sleep(min(wait, 5))
                logger.warning("Claude %s — %.1fs 뒤 1회 다시", r.status_code, wait)
                continue
        return r
    return last


def messages_json(system: str, user: str, schema: Dict[str, Any], *, max_tokens: int = 2000,
                  effort: Optional[str] = None, timeout: float = 30.0,
                  note: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """JSON 스키마로 답을 받는다 → `(답 dict, 호출 기록 {model, ms, in_tok, out_tok, cost_usd, stop_reason})`.

    키·예산이 막으면 `ClaudeUnavailable`, 불렀는데 실패면 `ClaudeError`.
    """
    if not _key():
        raise ClaudeUnavailable("ANTHROPIC_API_KEY 없음")
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        raise ClaudeUnavailable("ADAPTER_DRY_RUN=1 — Claude를 부르지 않음")
    mid = model()
    from src.ai.budget import BudgetGuard
    guard = BudgetGuard()
    est = cost_usd(mid, (len(system) + len(user)) // 2 + 200, max_tokens)
    if not guard.can_spend(estimated_cost_usd=est):
        raise ClaudeUnavailable("서버 월 예산(AI_MONTHLY_BUDGET_USD) 상한 — Claude를 부르지 않음")
    body = {
        "model": mid,
        "max_tokens": int(max_tokens),
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": effort or os.getenv("ANTHROPIC_EFFORT", DEFAULT_EFFORT) or DEFAULT_EFFORT,
                          "format": {"type": "json_schema", "schema": schema}},
    }
    t0 = time.monotonic()
    try:
        r = _post(body, timeout)
    except Exception as exc:                                     # 네트워크 — 「불렀는데 실패」
        raise ClaudeError(f"Claude 호출 실패 — {type(exc).__name__}: {str(exc)[:160]}") from exc
    ms = int((time.monotonic() - t0) * 1000)
    if r is None or r.status_code != 200:
        st = getattr(r, "status_code", None)
        txt = (getattr(r, "text", "") or "")[:400]
        raise ClaudeError(f"Claude HTTP {st} — {txt[:200]}", status=st, body=txt)
    try:
        data = r.json()
    except Exception as exc:
        raise ClaudeError("Claude 응답이 JSON이 아님", status=200, body=(r.text or "")[:400]) from exc
    usage = data.get("usage") or {}
    in_tok, out_tok = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    c = cost_usd(str(data.get("model") or mid), in_tok, out_tok)
    try:
        guard.record(c, provider="anthropic", tokens=in_tok + out_tok, note=note or "claude")
    except Exception as exc:                                     # 기록 실패가 결과를 버리지 않는다
        logger.warning("Claude 비용 기록 실패: %s", exc)
    meta = {"model": str(data.get("model") or mid), "ms": ms, "in_tok": in_tok, "out_tok": out_tok,
            "cost_usd": float(c), "stop_reason": str(data.get("stop_reason") or "")}
    if meta["stop_reason"] == "refusal":
        raise ClaudeError("Claude가 답을 거절함(refusal)", status=200)
    text = next((b.get("text") for b in (data.get("content") or [])
                 if isinstance(b, dict) and b.get("type") == "text" and b.get("text")), "")
    if not text:
        raise ClaudeError(f"Claude 답에 글이 없음(stop_reason={meta['stop_reason'] or '?'})", status=200)
    try:
        obj = json.loads(text)
    except Exception as exc:
        raise ClaudeError("Claude 답이 스키마 JSON이 아님", status=200, body=text[:400]) from exc
    if not isinstance(obj, dict):
        raise ClaudeError("Claude 답이 객체가 아님", status=200, body=text[:400])
    return obj, meta


def ping() -> Dict[str, Any]:
    """관리자 화면 버튼용 — 짧은 질문 하나로 키·모델·지연·비용을 잰다([[키를 옮기지 말고 측정을 옮긴다]])."""
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "word": {"type": "string"}},
              "required": ["ok", "word"], "additionalProperties": False}
    try:
        obj, meta = messages_json("You answer with the requested JSON only.",
                                  'Return {"ok": true, "word": "다리"}.', schema, max_tokens=200, note="ping")
        return {"ok": bool(obj.get("ok")), "answer": obj, **meta}
    except ClaudeUnavailable as exc:
        return {"ok": False, "unavailable": True, "error": str(exc), "model": model()}
    except ClaudeError as exc:
        return {"ok": False, "error": str(exc), "status": exc.status, "model": model()}
