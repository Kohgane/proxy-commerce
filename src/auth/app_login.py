"""앱 v1.1(오너 2026-11-23) — 소셜 로그인 **앱 모드**의 1회용 코드.

아이폰 앱은 구글·카카오·네이버 로그인만 ASWebAuthenticationSession(사파리 쪽 창)으로 연다 — 구글이 웹뷰 로그인을 막는다.
그 창에서 로그인이 끝나도 앱 웹뷰에는 쿠키가 없다. 그래서:

1. `/auth/<p>/start?app=1&next=…` 로 시작한 로그인은 콜백 끝에서 세션을 여는 대신 **1회용 코드**를 만들어
   `gogabridj://auth?code=<코드>&next=…` 로 돌려준다.
2. 앱 웹뷰가 `GET /auth/app/exchange?code=…&next=…` 를 열면 그 코드로 **웹뷰에** 세션 쿠키를 심고 `next` 로 보낸다.

코드는 **60초 · 한 번만**. 저장은 `app_state`(PG면 워커 여럿이 같은 코드를 본다), 꺼낼 때 한 트랜잭션으로 「쓴 것」 표시 —
같은 코드를 두 번 내밀면 두 번째는 실패한다. 코드 값은 로그에 남기지 않는다.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

TTL_SEC = 60
_PREFIX = "app_login_code:"
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
APP_SCHEME = "gogabridj"


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prune() -> None:
    """지난 코드를 지운다(만들 때마다 — 표가 쌓이지 않게)."""
    try:
        from src.db import pg
        if pg.pg_enabled():
            with pg.tx() as cur:
                cur.execute("DELETE FROM app_state WHERE key LIKE %s AND updated_at < now() - interval '5 minutes'",
                            (_PREFIX + "%",))
            return
    except Exception:
        return
    st = _st()
    with st._LOCK:
        for k in list(st._MEM_STATE.keys()):
            v = st._MEM_STATE.get(k) or {}
            if k.startswith(_PREFIX) and str(v.get("exp") or "") < _now().isoformat():
                st._MEM_STATE.pop(k, None)


def issue(user) -> str:
    """로그인된 사용자 → 1회용 코드(60초). 세션에 싣는 값만 담는다(비밀번호·토큰 0)."""
    _prune()
    code = secrets.token_urlsafe(24)
    _st().state_set(_PREFIX + code, {
        "user_id": str(getattr(user, "user_id", "") or ""),
        "email": str(getattr(user, "email", "") or ""),
        "name": str(getattr(user, "name", "") or ""),
        "role": str(getattr(user, "role", "") or "seller"),
        "exp": (_now() + timedelta(seconds=TTL_SEC)).isoformat(),
        "used": False,
    })
    return code


def take(code: str) -> dict:
    """코드 → 사용자 값(한 번만). 모양이 틀림·없음·지남·이미 씀이면 빈 dict."""
    c = str(code or "").strip()
    if not _CODE_RE.match(c):
        return {}
    got: dict = {}

    def _mark(cur: dict) -> dict:
        if cur and not cur.get("used") and str(cur.get("exp") or "") >= _now().isoformat():
            got.update(cur)
        return {**(cur or {}), "used": True} if cur else {}

    _st().state_update(_PREFIX + c, _mark)
    return got if got.get("user_id") else {}


def app_callback_url(code: str, next_url: str) -> str:
    """`gogabridj://auth?code=…&next=…` — 앱의 ASWebAuthenticationSession이 이 스킴을 받아 창을 닫는다."""
    from urllib.parse import urlencode
    return f"{APP_SCHEME}://auth?" + urlencode({"code": code, "next": next_url})
