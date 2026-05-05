"""src/auth/models.py — 사용자 데이터 모델 (Phase 133)."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class User:
    """사용자 모델."""

    user_id: str
    email: str
    name: str
    avatar_url: str = ""
    role: str = "seller"          # seller / admin
    email_verified: bool = False
    active: bool = True
    created_at: str = ""          # ISO 8601
    last_login_at: Optional[str] = None
    social_accounts: List[dict] = field(default_factory=list)  # [{provider, provider_user_id, linked_at}]
    password_hash: str = ""
    reset_token: str = ""
    reset_token_exp: str = ""

    def to_row(self) -> dict:
        """Google Sheets 행으로 직렬화."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "email_verified": "1" if self.email_verified else "0",
            "active": "1" if self.active else "0",
            "created_at": self.created_at,
            "last_login_at": self.last_login_at or "",
            "social_accounts_json": json.dumps(self.social_accounts, ensure_ascii=False),
            "password_hash": self.password_hash,
            "reset_token": self.reset_token,
            "reset_token_exp": self.reset_token_exp,
        }

    @classmethod
    def from_row(cls, row: dict) -> "User":
        """Google Sheets 행에서 역직렬화."""
        social_raw = row.get("social_accounts_json", "[]")
        try:
            social = json.loads(social_raw) if social_raw else []
        except (json.JSONDecodeError, TypeError):
            social = []
        return cls(
            user_id=row.get("user_id", ""),
            email=row.get("email", ""),
            name=row.get("name", ""),
            avatar_url=row.get("avatar_url", ""),
            role=row.get("role", "seller"),
            email_verified=row.get("email_verified", "0") == "1",
            active=row.get("active", "1") == "1",
            created_at=row.get("created_at", ""),
            last_login_at=row.get("last_login_at") or None,
            social_accounts=social,
            password_hash=row.get("password_hash", ""),
            reset_token=row.get("reset_token", ""),
            reset_token_exp=row.get("reset_token_exp", ""),
        )

    @classmethod
    def new(cls, email: str, name: str, avatar_url: str = "", role: str = "seller") -> "User":
        """신규 사용자 생성."""
        return cls(
            user_id=str(uuid.uuid4()),
            email=email,
            name=name,
            avatar_url=avatar_url,
            role=role,
            email_verified=False,
            active=True,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_login_at=None,
        )
