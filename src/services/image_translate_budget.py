"""Z3-2(오너 2026-10-04) — 텐센트 이미지 번역 **월 예산**(계정 전체 하나) · 장부 · 진단 한 줄.

- 단가(오너 제공): pro(`Mode=0`, ImageTranslateLLM 기본) $0.04/장 · lite(`Mode=1`) $0.02/장 · 무료분 없음 · QPS 1.
  env `TENCENT_IMAGE_PRICE_PRO_USD` / `TENCENT_IMAGE_PRICE_LITE_USD`로 바꾼다(청구서가 다르면 그 값으로).
- 월 상한 `TENCENT_IMAGE_MONTHLY_BUDGET_USD`(기본 200) — **계정 전체 단일**(사용자별 아님, Stage 6에서 쪼갠다).
  넘으면 번역을 **안 보내고** 원본으로 등록을 계속한다(실패 아님).
- 장부 = `app_state` `imgko_budget:YYYY-MM`(KST 달) — 보낸 장(calls)·성공 장(ok)·추정 비용(usd = 성공 장 × 단가)·
  모드별 장 수·예산으로 건너뛴 장·로컬 판정으로 건너뛴 장. 비용은 **추정**이다(청구서가 정본).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))
ENV_BUDGET = "TENCENT_IMAGE_MONTHLY_BUDGET_USD"
DEFAULT_BUDGET = 200.0
ENV_MODE = "TENCENT_TMT_MODE"


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def price(mode: int) -> float:
    return _f("TENCENT_IMAGE_PRICE_LITE_USD", 0.02) if int(mode) == 1 else _f("TENCENT_IMAGE_PRICE_PRO_USD", 0.04)


def budget() -> float:
    return max(0.0, _f(ENV_BUDGET, DEFAULT_BUDGET))


def mode() -> int:
    """지금 보낼 모드 — `TENCENT_TMT_MODE`(0=pro 기본 · 1=lite). 다른 값은 0."""
    return 1 if str(os.getenv(ENV_MODE, "0")).strip() == "1" else 0


def month(now=None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(_KST).strftime("%Y-%m")


def _key(now=None) -> str:
    return "imgko_budget:" + month(now)


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def ledger(now=None) -> dict:
    try:
        v = _st().state_get(_key(now)) or {}
    except Exception:
        v = {}
    return {k: v.get(k, 0) for k in ("calls", "ok", "usd", "pro", "lite", "skip_budget", "skip_ocr")}


def _bump(fields: dict, now=None) -> None:
    """장부 칸 더하기 — PG면 한 문장(워커 둘이 동시에 와도 안 잃는다), 아니면 메모리."""
    key = _key(now)
    try:
        from src.db import pg
        if pg.pg_enabled():
            with pg.tx() as cur:
                cur.execute("INSERT INTO app_state (key, value, updated_at) VALUES (%s::text, '{}'::jsonb, now()) "
                            "ON CONFLICT (key) DO NOTHING", (key,))
                for k, v in fields.items():
                    cur.execute("UPDATE app_state SET value = jsonb_set(value, ARRAY[%s::text], "
                                "to_jsonb(COALESCE((value->>%s::text)::numeric, 0) + %s::numeric)), updated_at = now() "
                                "WHERE key = %s::text", (k, k, v, key))
            return
        cur_v = _st().state_get(key) or {}
        for k, v in fields.items():
            cur_v[k] = round(float(cur_v.get(k) or 0) + float(v), 4)
        _st().state_set(key, cur_v)
    except Exception as exc:
        logger.warning("[이미지번역·예산] 장부 기록 실패: %s: %s", type(exc).__name__, exc)


def can_send(m: int | None = None, now=None) -> tuple:
    """`(보내도 되나, 이번 달 추정 비용, 상한)` — 한 장 더 보내면 상한을 넘는지로 판단."""
    m = mode() if m is None else m
    spent = float(ledger(now).get("usd") or 0)
    cap = budget()
    return (spent + price(m) <= cap + 1e-9), spent, cap


def record_call(m: int, ok: bool, now=None) -> None:
    """텐센트에 한 장 보냈다 — 성공 응답이면 단가만큼 추정 비용."""
    fields = {"calls": 1, ("lite" if int(m) == 1 else "pro"): 1}
    if ok:
        fields.update({"ok": 1, "usd": price(m)})
    _bump(fields, now)


def record_skip(kind: str, now=None) -> None:
    _bump({"skip_budget" if kind == "budget" else "skip_ocr": 1}, now)


def status_line(now=None) -> str:
    """진단 한 줄 — 「이미지 번역 이번 달 n장 / $x」(오너가 청구서를 안 봐도 되게)."""
    lg = ledger(now)
    m = mode()
    return (f"이미지 번역 이번 달({month(now)}) {int(lg['ok'])}장 / ${float(lg['usd']):.2f} "
            f"(상한 ${budget():.0f} · {'lite' if m == 1 else 'pro'} ${price(m):.2f}/장 · 보낸 {int(lg['calls'])}장 · "
            f"로컬 판정으로 안 보냄 {int(lg['skip_ocr'])}장 · 예산으로 안 보냄 {int(lg['skip_budget'])}장) — 추정, 청구서가 정본")
