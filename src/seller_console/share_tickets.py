"""P(오너 2026-10-01) — iOS 「URL 열기」가 `text=` 직후에서 URL을 자른다(운영 도착 기록: 쿼리 9자 `v=2&text=`).

두 갈래로 막는다.

## P1 이중 인코딩 수용
단축어가 「URL 인코딩」을 **두 번** 걸면 URL에 비ASCII가 하나도 없다(`%25E3%2580…`). 서버는 표준 디코드 1회 뒤에도
값이 `%XX`·안전 문자뿐이면 **한 번 더** 푼다(최대 2회) — 풀어서 CJK나 공백이 생길 때만 채택(영문 `%41` 같은 우연은 그대로).
iOS 「URL 인코딩」은 `:`·`/`를 바꾸지 않으므로(오너 실측) 안전 문자에 둘을 넣는다.

## P2 URL을 버리는 길(티켓)
단축어가 원문을 `POST /seller/collect/share-in`(양식 `text`)으로 보내면 서버가 **ASCII 짧은 티켓 URL 한 줄**을 돌려준다
(`…/seller/collect/share?v=3&t=<티켓>`). 단축어는 그 줄을 「URL 열기」에 넘긴다 — 잘릴 비ASCII가 URL에 없다.
  · 로그인 불필요(단축어는 쿠키가 없다). 남용 막이: IP당 분당 10건 · 티켓 10분 · 상품은 **로그인 뒤 티켓을 열 때만** 저장.
  · 원문은 티켓에만(10분) — 로그에는 길이만 남긴다(tk 봉인).
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

TTL_MIN = 10
RATE_PER_MIN = 10
_PREFIX = "share_ticket:"
_RL_PREFIX = "share_in_rl:"
_TICKET_RE = re.compile(r"^[A-Za-z0-9_-]{12,40}$")
_ENCODED_RE = re.compile(r"^(?:%[0-9A-Fa-f]{2}|[A-Za-z0-9._~:/-])+$")
_HAS_PCT = re.compile(r"%[0-9A-Fa-f]{2}")
_CJK = re.compile("[　-〿぀-ヿ㐀-䶿一-鿿가-힯＀-￯]")


def decode_again(value: str, *, max_extra: int = 2) -> tuple:
    """`(값, 추가 디코드 횟수)` — 표준 디코드 1회 뒤에도 값이 `%XX`·안전 문자뿐이면 최대 2회 더 푼다.

    채택은 풀린 결과에 **CJK나 공백**이 생겼을 때만 — 영문 값의 우연한 `%41`은 그대로 둔다.
    """
    orig = str(value or "")
    v, n = orig, 0
    while n < max_extra and _ENCODED_RE.match(v) and _HAS_PCT.search(v):
        nxt = unquote(v)
        if nxt == v:
            break
        v, n = nxt, n + 1
    if n and (_CJK.search(v) or re.search(r"\s", v)):
        return v, n
    return orig, 0


# ── 저장(app_state — PG면 워커 여럿이 같은 티켓을 본다) ─────────────────────────

def _st():
    from src.db import image_translate_queue_pg as st
    return st


def _now():
    return datetime.now(timezone.utc)


def _pg():
    try:
        from src.db import pg
        return pg if pg.pg_enabled() else None
    except Exception:
        return None


class RateLimited(Exception):
    pass


def _rate_take(ip: str) -> bool:
    """이 IP의 이번 분 몫을 1 올린다(원자적) — 상한이면 False."""
    from src.db import option_translate_queue_pg as q
    key = f"{_RL_PREFIX}{ip or '-'}:{_now().strftime('%Y%m%d%H%M')}"
    granted, _n = q.take_n(key, RATE_PER_MIN, 1)
    return bool(granted)


def prune() -> None:
    """만료된 티켓·지난 분의 레이트 칸을 지운다(만들 때마다 — 표가 쌓이지 않게)."""
    pg = _pg()
    if pg:
        with pg.tx() as cur:
            cur.execute("DELETE FROM app_state WHERE (key LIKE %s AND updated_at < now() - interval '15 minutes') "
                        "OR (key LIKE %s AND updated_at < now() - interval '5 minutes')",
                        (_PREFIX + "%", _RL_PREFIX + "%"))
        return
    st = _st()
    with st._LOCK:
        for k in list(st._MEM_STATE.keys()):
            v = st._MEM_STATE.get(k) or {}
            if k.startswith(_PREFIX) and str(v.get("exp") or "") < _now().isoformat():
                st._MEM_STATE.pop(k, None)


def create(text: str, *, ip: str = "") -> str:
    """원문 → 티켓(ASCII 16자). 빈 글이면 ValueError, 레이트 상한이면 RateLimited."""
    t = str(text or "").strip()
    if not t:
        raise ValueError("empty")
    if not _rate_take(ip):
        raise RateLimited(ip)
    try:
        prune()
    except Exception:
        pass
    ticket = secrets.token_urlsafe(12)
    _st().state_set(_PREFIX + ticket, {"text": t[:4000], "exp": (_now() + timedelta(minutes=TTL_MIN)).isoformat(),
                                       "used": False})
    return ticket


def read(ticket: str) -> dict:
    """`{ok, text, reason}` — reason: `bad`(모양이 틀림=위조) · `expired`(없거나 지남)."""
    tk = str(ticket or "").strip()
    if not _TICKET_RE.match(tk):
        return {"ok": False, "text": "", "reason": "bad"}
    v = _st().state_get(_PREFIX + tk) or {}
    if not v or str(v.get("exp") or "") < _now().isoformat():
        return {"ok": False, "text": "", "reason": "expired"}
    return {"ok": True, "text": str(v.get("text") or ""), "reason": "", "used": bool(v.get("used"))}


def mark_used(ticket: str) -> None:
    """로그인 뒤 담기까지 간 티켓 — 지우지 않는다(새로고침하면 「이미 담은 상품」으로 이어지게, 만료는 그대로)."""
    tk = str(ticket or "").strip()
    v = _st().state_get(_PREFIX + tk) or {}
    if v:
        v["used"] = True
        _st().state_set(_PREFIX + tk, v)
