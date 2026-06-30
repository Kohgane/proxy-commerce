"""tests/test_v38_token_history_split.py — v38 #6: 활성 토큰만 메인 목록, 폐기 토큰은 이력으로 분리."""
from __future__ import annotations

import os

import pytest

_SAMPLE = [
    {"token_hash_prefix": "aaaa1111...", "token_hash": "aaaa1111", "scopes": ["collect.write"],
     "created_at": "2026-06-20T00:00:00", "last_used_at": "2026-06-27T00:00:00", "expires_at": "2027-06-20", "revoked": False},
    {"token_hash_prefix": "bbbb2222...", "token_hash": "bbbb2222", "scopes": ["collect.write"],
     "created_at": "2026-05-01T00:00:00", "last_used_at": "", "expires_at": "2027-05-01", "revoked": True},
    {"token_hash_prefix": "cccc3333...", "token_hash": "cccc3333", "scopes": ["catalog.read"],
     "created_at": "2026-04-01T00:00:00", "last_used_at": "", "expires_at": "2027-04-01", "revoked": True},
]


@pytest.fixture
def client(monkeypatch):
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    import src.auth.personal_tokens as pt
    monkeypatch.setattr(pt, "list_tokens", lambda user_id, **kw: [dict(t) for t in _SAMPLE])
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_active_in_main_revoked_in_history(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/me/tokens").get_data(as_text=True)
    # 폐기 토큰은 '발급·폐기 이력' 분리 섹션으로
    assert "발급·폐기 이력" in html
    assert "2건" in html                       # 폐기 2건
    # 활성 토큰(aaaa)은 메인, 삭제 버튼 노출
    assert "aaaa1111" in html
    assert "revoke-btn" in html
    # 폐기 토큰 prefix도 이력에 표시(이력 보관)
    assert "bbbb2222" in html and "cccc3333" in html


def test_history_hidden_when_no_revoked(client, monkeypatch):
    import src.auth.personal_tokens as pt
    monkeypatch.setattr(pt, "list_tokens", lambda user_id, **kw: [dict(_SAMPLE[0])])  # 활성 1개만
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/me/tokens").get_data(as_text=True)
    assert "발급·폐기 이력" not in html        # 폐기 없으면 이력 섹션 미노출
    assert "aaaa1111" in html
