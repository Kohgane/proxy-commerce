"""src/auth/personal_tokens.py — Personal Access Token 발급/검증/회수 (PG-only 전환).

1차 저장소 = **Supabase Postgres**(src.db.user_tokens_pg). 런타임 Sheets 폴백은 제거됐다.
PG 미설정 시에는 **인메모리**(개발/테스트 전용, 비영속)만 쓴다 — 프로덕션(APP_ENV=production)에서
PG가 없으면 부팅 자체가 실패한다(order_webhook 부팅 가드).

보안:
- raw 토큰은 생성 시 1회만 표시 (이후 불가)
- SHA-256 해시 저장(원문 저장 0)
- scopes: collect.write / catalog.read / markets.write
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets

logger = logging.getLogger(__name__)

_TOKEN_PREFIX = "kgp_"
_TOKEN_PREFIX_LEGACY = "tok_"  # Phase 135 이전 발급분 호환
_DEFAULT_EXPIRY_DAYS = 365
_IDLE_EXPIRY_DAYS = 90        # v81 STEP2: 90일 미사용 자동 만료(유휴 토큰 위생)
_VALID_SCOPES = {"collect.write", "catalog.read", "markets.write"}


def _parse_dt(s):
    try:
        dt = datetime.fromisoformat(str(s or "").replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:   # naive 저장분(offset 없는 ISO) → UTC 취급(aware 비교 안전)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_hard_expired(row, now) -> bool:
    dt = _parse_dt(row.get("expires_at", ""))
    return bool(dt and now > dt)


def _is_idle_expired(row, now) -> bool:
    """v81 STEP2: 최근 사용(없으면 발급) 시각 + 90일 < 지금이면 유휴 만료."""
    dt = _parse_dt(row.get("last_used_at") or row.get("created_at") or "")
    return bool(dt and now > dt + timedelta(days=_IDLE_EXPIRY_DAYS))

# 인증 캐시(TTL 5분) — revoke는 PG에 즉시 커밋되지만, 다른 워커의 캐시는 최대 5분 남을 수 있다.
_token_cache: dict = {}
_CACHE_TTL_SEC = 300

# 인메모리 저장소 — PG 미설정(개발/테스트) 전용. 비영속.
#   각 항목: {token_hash, user_id, scopes(list), created_at, last_used_at, expires_at, revoked(bool)}
_in_memory: list[dict] = []


class TokenStoreCommitError(RuntimeError):
    """토큰 저장소 커밋 실패."""


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _pg_tokens():
    """Postgres 백엔드 활성 시 user_tokens_pg 반환(스키마 1회), 아니면 None(인메모리)."""
    try:
        from src.db import pg as _pgmod
        if _pgmod.pg_enabled():
            _pgmod.init_schema()
            from src.db import user_tokens_pg as _tpg
            return _tpg
    except Exception as exc:
        logger.warning("PG 토큰 백엔드 확인 실패 — 인메모리 폴백: %s", exc)
    return None


def generate_token(user_id: str, scopes: list = None, expires_days: int = _DEFAULT_EXPIRY_DAYS) -> dict:
    """새 Personal Access Token 발급. PG면 트랜잭션 커밋 후 durable, 아니면 인메모리."""
    scopes = scopes or ["collect.write"]
    scopes = [s for s in scopes if s in _VALID_SCOPES] or ["collect.write"]

    raw_token = f"{_TOKEN_PREFIX}{secrets.token_hex(30)}"
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_dt = now + timedelta(days=expires_days)
    expires_at = expires_dt.isoformat()

    _tp = _pg_tokens()
    if _tp is not None:
        if not _tp.insert(user_id, token_hash, scopes, expires_dt):
            raise TokenStoreCommitError("토큰을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.")
        logger.info("Personal Token 발급(PG): user=%s scopes=%s", user_id, scopes)
    else:
        _in_memory.append({
            "token_hash": token_hash, "user_id": str(user_id), "scopes": list(scopes),
            "created_at": now.isoformat(), "last_used_at": "", "expires_at": expires_at,
            "revoked": False,
        })
        logger.info("Personal Token 발급(인메모리): user=%s scopes=%s", user_id, scopes)

    return {
        "raw_token": raw_token, "token_hash": token_hash, "user_id": user_id,
        "scopes": scopes, "created_at": now.isoformat(), "expires_at": expires_at, "durable": True,
    }


def validate_token(raw_token: str, required_scopes: list = None) -> Optional[dict]:
    """토큰 검증 → 유효하면 {user_id, scopes, expires_at, token_hash}, 아니면 None."""
    required_scopes = required_scopes or []
    if not raw_token or not (raw_token.startswith(_TOKEN_PREFIX) or raw_token.startswith(_TOKEN_PREFIX_LEGACY)):
        return None

    token_hash = _hash_token(raw_token)
    cache_entry = _token_cache.get(token_hash)
    if cache_entry:
        cached_at, user_info = cache_entry
        if (datetime.now(timezone.utc).timestamp() - cached_at) < _CACHE_TTL_SEC:
            if _check_scopes(user_info.get("scopes", []), required_scopes):
                return user_info

    _tp = _pg_tokens()
    if _tp is not None:
        info = _tp.validate(token_hash, required_scopes)
        if info:
            _token_cache[token_hash] = (datetime.now(timezone.utc).timestamp(), info)
        return info

    now = datetime.now(timezone.utc)
    for row in _in_memory:
        if row.get("token_hash") != token_hash:
            continue
        if row.get("revoked"):
            return None
        exp = row.get("expires_at", "")
        if exp:
            try:
                if now > datetime.fromisoformat(exp.replace("Z", "+00:00")):
                    return None
            except ValueError:
                pass
        if _is_idle_expired(row, now):   # v81 STEP2: 90일 미사용 유휴 만료
            return None
        scopes = list(row.get("scopes", []))
        if not _check_scopes(scopes, required_scopes):
            return None
        row["last_used_at"] = now.isoformat()
        user_info = {"user_id": row.get("user_id", ""), "scopes": scopes,
                     "expires_at": row.get("expires_at", ""), "token_hash": token_hash}
        _token_cache[token_hash] = (now.timestamp(), user_info)
        return user_info
    return None


def _check_scopes(user_scopes: list, required_scopes: list) -> bool:
    if not required_scopes:
        return True
    return all(s in user_scopes for s in required_scopes)


def _identity_set(user_id, user_ids) -> set:
    """관용 식별자 집합 — 토큰이 별칭(user_id↔email)으로 발급돼도 본인 것으로 매칭(부활 방지)."""
    ids = set()
    if user_ids:
        ids |= {str(u) for u in user_ids if str(u or "").strip()}
    if user_id is not None and str(user_id).strip():
        ids.add(str(user_id))
    return ids


def revoke_token(token_hash: str, user_id: str, *, user_ids=None) -> bool:
    """토큰 회수(삭제). PG면 소프트삭제=durable, 아니면 인메모리 revoked=True. 실제 커밋 시에만 True."""
    id_set = _identity_set(user_id, user_ids)
    _tp = _pg_tokens()
    if _tp is not None:
        ok = _tp.revoke(token_hash, id_set)
        if ok:
            _token_cache.pop(token_hash, None)
        return ok

    for row in _in_memory:
        if row.get("token_hash") == token_hash and str(row.get("user_id", "")) in id_set and not row.get("revoked"):
            row["revoked"] = True
            _token_cache.pop(token_hash, None)
            logger.info("토큰 회수(인메모리): user=%s hash=%s...", user_id, token_hash[:8])
            return True
    return False


def token_active(user_id: str, token_hash: str) -> bool:
    """v81 STEP2: 해시가 활성(비회수·비만료·비유휴)인지 확인 — 북마클릿 토큰 재사용 판정용(신규 남발 방지).
    PG면 validate로 활성 여부만(부작용=last_used 갱신 허용), 아니면 인메모리 조회."""
    if not token_hash:
        return False
    _tp = _pg_tokens()
    if _tp is not None:
        try:
            return bool(_tp.validate(token_hash, []))
        except Exception:
            return False
    id_set = _identity_set(user_id, None)
    now = datetime.now(timezone.utc)
    for row in _in_memory:
        if row.get("token_hash") != token_hash:
            continue
        if str(row.get("user_id", "")) not in id_set:
            return False
        if row.get("revoked") or _is_hard_expired(row, now) or _is_idle_expired(row, now):
            return False
        return True
    return False


def list_tokens(user_id: str, *, user_ids=None) -> list:
    """사용자 토큰 목록(raw 미포함). PG면 PG, 아니면 인메모리."""
    id_set = _identity_set(user_id, user_ids)
    _tp = _pg_tokens()
    if _tp is not None:
        return _tp.list_for(id_set)

    result = []
    now = datetime.now(timezone.utc)
    for row in _in_memory:
        if str(row.get("user_id", "")) not in id_set:
            continue
        th = row.get("token_hash", "")
        result.append({
            "token_hash_prefix": th[:8] + "...",
            "token_hash": th,
            "scopes": list(row.get("scopes", [])),
            "created_at": row.get("created_at", ""),
            "last_used_at": row.get("last_used_at", ""),
            "expires_at": row.get("expires_at", ""),
            "revoked": bool(row.get("revoked")),
            "idle_expired": _is_idle_expired(row, now),   # v81 STEP2: 90일 미사용 유휴 만료(정직 표기)
        })
    return result
