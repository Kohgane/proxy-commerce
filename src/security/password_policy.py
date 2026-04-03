"""src/security/password_policy.py — 비밀번호 정책."""
from __future__ import annotations

import hashlib
import re


class PasswordPolicy:
    """비밀번호 정책 검사기."""

    def __init__(
        self,
        min_length: int = 8,
        require_uppercase: bool = True,
        require_numbers: bool = True,
        require_special: bool = True,
    ) -> None:
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_numbers = require_numbers
        self.require_special = require_special
        self._history: dict[str, list[str]] = {}

    def validate(self, password: str) -> dict:
        """비밀번호를 검사하고 결과를 반환한다."""
        errors: list[str] = []

        if len(password) < self.min_length:
            errors.append(f"최소 {self.min_length}자 이상이어야 합니다.")
        if self.require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("대문자가 포함되어야 합니다.")
        if self.require_numbers and not re.search(r'\d', password):
            errors.append("숫자가 포함되어야 합니다.")
        if self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("특수문자가 포함되어야 합니다.")

        return {"valid": len(errors) == 0, "errors": errors}

    def check_history(self, user_id: str, password_hash: str) -> bool:
        """비밀번호가 이전에 사용된 적 있는지 확인한다. True이면 이전에 사용됨."""
        history = self._history.get(user_id, [])
        used = password_hash in history
        if not used:
            history.append(password_hash)
            self._history[user_id] = history[-10:]
        return used
