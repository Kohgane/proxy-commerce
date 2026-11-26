"""오너 11-26 오후 ④ — 애플 로그인 계정을 지울 때 애플 쪽 토큰도 폐기한다(앱스토어 심사 5.1.1(v) · Sign in with Apple 요건).

애플 로그인 콜백이 받은 `refresh_token`을 **암호화해서만**(마켓 키와 같은 Fernet) `app_state apple_tokens`에 사용자별로 둔다.
암호화 키가 없으면 저장하지 않는다(평문 보관 금지) — 그때 폐기는 「토큰 없음」으로 사실대로 남는다.
계정 삭제 실행(오너 탭) 때 `revoke(user_id)` → `POST https://appleid.apple.com/auth/revoke`(token_type_hint=refresh_token).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger(__name__)

KEY = "apple_tokens"


def _f():
    from src.seller_console.market_credentials import _fernet
    return _fernet()


def _all() -> Dict:
    from src.db import image_translate_queue_pg as st
    return dict(st.state_get(KEY) or {})


def _save_all(d: Dict) -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(KEY, d)


def save(user_id: str, refresh_token: str) -> bool:
    if not (user_id and refresh_token):
        return False
    f = _f()
    if f is None:
        logger.warning("[애플 토큰] 암호화 키가 없어 refresh token을 저장하지 않음(평문 보관 금지) user=%s", user_id)
        return False
    d = _all()
    d[str(user_id)] = {"enc": f.encrypt(refresh_token.encode()).decode(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _save_all(d)
    return True


def has(user_id: str) -> bool:
    return str(user_id) in _all()


def revoke(user_id: str, *, provider=None) -> Dict:
    """`{ok, step}` — 계정 삭제 단계 줄에 그대로 적는다. 토큰이 없으면 ok=True(폐기할 것 없음) + 사유."""
    rec = _all().get(str(user_id))
    if not rec:
        return {"ok": True, "step": "애플 토큰 없음(애플 로그인 아님 · 저장 전 가입)"}
    f = _f()
    if f is None:
        return {"ok": False, "step": "실패: 암호화 키가 없어 저장된 애플 토큰을 못 풀어요"}
    try:
        token = f.decrypt(rec["enc"].encode()).decode()
    except Exception as exc:                                       # noqa: BLE001
        return {"ok": False, "step": f"실패: 애플 토큰 풀기 — {type(exc).__name__}"}
    if provider is None:
        from src.auth.providers.apple import AppleProvider
        provider = AppleProvider()
    res = provider.revoke(token)
    if res.get("ok"):
        d = _all()
        d.pop(str(user_id), None)
        _save_all(d)
        return {"ok": True, "step": "애플 토큰 폐기(appleid.apple.com/auth/revoke 200)"}
    return {"ok": False, "step": "실패: 애플 폐기 — " + str(res.get("error") or "응답 원문 없음")[:200]}
