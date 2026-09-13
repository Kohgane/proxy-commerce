"""src/db/user_identities_pg.py — 로그인 정체성 저장소 (C-F19).

PG가 켜져 있으면 `user_identities` 테이블, 아니면 **인메모리**(개발·테스트, 비영속).

여긴 "누가 누구인가"만 적는다 — 비밀번호·토큰은 오지 않는다.
`(provider, email)`이 키고, 값은 **정본 user_id**다.
"""
from __future__ import annotations

import logging

from src.db import pg

logger = logging.getLogger(__name__)

# 인메모리 폴백: {(provider, email): {"user_id", "is_primary", "display_name"}}
_MEM: dict[tuple, dict] = {}


def _enabled() -> bool:
    try:
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    _MEM.clear()


def norm_email(email) -> str:
    return str(email or "").strip().lower()


def register(provider: str, email: str, user_id: str, *,
             is_primary: bool = False, display_name: str = "") -> bool:
    """`(provider, email) → user_id` 한 줄. 이미 있으면 갈아끼운다. 커밋됐을 때만 True."""
    prov, mail, uid = str(provider or "").strip().lower(), norm_email(email), str(user_id or "").strip()
    if not (prov and mail and uid):
        return False
    if not _enabled():
        _MEM[(prov, mail)] = {"user_id": uid, "is_primary": bool(is_primary),
                              "display_name": str(display_name or "")}
        return True
    with pg.tx() as cur:
        cur.execute(
            "INSERT INTO user_identities (provider, email, user_id, is_primary, display_name) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (provider, email) WHERE deleted_at IS NULL "
            "DO UPDATE SET user_id = EXCLUDED.user_id, is_primary = EXCLUDED.is_primary, "
            "              display_name = EXCLUDED.display_name",
            (prov, mail, uid, bool(is_primary), str(display_name or "")))
    return True


def resolve(provider: str, email: str) -> str:
    """이 (프로바이더, 이메일)의 정본 user_id. 없으면 빈 문자열."""
    prov, mail = str(provider or "").strip().lower(), norm_email(email)
    if not (prov and mail):
        return ""
    if not _enabled():
        return _MEM.get((prov, mail), {}).get("user_id", "")
    with pg.query() as cur:
        cur.execute("SELECT user_id FROM user_identities "
                    "WHERE provider = %s AND email = %s AND deleted_at IS NULL", (prov, mail))
        row = cur.fetchone()
    return str(row[0]) if row else ""


def resolve_any_provider(email: str) -> str:
    """**어느 프로바이더로든** 이 이메일이 이미 아는 사람인가 — 정본 user_id 또는 빈 문자열.

    구글로 처음 들어와도 hanmail로 이미 등록된 사람이면 같은 사람이다.
    이메일 소유 증명은 프로바이더가 한다(우리가 또 하지 않는다).
    """
    mail = norm_email(email)
    if not mail:
        return ""
    if not _enabled():
        for (_p, m), row in _MEM.items():
            if m == mail:
                return row.get("user_id", "")
        return ""
    with pg.query() as cur:
        cur.execute("SELECT user_id FROM user_identities WHERE email = %s AND deleted_at IS NULL "
                    "ORDER BY is_primary DESC, created_at ASC LIMIT 1", (mail,))
        row = cur.fetchone()
    return str(row[0]) if row else ""


def profile(user_id: str) -> dict:
    """이 사람의 **대표 이메일·표시 이름**. 없으면 빈 dict.

    화면·회신에 쓸 이름이 여기서 나온다 — 사용자 저장소(시트)가 닿지 않아도
    이건 PG에 있어서 답할 수 있다. (C-F17-A에서 시트가 죽어 이름이 통째로 사라졌다.)
    """
    uid = str(user_id or "").strip()
    if not uid:
        return {}
    if not _enabled():
        rows = [r for r in _MEM.values() if r.get("user_id") == uid]
        if not rows:
            return {}
        best = next((r for r in rows if r.get("is_primary")), rows[0])
        mail = next((m for (_p, m), r in _MEM.items() if r is best), "")
        return {"email": mail, "display_name": best.get("display_name", "")}
    with pg.query() as cur:
        cur.execute("SELECT email, display_name FROM user_identities "
                    "WHERE user_id = %s AND deleted_at IS NULL "
                    "ORDER BY is_primary DESC, created_at ASC LIMIT 1", (uid,))
        row = cur.fetchone()
    return {"email": str(row[0]), "display_name": str(row[1] or "")} if row else {}


def emails_for(user_id: str) -> list:
    """이 사람이 쓰는 이메일 전부(대표 먼저) — 진단·보고용."""
    uid = str(user_id or "").strip()
    if not uid:
        return []
    if not _enabled():
        out = [(m, r.get("is_primary")) for (_p, m), r in _MEM.items() if r.get("user_id") == uid]
        return [m for m, _pri in sorted(out, key=lambda x: (not x[1], x[0]))]
    with pg.query() as cur:
        cur.execute("SELECT DISTINCT email, bool_or(is_primary) AS pri FROM user_identities "
                    "WHERE user_id = %s AND deleted_at IS NULL GROUP BY email "
                    "ORDER BY pri DESC, email ASC", (uid,))
        return [str(r[0]) for r in cur.fetchall()]


def backup_rows(batch_id: str, rows: list) -> None:
    """병합 전 값을 백업표에 적는다 — **되돌릴 수 있어야 병합해도 된다.**

    rows: [(table_name, row_id, field, old_value, new_value), …]
    PG가 없으면 백업도 없다 → 그럴 땐 호출부가 병합 자체를 하지 않는다.
    """
    if not (rows and _enabled()):
        return
    with pg.tx() as cur:
        for table_name, row_id, field, old_value, new_value in rows:
            cur.execute(
                "INSERT INTO identity_merge_backup (batch_id, table_name, row_id, field, old_value, new_value) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (batch_id, table_name, str(row_id), field, str(old_value), str(new_value)))
