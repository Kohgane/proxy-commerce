"""src/auth/user_store.py — 사용자 저장소 (Google Sheets backend, Phase 133).

users 워크시트 자동 부트스트랩.
컬럼: user_id, email, name, avatar_url, role, email_verified, active,
       created_at, last_login_at, social_accounts_json,
       password_hash, reset_token, reset_token_exp
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from .models import User

logger = logging.getLogger(__name__)

_WORKSHEET_NAME = "users"
_HEADERS = [
    "user_id",
    "email",
    "name",
    "avatar_url",
    "role",
    "email_verified",
    "active",
    "created_at",
    "last_login_at",
    "social_accounts_json",
    "password_hash",
    "reset_token",
    "reset_token_exp",
]


def _get_worksheet():
    """Google Sheets users 워크시트 반환 (없으면 자동 생성)."""
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        from src.utils.sheets import SCOPES, _get_credentials_dict

        creds_dict = _get_credentials_dict()
        if not creds_dict:
            return None
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        if not sheet_id:
            return None
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)

        # 워크시트 자동 부트스트랩
        try:
            ws = spreadsheet.worksheet(_WORKSHEET_NAME)
        except Exception:
            ws = spreadsheet.add_worksheet(title=_WORKSHEET_NAME, rows=100, cols=len(_HEADERS))
            ws.append_row(_HEADERS)
        return ws
    except Exception as exc:
        logger.warning("user_store: 워크시트 연결 실패: %s", exc)
        return None


class UserStore:
    """사용자 CRUD — Google Sheets 백엔드."""

    def __init__(self) -> None:
        self._ws = None  # 지연 초기화

    def _get_ws(self):
        if self._ws is None:
            self._ws = _get_worksheet()
        return self._ws

    def _all_rows(self) -> List[dict]:
        ws = self._get_ws()
        if ws is None:
            return []
        try:
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("user_store: 전체 레코드 조회 실패: %s", exc)
            return []

    def find_by_email(self, email: str) -> Optional[User]:
        """이메일로 사용자 찾기."""
        for row in self._all_rows():
            if row.get("email", "").lower() == email.lower():
                u = User.from_row(row)
                if u.active:
                    return u
        return None

    def find_by_provider(self, provider: str, provider_user_id: str) -> Optional[User]:
        """소셜 프로바이더 + 사용자 ID로 찾기."""
        for row in self._all_rows():
            social_raw = row.get("social_accounts_json", "[]")
            try:
                accounts = json.loads(social_raw) if social_raw else []
            except (json.JSONDecodeError, TypeError):
                accounts = []
            for acc in accounts:
                if acc.get("provider") == provider and acc.get("provider_user_id") == provider_user_id:
                    u = User.from_row(row)
                    if u.active:
                        return u
        return None

    def find_by_id(self, user_id: str) -> Optional[User]:
        """user_id로 사용자 찾기."""
        for row in self._all_rows():
            if row.get("user_id") == user_id:
                u = User.from_row(row)
                if u.active:
                    return u
        return None

    def find_by_reset_token(self, token: str) -> Optional[User]:
        """비밀번호 재설정 토큰으로 사용자 찾기."""
        if not token:
            return None
        for row in self._all_rows():
            if row.get("reset_token") == token:
                u = User.from_row(row)
                if u.active:
                    return u
        return None

    def create(self, user: User) -> User:
        """신규 사용자 생성."""
        ws = self._get_ws()
        if ws is None:
            logger.warning("user_store: 시트 미연결 — 사용자 생성 건너뜀")
            return user
        try:
            row = user.to_row()
            ws.append_row([row.get(h, "") for h in _HEADERS])
            logger.info("user_store: 사용자 생성: %s", user.email)
        except Exception as exc:
            logger.warning("user_store: 사용자 생성 실패: %s", exc)
        return user

    def update(self, user: User) -> None:
        """사용자 정보 갱신 (email 기준으로 행 찾기)."""
        ws = self._get_ws()
        if ws is None:
            return
        try:
            cell = ws.find(user.user_id)
            if cell:
                row_data = user.to_row()
                ws.update(f"A{cell.row}:{chr(64 + len(_HEADERS))}{cell.row}",
                          [[row_data.get(h, "") for h in _HEADERS]])
        except Exception as exc:
            logger.warning("user_store: 사용자 갱신 실패: %s", exc)

    def link_social(self, user_id: str, provider_data: dict) -> None:
        """소셜 계정 연결 추가."""
        user = self.find_by_id(user_id)
        if not user:
            return
        # 중복 체크
        for acc in user.social_accounts:
            if acc.get("provider") == provider_data.get("provider")
               and acc.get("provider_user_id") == provider_data.get("provider_user_id")):
                return  # 이미 연결됨
        user.social_accounts.append({
            "provider": provider_data.get("provider", ""),
            "provider_user_id": provider_data.get("provider_user_id", ""),
            "linked_at": datetime.now(timezone.utc).isoformat(),
        })
        self.update(user)

    def update_last_login(self, user_id: str) -> None:
        """마지막 로그인 시간 갱신."""
        user = self.find_by_id(user_id)
        if not user:
            return
        user.last_login_at = datetime.now(timezone.utc).isoformat()
        self.update(user)


# 싱글톤 인스턴스 (app-level)
_store: Optional[UserStore] = None


def get_store() -> UserStore:
    global _store
    if _store is None:
        _store = UserStore()
    return _store
