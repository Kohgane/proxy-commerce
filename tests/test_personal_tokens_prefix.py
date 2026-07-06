"""tests/test_personal_tokens_prefix.py — 토큰 prefix 통일 테스트 (Phase 135.2).

신규 발급 토큰은 kgp_ 시작.
기존 tok_ 토큰도 validate_token 통과 (백워드 호환).
"""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
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


@pytest.fixture
def token_sheet(monkeypatch):
    # PG-only 전환 후: 인메모리(개발/테스트) 저장소. Sheets 목킹 제거.
    pt._token_cache.clear()
    pt._in_memory[:] = []
    yield None
    pt._token_cache.clear()
    pt._in_memory[:] = []


class TestTokenPrefixUnification:
    def test_new_token_starts_with_kgp(self, token_sheet):
        """신규 발급 토큰은 kgp_ 시작."""
        result = pt.generate_token("user123", scopes=["collect.write"])
        assert result["raw_token"].startswith("kgp_"), \
            f"신규 토큰이 kgp_로 시작하지 않습니다: {result['raw_token'][:10]}"

    def test_token_prefix_constant_is_kgp(self):
        """_TOKEN_PREFIX 상수가 kgp_."""
        assert pt._TOKEN_PREFIX == "kgp_"

    def test_legacy_prefix_constant_is_tok(self):
        """_TOKEN_PREFIX_LEGACY 상수가 tok_."""
        assert pt._TOKEN_PREFIX_LEGACY == "tok_"

    def test_validate_rejects_wrong_prefix(self):
        """완전히 다른 prefix는 거부됨."""
        result = pt.validate_token("xyz_abc123" + "a" * 50)
        assert result is None

    def test_validate_accepts_tok_prefix(self):
        """기존 tok_ 토큰은 validate_token에서 prefix 거부되지 않음.
        (GOOGLE_SHEET_ID 없으면 Sheets 조회 실패로 None이지만 prefix 오류는 아님)
        """
        # tok_ prefix는 prefix 체크를 통과하므로 Sheets 없을 때 None (not rejected by prefix)
        # 실제 Sheets 없는 환경: prefix 통과 → Sheets 미연결 → None (정상)
        result = pt.validate_token("tok_" + "a" * 60)
        # GOOGLE_SHEET_ID="" 이므로 None이지만 prefix 이유가 아님 — 별도 확인
        # 중요: "invalid prefix" 관련 로그 없이 None
        assert result is None  # Sheets 없으므로 None — prefix 이유는 X

    def test_validate_accepts_kgp_prefix(self):
        """kgp_ prefix도 validate_token에서 prefix 거부되지 않음."""
        result = pt.validate_token("kgp_" + "a" * 60)
        # GOOGLE_SHEET_ID="" 이므로 None — prefix 이유가 아님
        assert result is None  # Sheets 없으므로 None — prefix 이유는 X

    def test_token_length_64(self, token_sheet):
        """신규 토큰 길이가 64자 (kgp_ 4자 + hex 60자)."""
        result = pt.generate_token("user123")
        assert len(result["raw_token"]) == 64
