"""src/auth/signup_origin.py — Y15-B(오너 2026-10-22) 가입 유입 기록.

신규 셀러(soenstore1004) 가입을 조사해 보니 **어디서 들어왔는지 남은 게 없었다** — route_hits는 화면 이름 카운터뿐이고
사용자별 방문 기록이 없다. 그래서 가입 순간에 한 줄을 남긴다:

`{referrer, landing_path, utm_source…, ip(X-Forwarded-For 첫 값), ua, at, first_at}`

- **첫 방문**의 referrer·랜딩 경로·utm은 세션 쿠키(`kgp_first_visit`)에 담아 두었다가 가입 때 옮긴다
  (가입 화면에 도착했을 땐 referrer가 이미 우리 사이트다).
- 저장 = `app_state` `signup_origin:<user_id>`(PG). 이메일 가입은 `password_accounts`(PG), 소셜 가입은 `users` 시트에 계정이
  있어 둘이 같이 닿는 곳이 이 표뿐이다(시트에는 extra 칸이 없다) — 조사 때 DB에서 바로 읽힌다.
- 로그에는 referrer **호스트만** 남긴다(IP·UA는 저장만, 로그 금지).
- 기록 실패는 가입을 막지 않는다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SESSION_KEY = "kgp_first_visit"
STATE_PREFIX = "signup_origin:"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")
_SKIP_PREFIX = ("/static", "/health", "/api/", "/cron", "/webhook", "/favicon", "/sw.js", "/manifest",
                "/.well-known", "/robots", "/sitemap")


def capture_first_visit() -> None:
    """`before_request` — 로그인 안 한 사람의 **첫** 화면 요청 한 번만 세션에 적는다(정적·API·헬스는 건너뜀)."""
    try:
        from flask import request, session
        if request.method != "GET":
            return
        path = request.path or "/"
        last = path.rsplit("/", 1)[-1]
        if path.startswith(_SKIP_PREFIX) or "." in last:
            return
        if session.get("user_id") or session.get(SESSION_KEY):
            return
        ref = str(request.referrer or "")
        if urlparse(ref).netloc.lower() == str(request.host or "").lower():
            ref = ""                                             # 우리 사이트 안에서 온 것 = 유입처 아님
        session[SESSION_KEY] = {
            "referrer": ref[:300], "landing_path": path[:200],
            "utm": {k: str(request.args.get(k))[:100] for k in UTM_KEYS if request.args.get(k)},
            "at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:                                     # noqa: BLE001 — 기록이 화면을 막지 않는다
        logger.debug("[유입] 첫 방문 기록 실패: %s", exc)


def build() -> dict:
    """가입 요청에서 — 세션의 첫 방문 + 지금 요청의 ip·ua."""
    from flask import request, session
    first = dict(session.get(SESSION_KEY) or {})
    xff = str(request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip()
    out = {
        "referrer": str(first.get("referrer") or ""),
        "landing_path": str(first.get("landing_path") or ""),
        "ip": xff or str(request.remote_addr or ""),
        "ua": str(request.headers.get("User-Agent", "") or "")[:200],
        "at": datetime.now(timezone.utc).isoformat(),
        "first_at": str(first.get("at") or ""),
    }
    out.update({k: v for k, v in (first.get("utm") or {}).items() if k in UTM_KEYS})
    country = str(request.headers.get("CF-IPCountry", "") or "").strip().upper()
    if country and country not in ("XX", "T1"):
        out["country"] = country                                 # 앞단이 알려 줄 때만 — 지어내지 않는다
    return out


def record(user_id: str, origin: Optional[dict] = None) -> dict:
    """가입 직후 한 번. 반환 = 저장한 값(실패해도 값은 돌려준다 — 알림 줄에 쓴다)."""
    try:
        origin = origin if origin is not None else build()
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[유입] 가입 기록 만들기 실패: %s", exc)
        return {}
    try:
        from src.db import image_translate_queue_pg as st
        st.state_set(STATE_PREFIX + str(user_id), origin)
        logger.info("[유입] 가입 uid=%s… 유입=%s 랜딩=%s", str(user_id)[:8], referrer_host(origin), origin.get("landing_path"))
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[유입] 가입 기록 저장 실패(가입은 계속): %s", exc)
    return origin


def get(user_id: str) -> dict:
    from src.db import image_translate_queue_pg as st
    return st.state_get(STATE_PREFIX + str(user_id)) or {}


def referrer_host(origin: dict) -> str:
    host = urlparse(str((origin or {}).get("referrer") or "")).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def telegram_line(origin: dict) -> str:
    """「유입: <referrer 호스트 또는 직접> · <국가>」 — 국가는 모르면 뺀다."""
    line = f"유입: {referrer_host(origin) or '직접'}"
    if (origin or {}).get("country"):
        line += f" · {origin['country']}"
    return line
