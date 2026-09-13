"""src/db/user_tokens_pg.py — 수집기 토큰 Postgres 백엔드(이관 1단계).

personal_tokens가 토큰/해시를 만들고, 저장·조회·검증·회수만 이 모듈(PG)에 위임한다.
트랜잭션 커밋 후에만 성공 → 토큰 저장→재시작→유지(영속). 해시만 저장(시크릿 원문 0).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from . import pg

logger = logging.getLogger(__name__)


def insert(user_id: str, token_hash: str, scopes: list, expires_at: datetime) -> bool:
    """토큰 저장(커밋 후 True). 해시 유니크(활성) — 충돌 시 False."""
    with pg.tx() as cur:
        cur.execute(
            """INSERT INTO user_tokens (user_id, token_hash, token_prefix, scopes, status, expires_at)
               VALUES (%s,%s,%s,%s,'active',%s)
               ON CONFLICT (token_hash) WHERE deleted_at IS NULL DO NOTHING
               RETURNING id""",
            (user_id, token_hash, (token_hash or "")[:8], json.dumps(scopes), expires_at))
        return cur.fetchone() is not None


def validate(token_hash: str, required_scopes: list) -> dict | None:
    """유효 토큰이면 user_info 반환(+ last_used 갱신), 아니면 None."""
    now = datetime.now(timezone.utc)
    with pg.tx() as cur:
        cur.execute("SELECT user_id, scopes, status, expires_at FROM user_tokens WHERE token_hash=%s AND deleted_at IS NULL LIMIT 1",
                    (token_hash,))
        r = cur.fetchone()
        if not r:
            return None
        user_id, scopes_raw, status, expires_at = r
        if str(status) == "revoked":
            return None
        if expires_at and now > expires_at:
            return None
        try:
            scopes = json.loads(scopes_raw) if scopes_raw else []
        except Exception:
            scopes = []
        if required_scopes and not all(s in scopes for s in required_scopes):
            return None
        cur.execute("UPDATE user_tokens SET last_used_at=%s WHERE token_hash=%s AND deleted_at IS NULL",
                    (now, token_hash))
    return {"user_id": user_id or "", "scopes": scopes,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat() if expires_at else "",
            "token_hash": token_hash}


def revoke(token_hash: str, id_set: set) -> bool:
    """본인 토큰이면 status=revoked(이력 보존). 커밋된 경우만 True."""
    if not id_set:
        return False
    with pg.tx() as cur:
        cur.execute("UPDATE user_tokens SET status='revoked' WHERE token_hash=%s AND user_id = ANY(%s) AND deleted_at IS NULL AND status<>'revoked' RETURNING id",
                    (token_hash, list(id_set)))
        return cur.fetchone() is not None


def list_for(id_set: set) -> list:
    if not id_set:
        return []
    with pg.query() as cur:
        # C-F17-A5: `user_id`를 안 싣고 있었다 — 화면의 「발급 계정」 칸이 늘 비어 있던 이유다
        #   (칸은 C-F15가 만들었는데 채울 값이 오지 않았다). 이름 짓기는 화면이 아니라
        #   `account_label`이 하고, 여기서는 원값만 올려 준다.
        cur.execute("SELECT token_hash, scopes, created_at, last_used_at, expires_at, status, user_id FROM user_tokens WHERE user_id = ANY(%s) AND deleted_at IS NULL ORDER BY created_at DESC",
                    (list(id_set),))
        out = []
        for token_hash, scopes_raw, created_at, last_used_at, expires_at, status, user_id in cur.fetchall():
            try:
                scopes = json.loads(scopes_raw) if scopes_raw else []
            except Exception:
                scopes = []
            out.append({
                "token_hash_prefix": (token_hash or "")[:8] + "...",
                "token_hash": token_hash,
                "scopes": scopes,
                "created_at": created_at.astimezone(timezone.utc).isoformat() if created_at else "",
                "last_used_at": last_used_at.astimezone(timezone.utc).isoformat() if last_used_at else "",
                "expires_at": expires_at.astimezone(timezone.utc).isoformat() if expires_at else "",
                "revoked": str(status) == "revoked",
                "user_id": str(user_id or ""),
            })
        return out
