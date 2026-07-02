"""src/auth/personal_tokens.py — Personal Access Token 발급/검증/회수 (Phase 135).

토큰 저장: Google Sheets `personal_tokens` 워크시트
  columns: token_hash | user_id | scopes_json | created_at | last_used_at | expires_at | revoked

보안:
- raw 토큰은 생성 시 1회만 표시 (이후 불가)
- SHA-256 해시 저장
- scopes: collect.write / catalog.read / markets.write
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "personal_tokens"
_TOKEN_PREFIX = "kgp_"
_TOKEN_PREFIX_LEGACY = "tok_"  # Phase 135 이전 발급분 호환
_TOKEN_LENGTH = 64  # 총 길이 (prefix 포함)
_DEFAULT_EXPIRY_DAYS = 365
_VALID_SCOPES = {"collect.write", "catalog.read", "markets.write"}

# 인메모리 캐시 (Sheets 부하 감소, TTL 5분)
_token_cache: dict = {}
_CACHE_TTL_SEC = 300


class TokenStoreCommitError(RuntimeError):
    """토큰 저장소 커밋 실패."""


def _hash_token(raw: str) -> str:
    """SHA-256 해시 반환."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_worksheet():
    """personal_tokens 워크시트 반환."""
    from src.utils.sheets import open_sheet
    return open_sheet(_SHEET_ID, _WS_NAME)


def _ensure_headers(ws) -> None:
    """헤더 행 없으면 생성."""
    try:
        first_row = ws.row_values(1)
        if not first_row or first_row[0] != "token_hash":
            ws.insert_row(
                ["token_hash", "user_id", "scopes_json", "created_at", "last_used_at", "expires_at", "revoked"],
                index=1,
            )
    except Exception:
        pass


def _sheet_records(ws=None) -> list[dict]:
    ws = ws or _get_worksheet()
    return ws.get_all_records()


def _find_token_row(token_hash: str, *, ws=None) -> Optional[dict]:
    for row in _sheet_records(ws):
        if row.get("token_hash") == token_hash:
            return row
    return None


def generate_token(user_id: str, scopes: list = None, expires_days: int = _DEFAULT_EXPIRY_DAYS) -> dict:
    """새 Personal Access Token 발급.

    Args:
        user_id: 사용자 ID
        scopes: 권한 목록 (기본: ["collect.write"])
        expires_days: 만료 일수

    Returns:
        {raw_token: str, token_hash: str, scopes: list, expires_at: str}
        raw_token은 1회만 반환됨
    """
    scopes = scopes or ["collect.write"]
    # 유효한 스코프만 허용
    scopes = [s for s in scopes if s in _VALID_SCOPES]
    if not scopes:
        scopes = ["collect.write"]

    # 토큰 생성: kgp_ + 60자리 랜덤 hex
    raw_suffix = secrets.token_hex(30)  # 60자
    raw_token = f"{_TOKEN_PREFIX}{raw_suffix}"
    token_hash = _hash_token(raw_token)

    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=expires_days)).isoformat()

    row = [
        token_hash,
        user_id,
        json.dumps(scopes),
        now.isoformat(),
        "",       # last_used_at
        expires_at,
        "false",  # revoked
    ]

    if not _SHEET_ID:
        raise TokenStoreCommitError("토큰 저장소가 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.")

    try:
        ws = _get_worksheet()
        _ensure_headers(ws)
        ws.append_row(row)
        saved = _find_token_row(token_hash, ws=ws)
        if not saved or str(saved.get("user_id", "")) != str(user_id):
            raise TokenStoreCommitError("토큰을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.")
        logger.info("Personal Token 발급: user=%s scopes=%s", user_id, scopes)
    except TokenStoreCommitError:
        raise
    except Exception as exc:
        logger.error("토큰 저장 실패: %s", exc)
        raise TokenStoreCommitError("토큰을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.") from exc

    return {
        "raw_token": raw_token,
        "token_hash": token_hash,
        "user_id": user_id,
        "scopes": scopes,
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "durable": True,
    }


def validate_token(raw_token: str, required_scopes: list = None) -> Optional[dict]:
    """토큰 검증.

    Args:
        raw_token: 원본 토큰 문자열
        required_scopes: 필요한 권한 목록

    Returns:
        유효한 경우 {user_id, scopes, expires_at}, 없으면 None
    """
    required_scopes = required_scopes or []
    if not raw_token or not (raw_token.startswith(_TOKEN_PREFIX) or raw_token.startswith(_TOKEN_PREFIX_LEGACY)):
        return None

    token_hash = _hash_token(raw_token)

    # 캐시 확인
    cache_entry = _token_cache.get(token_hash)
    if cache_entry:
        cached_at, user_info = cache_entry
        if (datetime.now(timezone.utc).timestamp() - cached_at) < _CACHE_TTL_SEC:
            if _check_scopes(user_info.get("scopes", []), required_scopes):
                return user_info

    if not _SHEET_ID:
        return None

    try:
        ws = _get_worksheet()
        records = _sheet_records(ws)
        now = datetime.now(timezone.utc)

        for row in records:
            if row.get("token_hash") != token_hash:
                continue
            if str(row.get("revoked", "false")).lower() == "true":
                return None
            expires_at_str = row.get("expires_at", "")
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    if now > expires_at:
                        return None
                except ValueError:
                    pass

            scopes_raw = row.get("scopes_json", "[]")
            try:
                scopes = json.loads(scopes_raw)
            except Exception:
                scopes = []

            if not _check_scopes(scopes, required_scopes):
                return None

            user_info = {
                "user_id": row.get("user_id", ""),
                "scopes": scopes,
                "expires_at": row.get("expires_at", ""),
                "token_hash": token_hash,
            }

            # 캐시 저장
            _token_cache[token_hash] = (now.timestamp(), user_info)

            # last_used_at 갱신 (비동기적으로 해도 되지만 간단히 동기 처리)
            try:
                # 행 번호 찾기 (헤더 포함 +2)
                row_idx = records.index(row) + 2
                ws.update_cell(row_idx, 5, now.isoformat())
            except Exception:
                pass

            return user_info

    except Exception as exc:
        logger.warning("토큰 검증 오류: %s", exc)

    return None


def _check_scopes(user_scopes: list, required_scopes: list) -> bool:
    """사용자 스코프에 필요한 권한이 모두 포함되어 있는지 확인."""
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
    """토큰 회수(삭제).

    v39 C: user_ids(관용 식별자 집합)를 주면 별칭(user_id↔email) 불일치로 삭제 0건 →
    재진입 시 부활하던 버그를 방지(시트 revoked=true 영속 커밋). user_ids 미지정 시 exact user_id.

    Returns:
        성공 여부(실제 시트 커밋됐을 때만 True — 가짜 성공 0).
    """
    if not _SHEET_ID:
        return False

    id_set = _identity_set(user_id, user_ids)
    try:
        ws = _get_worksheet()
        records = _sheet_records(ws)
        for i, row in enumerate(records):
            if row.get("token_hash") == token_hash and str(row.get("user_id", "")) in id_set:
                row_idx = i + 2
                ws.update_cell(row_idx, 7, "true")  # revoked 컬럼
                persisted = _find_token_row(token_hash, ws=ws)
                if str((persisted or {}).get("revoked", "false")).lower() != "true":
                    logger.error("토큰 회수 검증 실패: hash=%s...", token_hash[:8])
                    return False
                _token_cache.pop(token_hash, None)
                logger.info("토큰 회수: user=%s hash=%s...", user_id, token_hash[:8])
                return True
    except Exception as exc:
        logger.error("토큰 회수 실패: %s", exc)

    return False


def list_tokens(user_id: str, *, user_ids=None) -> list:
    """사용자의 토큰 목록 반환 (raw 값 미포함).

    v39 C: user_ids(관용 식별자 집합)를 주면 별칭으로 발급된 토큰도 본인 목록에 보인다
    (보여야 삭제도 가능 — 삭제/표시 스코프 일치로 부활 방지). 미지정 시 exact user_id.

    Returns:
        [{token_hash_prefix, scopes, created_at, last_used_at, expires_at, revoked}]
    """
    if not _SHEET_ID:
        return []

    id_set = _identity_set(user_id, user_ids)
    result = []
    try:
        ws = _get_worksheet()
        records = _sheet_records(ws)
        for row in records:
            if str(row.get("user_id", "")) not in id_set:
                continue
            token_hash = row.get("token_hash", "")
            result.append({
                "token_hash_prefix": token_hash[:8] + "...",
                "token_hash": token_hash,
                "scopes": json.loads(row.get("scopes_json", "[]")),
                "created_at": row.get("created_at", ""),
                "last_used_at": row.get("last_used_at", ""),
                "expires_at": row.get("expires_at", ""),
                "revoked": str(row.get("revoked", "false")).lower() == "true",
            })
    except Exception as exc:
        logger.warning("토큰 목록 조회 실패: %s", exc)

    return result
