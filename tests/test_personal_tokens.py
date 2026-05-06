"""tests/test_personal_tokens.py — Personal Access Token 테스트 (Phase 135).

발급/검증/만료/회수 테스트.
GOOGLE_SHEET_ID="" 로 Sheets 없이 실행.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.auth.personal_tokens import (
    _hash_token,
    _check_scopes,
    generate_token,
    validate_token,
    revoke_token,
    list_tokens,
    _TOKEN_PREFIX,
)


class TestTokenUtils:
    def test_hash_token_consistent(self):
        raw = "tok_abc123"
        assert _hash_token(raw) == _hash_token(raw)

    def test_hash_token_different_inputs(self):
        assert _hash_token("tok_aaa") != _hash_token("tok_bbb")

    def test_check_scopes_all_present(self):
        assert _check_scopes(["collect.write", "catalog.read"], ["collect.write"]) is True

    def test_check_scopes_missing(self):
        assert _check_scopes(["collect.write"], ["markets.write"]) is False

    def test_check_scopes_empty_required(self):
        assert _check_scopes([], []) is True


class TestGenerateToken:
    def test_generate_returns_raw_token(self):
        result = generate_token("user123", scopes=["collect.write"])
        assert result["raw_token"].startswith(_TOKEN_PREFIX)
        assert len(result["raw_token"]) == 64  # "tok_" + 60 chars

    def test_generate_invalid_scope_filtered(self):
        result = generate_token("user123", scopes=["invalid.scope", "collect.write"])
        assert "invalid.scope" not in result["scopes"]
        assert "collect.write" in result["scopes"]

    def test_generate_empty_scope_defaults(self):
        result = generate_token("user123", scopes=[])
        assert "collect.write" in result["scopes"]

    def test_generate_token_hash_present(self):
        result = generate_token("user123")
        assert "token_hash" in result
        assert len(result["token_hash"]) == 64  # SHA-256 hex

    def test_generate_raw_token_matches_hash(self):
        result = generate_token("user123")
        assert _hash_token(result["raw_token"]) == result["token_hash"]

    def test_generate_no_sheet(self):
        """GOOGLE_SHEET_ID 없어도 token 생성 성공."""
        result = generate_token("user123")
        assert result["raw_token"].startswith(_TOKEN_PREFIX)


class TestValidateToken:
    def test_validate_no_sheet_returns_none(self):
        """Sheets 없으면 None 반환."""
        result = validate_token("tok_validprefix" + "a" * 56)
        assert result is None

    def test_validate_wrong_prefix_returns_none(self):
        result = validate_token("invalid_token_without_prefix")
        assert result is None

    def test_validate_empty_returns_none(self):
        result = validate_token("")
        assert result is None


class TestRevokeToken:
    def test_revoke_no_sheet(self):
        """Sheets 없으면 False."""
        result = revoke_token("abc123", "user123")
        assert result is False


class TestListTokens:
    def test_list_tokens_no_sheet(self):
        """Sheets 없으면 빈 리스트."""
        result = list_tokens("user123")
        assert result == []
