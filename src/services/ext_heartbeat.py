"""Y12-D 7(오너 2026-10-18 「확장 heartbeat」) — PC 수집기(크롬 확장)가 살아 있나.

확장은 콘솔 탭이 열려 있으면 1분마다 `POST /api/v1/collect/ext/beat {version}`을 보낸다(1.5.167~). 그 전 버전도
보강 대기 폴링(`GET /enrich/pending`, 1.5.151~ · 5분 주기 + 콘솔 탭 열 때)을 하므로 그 폴링도 신호로 친다(버전은 모름).
기록 = app_state `ext_beat:{user_id}` `{at, version, source}` — 계정마다 마지막 하나만(로그 아님).

대시보드 「돌아가는 것」: 「PC 수집기 · 연결 HH:MM」 / 「PC 수집기 · 끊김 n시간」 / 신호 기록 없음.
끊김 = 마지막 신호가 `STALE_MIN`(기본 15분 — 폴링 주기 5분의 3배) 넘게 전. 끊긴 채 재수집 대기가 있으면 손댈 것 「PC에서 콘솔 탭 열기」.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)

KEY = "ext_beat:"
_VER_RE = re.compile(r"^\d{1,3}(?:\.\d{1,4}){1,3}$")


def stale_min() -> int:
    try:
        return max(5, int(os.getenv("EXT_BEAT_STALE_MIN", "15")))
    except ValueError:
        return 15


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def clean_version(v) -> str:
    v = str(v or "").strip()
    return v if _VER_RE.match(v) else ""


def beat(user_id: str, version: str = "", source: str = "beat", now: Optional[datetime] = None) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    rec = {"at": (now or datetime.now(timezone.utc)).isoformat(), "version": clean_version(version), "source": str(source)[:20]}
    try:
        if not rec["version"]:                                   # 폴링(옛 확장)이 1분 비트가 남긴 버전을 지우지 않게
            rec["version"] = str((_st().state_get(KEY + uid) or {}).get("version") or "")
        _st().state_set(KEY + uid, rec)
    except Exception as exc:                                     # noqa: BLE001 — 신호 기록 실패가 수집을 막지 않는다
        logger.debug("[PC 수집기] 신호 기록 실패: %s", exc)


def status(ids: Iterable[str], now: Optional[datetime] = None) -> Dict:
    """`{seen, at, version, age_min, connected, line}` — 여러 식별자(user_id·email) 중 가장 최근 신호."""
    best = None
    for i in {str(x) for x in (ids or []) if x}:
        try:
            r = _st().state_get(KEY + i) or {}
        except Exception:                                        # noqa: BLE001
            r = {}
        if r.get("at") and (best is None or str(r["at"]) > str(best["at"])):
            best = r
    if not best:
        return {"seen": False, "connected": None, "line": "PC 수집기 · 신호 기록 없음"}
    try:
        at = datetime.fromisoformat(str(best["at"]).replace("Z", "+00:00"))
    except ValueError:
        return {"seen": False, "connected": None, "line": "PC 수집기 · 신호 기록 없음"}
    now = now or datetime.now(timezone.utc)
    age = max(0, int((now - at).total_seconds() // 60))
    from src.seller_console.attention import KST
    ver = str(best.get("version") or "")
    vtxt = f" · v{ver}" if ver else ""
    if age <= stale_min():
        line = f"PC 수집기 · 연결 {at.astimezone(KST).strftime('%H:%M')}{vtxt}"
        ok = True
    else:
        h = age // 60
        line = f"PC 수집기 · 끊김 {h}시간" if h else f"PC 수집기 · 끊김 {age}분"
        line += vtxt
        ok = False
    return {"seen": True, "at": best["at"], "version": ver, "age_min": age, "connected": ok, "line": line}
