"""src/auth/password_accounts.py — 이메일+비밀번호 계정 한 곳 (AUTH-1, 오너 2026-09-30).

## 실측

가입 → 「가입이 완료되었습니다」 → 같은 자격으로 로그인 → 「이메일 또는 비밀번호가 올바르지 않습니다」.
로그인 코드엔 인증 게이트가 **없었다.** 원인은 저장소였다:

1. 계정 행이 Google Sheets `users`에 있었고, gspread 6 `get_all_records`는 문자열 `"1"`을 **숫자 1**로 준다.
   `User.from_row`의 `active == "1"`이 늘 거짓 → **모든 시트 계정이 비활성** → `find_by_email`이 늘 None.
2. 시트 쓰기가 실패해도(429·연결) 경고 로그만 남기고 화면은 「가입 완료」.
3. 한편 정체성 표(PG)엔 이메일이 적혀 → 다시 가입하면 「이미 등록된 이메일」. **가입도 로그인도 안 되는 고리.**

## 무엇을 바꾸나

- 계정은 **PG `password_accounts`**(커밋 확인 뒤에만 성공). PG가 없으면 인메모리(개발·테스트).
- 옛 시트 계정은 **읽는 입구로만** 남긴다 — 찾으면 해시 그대로 PG로 옮겨 적는다(새로 만들지 않는다).
- 실패는 삼키지 않는다: 호출부가 **원인 코드 + 한국어 원문**을 화면에 적는다.
"""
from __future__ import annotations

import logging
import os

from src.db import password_accounts_pg as store
from src.db.password_accounts_pg import AccountExists  # noqa: F401 — 호출부가 여기서 가져간다

logger = logging.getLogger(__name__)


class StoreDown(Exception):
    """계정 저장소에 닿지 못했다(연결·쿼리 실패) — 「없는 계정」과 다르다."""


def require_email_verify() -> bool:
    """이메일 인증을 로그인 조건으로 쓸지 — 오너 결정(㊼ 2026-09-30): 기본 끔."""
    return str(os.getenv("AUTH_REQUIRE_EMAIL_VERIFY", "0")).strip().lower() in ("1", "true", "yes", "on")


def _legacy_sheet_account(email: str) -> dict | None:
    """옛 시트 `users`의 비밀번호 계정 — 있으면 row dict, 없거나 못 읽으면 None."""
    try:
        from .user_store import get_store
        u = get_store().find_by_email(email)
    except Exception as exc:
        logger.warning("옛 시트 계정 조회 실패: %s", exc)
        return None
    if not u or not getattr(u, "password_hash", ""):
        return None
    return {"user_id": u.user_id, "email": store.norm_email(u.email), "name": u.name or "",
            "role": u.role or "seller", "password_hash": u.password_hash,
            "email_verified": bool(u.email_verified)}


def find(email: str) -> dict | None:
    """이 이메일의 비밀번호 계정. 없으면 None. 저장소가 죽었으면 `StoreDown`."""
    mail = store.norm_email(email)
    if not mail:
        return None
    try:
        row = store.get_by_email(mail)
    except Exception as exc:
        raise StoreDown(str(exc)) from exc
    if row:
        return row
    legacy = _legacy_sheet_account(mail)
    if not legacy:
        return None
    # 정본 user_id는 정체성 표가 쥔다(시트 행의 UUID는 C-F17-A1 때 흩어진 값일 수 있다).
    uid = legacy["user_id"]
    try:
        from src.db import user_identities_pg as ident
        uid = ident.resolve("password", mail) or uid
    except Exception:
        pass
    try:
        return store.create(user_id=uid, email=mail, password_hash=legacy["password_hash"],
                            name=legacy["name"], role=legacy["role"],
                            email_verified=legacy["email_verified"], source="sheets")
    except AccountExists:
        return store.get_by_email(mail)
    except Exception as exc:
        # 옮겨 적기 실패해도 이번 로그인은 시트 값으로 된다(다음 로그인에 다시 옮긴다).
        logger.warning("옛 시트 계정 옮겨 적기 실패(이번 로그인은 시트 값으로): %s", exc)
        return dict(legacy, user_id=uid, verify_token="", reset_token="", reset_token_exp="", source="sheets")


def create(**kw) -> dict:
    """새 계정 — 커밋·재조회까지 확인. 같은 이메일이면 `AccountExists`, 저장 실패면 예외 그대로."""
    return store.create(**kw)


def update(email: str, **fields) -> bool:
    return store.update(email, **fields)


def by_token(kind: str, token: str) -> dict | None:
    try:
        return store.get_by_token(kind, token)
    except Exception as exc:
        raise StoreDown(str(exc)) from exc


def touch_login(email: str) -> None:
    store.touch_login(email)


def reset_for_tests() -> None:
    store.reset_for_tests()
