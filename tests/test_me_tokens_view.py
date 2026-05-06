"""tests/test_me_tokens_view.py — /seller/me/tokens 라우트 테스트 (Phase 135.1).

GET  /seller/me/tokens       — 200 반환 확인
POST /seller/me/tokens/generate — 토큰 발급 JSON 응답
POST /seller/me/tokens/revoke   — 토큰 회수 JSON 응답
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.seller_console.views import bp
    from flask import Flask
    app = Flask(__name__, template_folder="../src/seller_console/templates")
    app.register_blueprint(bp)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    return app.test_client()


class TestListTokensView:
    def test_get_returns_200(self, client):
        resp = client.get("/seller/me/tokens")
        assert resp.status_code == 200

    def test_get_contains_token_heading(self, client):
        resp = client.get("/seller/me/tokens")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "Token" in data or "토큰" in data

    def test_get_with_session_user(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = "test_user_123"
        resp = client.get("/seller/me/tokens")
        assert resp.status_code == 200

    def test_get_with_empty_tokens_list(self, client):
        with patch("src.auth.personal_tokens.list_tokens", return_value=[]):
            resp = client.get("/seller/me/tokens")
        assert resp.status_code == 200


class TestGenerateTokenView:
    def test_post_generate_returns_ok(self, client):
        mock_result = {
            "raw_token": "tok_" + "a" * 60,
            "token_hash": "hash123",
            "user_id": "user1",
            "scopes": ["collect.write"],
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2027-01-01T00:00:00+00:00",
        }
        with patch("src.auth.personal_tokens.generate_token", return_value=mock_result):
            resp = client.post(
                "/seller/me/tokens/generate",
                data=json.dumps({"scopes": ["collect.write"], "expires_days": 365}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "raw_token" in data

    def test_post_generate_without_body(self, client):
        mock_result = {
            "raw_token": "tok_" + "b" * 60,
            "token_hash": "hash456",
            "user_id": "dev",
            "scopes": ["collect.write"],
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2027-01-01T00:00:00+00:00",
        }
        with patch("src.auth.personal_tokens.generate_token", return_value=mock_result):
            resp = client.post("/seller/me/tokens/generate", content_type="application/json")
        assert resp.status_code == 200

    def test_post_generate_with_multiple_scopes(self, client):
        mock_result = {
            "raw_token": "tok_" + "c" * 60,
            "token_hash": "hash789",
            "user_id": "user2",
            "scopes": ["collect.write", "catalog.read"],
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2027-01-01T00:00:00+00:00",
        }
        with patch("src.auth.personal_tokens.generate_token", return_value=mock_result):
            resp = client.post(
                "/seller/me/tokens/generate",
                data=json.dumps({"scopes": ["collect.write", "catalog.read"]}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_post_generate_error_returns_500(self, client):
        with patch("src.auth.personal_tokens.generate_token", side_effect=Exception("DB error")):
            resp = client.post(
                "/seller/me/tokens/generate",
                data=json.dumps({"scopes": ["collect.write"]}),
                content_type="application/json",
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["ok"] is False


class TestRevokeTokenView:
    def test_post_revoke_ok(self, client):
        with patch("src.auth.personal_tokens.revoke_token", return_value=True):
            resp = client.post(
                "/seller/me/tokens/revoke",
                data=json.dumps({"token_hash": "abc123hash"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_post_revoke_missing_hash_returns_400(self, client):
        resp = client.post(
            "/seller/me/tokens/revoke",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_post_revoke_not_found_returns_ok_false(self, client):
        with patch("src.auth.personal_tokens.revoke_token", return_value=False):
            resp = client.post(
                "/seller/me/tokens/revoke",
                data=json.dumps({"token_hash": "nonexistenthash"}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False

    def test_post_revoke_error_returns_500(self, client):
        with patch("src.auth.personal_tokens.revoke_token", side_effect=Exception("DB error")):
            resp = client.post(
                "/seller/me/tokens/revoke",
                data=json.dumps({"token_hash": "somehash"}),
                content_type="application/json",
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["ok"] is False
