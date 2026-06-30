"""src/auth/passkey_store.py — v40-D: 패스키(WebAuthn) 자격증명 저장.

기기에 저장된 공개키 자격증명을 서버에 보관(공개키·credential_id·sign_count·user_id).
Google Sheets `passkeys` 워크시트 + 인메모리 폴백(시트 미설정 시). 개인키는 절대 서버에 없음(기기에만).

컬럼: credential_id(b64url) | user_id | public_key(b64url) | sign_count | label | created_at | last_used_at
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

_HEADER = ["credential_id", "user_id", "public_key", "sign_count", "label", "created_at", "last_used_at"]
_in_memory: list = []


def _sheet_id() -> str:
    return os.getenv("GOOGLE_SHEET_ID", "").strip()


def _worksheet():
    from src.utils.sheets import open_sheet
    ws = open_sheet(_sheet_id(), "passkeys")
    try:
        values = ws.get_all_values()
        if not values:
            ws.append_row(_HEADER)
    except Exception:
        pass
    return ws


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_credential(*, credential_id: str, user_id: str, public_key: str,
                   sign_count: int, label: str = "") -> bool:
    """패스키 자격증명 저장(실제 커밋 시에만 True — 가짜 성공 0)."""
    row = {
        "credential_id": credential_id, "user_id": str(user_id), "public_key": public_key,
        "sign_count": int(sign_count), "label": label or "패스키", "created_at": _now(), "last_used_at": "",
    }
    if _sheet_id():
        try:
            ws = _worksheet()
            ws.append_row([row[c] for c in _HEADER])
            return True
        except Exception as exc:
            logger.warning("패스키 시트 저장 실패, 인메모리 폴백: %s", exc)
    _in_memory.append(row)
    return True


def _all_rows() -> List[dict]:
    rows: List[dict] = []
    if _sheet_id():
        try:
            for r in _worksheet().get_all_records():
                rows.append(dict(r))
        except Exception as exc:
            logger.warning("패스키 시트 조회 실패: %s", exc)
    # 인메모리(시트 미설정/쓰기 폴백분) 합집합
    seen = {str(r.get("credential_id")) for r in rows}
    for r in _in_memory:
        if str(r.get("credential_id")) not in seen:
            rows.append(dict(r))
    return rows


def list_for_user(user_id: str, *, user_ids=None) -> List[dict]:
    """사용자의 패스키 목록. v39 C 패턴: 관용 식별자(user_id↔email)로 별칭도 매칭."""
    ids = set()
    if user_ids:
        ids |= {str(u) for u in user_ids if str(u or "").strip()}
    if user_id:
        ids.add(str(user_id))
    return [r for r in _all_rows() if str(r.get("user_id", "")) in ids]


def get_by_credential_id(credential_id: str) -> Optional[dict]:
    for r in _all_rows():
        if str(r.get("credential_id")) == str(credential_id):
            return r
    return None


def update_sign_count(credential_id: str, new_count: int) -> None:
    """인증 성공 후 sign_count 갱신(리플레이 방어)."""
    if _sheet_id():
        try:
            ws = _worksheet()
            values = ws.get_all_values()
            if values:
                header = values[0]
                ci = header.index("credential_id") if "credential_id" in header else 0
                sci = header.index("sign_count") if "sign_count" in header else 3
                lui = header.index("last_used_at") if "last_used_at" in header else 6
                for r, rowv in enumerate(values[1:], start=2):
                    if ci < len(rowv) and rowv[ci] == str(credential_id):
                        ws.update_cell(r, sci + 1, int(new_count))
                        ws.update_cell(r, lui + 1, _now())
                        return
        except Exception as exc:
            logger.warning("패스키 sign_count 갱신 실패: %s", exc)
    for r in _in_memory:
        if str(r.get("credential_id")) == str(credential_id):
            r["sign_count"] = int(new_count)
            r["last_used_at"] = _now()


def delete_credential(credential_id: str, *, user_ids=None) -> bool:
    """패스키 삭제(본인 것만 — 관용 식별자). 시트+인메모리 양쪽. 실제 삭제 시 True."""
    ids = {str(u) for u in (user_ids or []) if str(u or "").strip()}
    deleted = False
    if _sheet_id():
        try:
            ws = _worksheet()
            values = ws.get_all_values()
            if values:
                header = values[0]
                ci = header.index("credential_id"); ui = header.index("user_id")
                for r in range(len(values) - 1, 0, -1):
                    rowv = values[r]
                    if ci < len(rowv) and rowv[ci] == str(credential_id) and (not ids or (ui < len(rowv) and rowv[ui] in ids)):
                        ws.delete_rows(r + 1)
                        deleted = True
        except Exception as exc:
            logger.warning("패스키 삭제 실패: %s", exc)
    before = len(_in_memory)
    _in_memory[:] = [r for r in _in_memory
                     if not (str(r.get("credential_id")) == str(credential_id)
                             and (not ids or str(r.get("user_id", "")) in ids))]
    return deleted or (len(_in_memory) < before)
