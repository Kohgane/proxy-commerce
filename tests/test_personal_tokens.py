"""tests/test_personal_tokens.py — Personal Access Token 테스트 (Phase 135).

발급/검증/만료/회수 테스트.
"""
from __future__ import annotations

import os
import sys

from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.auth.personal_tokens as pt


class _FakeWS:
    header = ["token_hash", "user_id", "scopes_json", "created_at", "last_used_at", "expires_at", "revoked"]

    def __init__(self):
        self.rows = []

    def row_values(self, index):
        if index == 1 and self.rows:
            return list(self.header)
        return []

    def insert_row(self, row, index=1):
        if row and row[0] == "token_hash":
            return
        self.rows.insert(max(index - 2, 0), list(row))

    def append_row(self, row):
        self.rows.append(list(row))

    def get_all_records(self):
        return [dict(zip(self.header, row)) for row in self.rows]

    def update_cell(self, row_idx, col, val):
        self.rows[row_idx - 2][col - 1] = val


@pytest.fixture(autouse=True)
def _reset_token_state():
    pt._token_cache.clear()
    yield
    pt._token_cache.clear()


@pytest.fixture
def token_sheet(monkeypatch):
    ws = _FakeWS()
    monkeypatch.setattr(pt, "_SHEET_ID", "sheet-test", raising=False)
    monkeypatch.setattr(pt, "_get_worksheet", lambda: ws)
    return ws


class TestTokenUtils:
    def test_hash_token_consistent(self):
        raw = "tok_abc123"
        assert pt._hash_token(raw) == pt._hash_token(raw)

    def test_hash_token_different_inputs(self):
        assert pt._hash_token("tok_aaa") != pt._hash_token("tok_bbb")

    def test_check_scopes_all_present(self):
        assert pt._check_scopes(["collect.write", "catalog.read"], ["collect.write"]) is True

    def test_check_scopes_missing(self):
        assert pt._check_scopes(["collect.write"], ["markets.write"]) is False

    def test_check_scopes_empty_required(self):
        assert pt._check_scopes([], []) is True


class TestGenerateToken:
    def test_generate_returns_raw_token(self, token_sheet):
        result = pt.generate_token("user123", scopes=["collect.write"])
        assert result["raw_token"].startswith(pt._TOKEN_PREFIX)
        assert len(result["raw_token"]) == 64  # "tok_" + 60 chars

    def test_generate_invalid_scope_filtered(self, token_sheet):
        result = pt.generate_token("user123", scopes=["invalid.scope", "collect.write"])
        assert "invalid.scope" not in result["scopes"]
        assert "collect.write" in result["scopes"]

    def test_generate_empty_scope_defaults(self, token_sheet):
        result = pt.generate_token("user123", scopes=[])
        assert "collect.write" in result["scopes"]

    def test_generate_token_hash_present(self, token_sheet):
        result = pt.generate_token("user123")
        assert "token_hash" in result
        assert len(result["token_hash"]) == 64  # SHA-256 hex

    def test_generate_raw_token_matches_hash(self, token_sheet):
        result = pt.generate_token("user123")
        assert pt._hash_token(result["raw_token"]) == result["token_hash"]

    def test_generate_no_sheet_is_honest_failure(self, monkeypatch):
        monkeypatch.setattr(pt, "_SHEET_ID", "", raising=False)
        with pytest.raises(pt.TokenStoreCommitError):
            pt.generate_token("user123")

    def test_generate_round_trip_validates_immediately(self, token_sheet):
        result = pt.generate_token("user123", scopes=["collect.write", "catalog.read"])
        user_info = pt.validate_token(result["raw_token"], required_scopes=["collect.write"])
        assert user_info is not None
        assert user_info["user_id"] == "user123"
        assert "catalog.read" in user_info["scopes"]

    def test_generate_append_failure_is_honest(self, token_sheet, monkeypatch):
        def _boom(row):
            raise RuntimeError("append failed")
        monkeypatch.setattr(token_sheet, "append_row", _boom)
        with pytest.raises(pt.TokenStoreCommitError):
            pt.generate_token("user123")

    def test_generate_missing_recheck_is_honest(self, token_sheet, monkeypatch):
        original_append = token_sheet.append_row

        def _append_without_persist(row):
            original_append(row)
            token_sheet.rows.clear()
        monkeypatch.setattr(token_sheet, "append_row", _append_without_persist)
        with pytest.raises(pt.TokenStoreCommitError):
            pt.generate_token("user123")


class TestValidateToken:
    def test_validate_round_trip_updates_last_used(self, token_sheet):
        result = pt.generate_token("user123")
        before = datetime.now(timezone.utc)
        validated = pt.validate_token(result["raw_token"])
        assert validated is not None
        row = pt._find_token_row(result["token_hash"], ws=token_sheet)
        assert row is not None
        assert row["last_used_at"]
        assert datetime.fromisoformat(row["last_used_at"]) >= before

    def test_validate_no_sheet_returns_none(self):
        """Sheets 없으면 None 반환."""
        result = pt.validate_token("tok_validprefix" + "a" * 56)
        assert result is None

    def test_validate_wrong_prefix_returns_none(self):
        result = pt.validate_token("invalid_token_without_prefix")
        assert result is None

    def test_validate_empty_returns_none(self):
        result = pt.validate_token("")
        assert result is None


class TestRevokeToken:
    def test_revoke_no_sheet(self):
        """Sheets 없으면 False."""
        result = pt.revoke_token("abc123", "user123")
        assert result is False

    def test_revoke_verifies_sheet_commit(self, token_sheet):
        result = pt.generate_token("user123")
        assert pt.revoke_token(result["token_hash"], "user123") is True
        row = pt._find_token_row(result["token_hash"], ws=token_sheet)
        assert row is not None
        assert str(row["revoked"]).lower() == "true"

    def test_revoke_fails_when_sheet_does_not_persist(self, token_sheet, monkeypatch):
        result = pt.generate_token("user123")

        def _no_persist(row_idx, col, val):
            return None
        monkeypatch.setattr(token_sheet, "update_cell", _no_persist)
        assert pt.revoke_token(result["token_hash"], "user123") is False


class TestListTokens:
    def test_list_tokens_no_sheet(self):
        """Sheets 없으면 빈 리스트."""
        result = pt.list_tokens("user123")
        assert result == []

    def test_list_tokens_reads_saved_row(self, token_sheet):
        result = pt.generate_token("user123", scopes=["collect.write", "markets.write"])
        tokens = pt.list_tokens("user123")
        assert len(tokens) == 1
        assert tokens[0]["token_hash"] == result["token_hash"]
        assert tokens[0]["scopes"] == ["collect.write", "markets.write"]
