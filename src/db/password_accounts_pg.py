"""src/db/password_accounts_pg.py — 이메일+비밀번호 계정 저장소 (AUTH-1).

PG가 켜져 있으면 `password_accounts` 테이블, 아니면 **인메모리**(개발·테스트, 비영속).
쓰기는 **커밋된 뒤에만** 성공이다 — 실패하면 예외가 그대로 올라간다(호출부가 화면에 원인을 적는다).
시트 `users`가 쓰기 실패를 경고 로그로 삼켜 「가입 완료」를 띄우던 것의 반대편이다.

행 dict 키: user_id · email · name · role · password_hash · email_verified · verify_token ·
reset_token · reset_token_exp(ISO 문자열 또는 "") · source.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from src.db import pg

logger = logging.getLogger(__name__)

_FIELDS = ("user_id", "email", "name", "role", "password_hash", "email_verified",
           "verify_token", "reset_token", "reset_token_exp", "source")
_MEM: dict[str, dict] = {}          # email → row
_LOCK = threading.Lock()


class AccountExists(Exception):
    """같은 이메일 계정이 이미 있다(두 번째 가입은 덮어쓰지 않고 실패)."""


def _enabled() -> bool:
    try:
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    with _LOCK:
        _MEM.clear()


def norm_email(email) -> str:
    return str(email or "").strip().lower()


def _iso(v) -> str:
    if not v:
        return ""
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat()
    return str(v)


def _row(rec) -> dict:
    return {k: (_iso(v) if k == "reset_token_exp" else v) for k, v in zip(_FIELDS, rec)}


_SELECT = ("SELECT user_id, email, name, role, password_hash, email_verified, verify_token, "
           "reset_token, reset_token_exp, source FROM password_accounts ")


def get_by_email(email: str) -> dict | None:
    mail = norm_email(email)
    if not mail:
        return None
    if not _enabled():
        with _LOCK:
            r = _MEM.get(mail)
            return dict(r) if r else None
    with pg.query() as cur:
        cur.execute(_SELECT + "WHERE email = %s AND deleted_at IS NULL", (mail,))
        rec = cur.fetchone()
    return _row(rec) if rec else None


def get_by_token(kind: str, token: str) -> dict | None:
    """kind = verify | reset."""
    col = {"verify": "verify_token", "reset": "reset_token"}.get(kind)
    tok = str(token or "").strip()
    if not (col and tok):
        return None
    if not _enabled():
        with _LOCK:
            r = next((r for r in _MEM.values() if r.get(col) == tok), None)
            return dict(r) if r else None
    with pg.query() as cur:
        cur.execute(_SELECT + f"WHERE {col} = %s AND deleted_at IS NULL", (tok,))
        rec = cur.fetchone()
    return _row(rec) if rec else None


def create(*, user_id: str, email: str, password_hash: str, name: str = "", role: str = "seller",
           email_verified: bool = False, verify_token: str = "", source: str = "signup") -> dict:
    """새 계정. **커밋 뒤 다시 읽어** 돌려준다(쓰기-확인). 같은 이메일이 있으면 `AccountExists`."""
    mail = norm_email(email)
    if not (mail and user_id and password_hash):
        raise ValueError("user_id·email·password_hash는 비울 수 없다")
    row = {"user_id": str(user_id), "email": mail, "name": str(name or ""), "role": str(role or "seller"),
           "password_hash": str(password_hash), "email_verified": bool(email_verified),
           "verify_token": str(verify_token or ""), "reset_token": "", "reset_token_exp": "",
           "source": str(source or "signup")}
    if not _enabled():
        with _LOCK:
            if mail in _MEM:
                raise AccountExists(mail)
            _MEM[mail] = row
        return dict(row)
    try:
        with pg.tx() as cur:
            cur.execute(
                "INSERT INTO password_accounts (user_id, email, name, role, password_hash, email_verified, "
                "verify_token, source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (row["user_id"], mail, row["name"], row["role"], row["password_hash"],
                 row["email_verified"], row["verify_token"], row["source"]))
    except Exception as exc:
        if "uq_password_accounts_email" in str(exc) or "duplicate key" in str(exc).lower():
            raise AccountExists(mail) from exc
        raise
    saved = get_by_email(mail)
    if not saved or saved["user_id"] != row["user_id"]:
        raise RuntimeError("계정을 적었는데 다시 읽히지 않는다(커밋 확인 실패)")
    return saved


def update(email: str, **fields) -> bool:
    """허용 필드만 갱신 — 커밋되면 True, 계정이 없으면 False."""
    mail = norm_email(email)
    allowed = {k: v for k, v in fields.items()
               if k in ("password_hash", "email_verified", "verify_token", "reset_token",
                        "reset_token_exp", "name", "role")}
    if not (mail and allowed):
        return False
    if not _enabled():
        with _LOCK:
            if mail not in _MEM:
                return False
            _MEM[mail].update({k: ("" if v is None else v) for k, v in allowed.items()})
        return True
    sets = ", ".join(f"{k} = %s" for k in allowed) + ", updated_at = now()"
    vals = [(v or None) if k == "reset_token_exp" else v for k, v in allowed.items()]
    with pg.tx() as cur:
        cur.execute(f"UPDATE password_accounts SET {sets} WHERE email = %s AND deleted_at IS NULL",
                    (*vals, mail))
        return cur.rowcount > 0


def touch_login(email: str) -> None:
    mail = norm_email(email)
    if not mail or not _enabled():
        return
    try:
        with pg.tx() as cur:
            cur.execute("UPDATE password_accounts SET last_login_at = now() "
                        "WHERE email = %s AND deleted_at IS NULL", (mail,))
    except Exception as exc:
        logger.warning("마지막 로그인 시각 기록 실패(로그인은 됨): %s", exc)
