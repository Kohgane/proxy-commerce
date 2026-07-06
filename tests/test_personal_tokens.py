"""tests/test_personal_tokens.py — Personal Access Token 테스트 (PG-only 전환 후).

발급/검증/만료/회수 — 인메모리(개발/테스트) 경로. Sheets 경로는 제거됐다.
(PG durable·삭제영속은 test_v45_supabase_stage1·test_v45_token_bulk_delete에서 로컬 PG로 검증.)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.auth.personal_tokens as pt


@pytest.fixture(autouse=True)
def _reset_token_state():
    pt._token_cache.clear()
    pt._in_memory[:] = []
    yield
    pt._token_cache.clear()
    pt._in_memory[:] = []


class TestTokenUtils:
    def test_hash_token_consistent(self):
        assert pt._hash_token("tok_abc123") == pt._hash_token("tok_abc123")

    def test_hash_token_different_inputs(self):
        assert pt._hash_token("tok_aaa") != pt._hash_token("tok_bbb")

    def test_check_scopes_all_present(self):
        assert pt._check_scopes(["collect.write", "catalog.read"], ["collect.write"]) is True

    def test_check_scopes_missing(self):
        assert pt._check_scopes(["collect.write"], ["markets.write"]) is False

    def test_check_scopes_empty_required(self):
        assert pt._check_scopes([], []) is True


class TestGenerateToken:
    def test_generate_returns_raw_token(self):
        result = pt.generate_token("user123", scopes=["collect.write"])
        assert result["raw_token"].startswith(pt._TOKEN_PREFIX)
        assert len(result["raw_token"]) == 64  # prefix + 60 chars

    def test_generate_invalid_scope_filtered(self):
        result = pt.generate_token("user123", scopes=["invalid.scope", "collect.write"])
        assert "invalid.scope" not in result["scopes"]
        assert "collect.write" in result["scopes"]

    def test_generate_empty_scope_defaults(self):
        assert "collect.write" in pt.generate_token("user123", scopes=[])["scopes"]

    def test_generate_token_hash_present(self):
        result = pt.generate_token("user123")
        assert "token_hash" in result and len(result["token_hash"]) == 64

    def test_generate_raw_token_matches_hash(self):
        result = pt.generate_token("user123")
        assert pt._hash_token(result["raw_token"]) == result["token_hash"]

    def test_generate_durable_flag(self):
        assert pt.generate_token("user123")["durable"] is True

    def test_generate_round_trip_validates_immediately(self):
        result = pt.generate_token("user123", scopes=["collect.write", "catalog.read"])
        user_info = pt.validate_token(result["raw_token"], required_scopes=["collect.write"])
        assert user_info is not None
        assert user_info["user_id"] == "user123"
        assert "catalog.read" in user_info["scopes"]


class TestValidateToken:
    def test_validate_round_trip_updates_last_used(self):
        result = pt.generate_token("user123")
        assert pt.validate_token(result["raw_token"]) is not None
        listed = pt.list_tokens("user123")
        assert listed and listed[0]["last_used_at"]        # 사용 시각 갱신

    def test_validate_unknown_token_returns_none(self):
        assert pt.validate_token("kgp_" + "a" * 60) is None

    def test_validate_wrong_prefix_returns_none(self):
        assert pt.validate_token("invalid_token_without_prefix") is None

    def test_validate_empty_returns_none(self):
        assert pt.validate_token("") is None


class TestRevokeToken:
    def test_revoke_unknown_returns_false(self):
        assert pt.revoke_token("abc123", "user123") is False

    def test_revoke_marks_revoked_and_blocks_validate(self):
        result = pt.generate_token("user123")
        assert pt.revoke_token(result["token_hash"], "user123") is True
        listed = [t for t in pt.list_tokens("user123") if t["token_hash"] == result["token_hash"]]
        assert listed and listed[0]["revoked"] is True
        assert pt.validate_token(result["raw_token"]) is None   # 회수 후 인증 불가

    def test_revoke_other_user_blocked(self):
        result = pt.generate_token("u1")
        assert pt.revoke_token(result["token_hash"], "u2") is False   # 타 유저 회수 차단


class TestListTokens:
    def test_list_tokens_empty(self):
        assert pt.list_tokens("user123") == []

    def test_list_tokens_reads_saved_row(self):
        result = pt.generate_token("user123", scopes=["collect.write", "markets.write"])
        tokens = pt.list_tokens("user123")
        assert len(tokens) == 1
        assert tokens[0]["token_hash"] == result["token_hash"]
        assert tokens[0]["scopes"] == ["collect.write", "markets.write"]
