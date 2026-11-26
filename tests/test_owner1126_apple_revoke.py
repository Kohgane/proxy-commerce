"""오너 11-26 오후 ④ — 애플 로그인 계정 삭제 때 애플 토큰 폐기. 계약.

콜백이 받은 refresh token은 **암호화해서만** 둔다(키 없으면 저장 안 함) · 계정 삭제 실행이 `/auth/revoke`를 부르고 결과를 단계 줄에 그대로 ·
애플 로그인이 아니면 「토큰 없음」(실패 아님).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def state(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    return s


@pytest.fixture
def key(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("MARKET_CRED_ENC_KEY", Fernet.generate_key().decode())


class FakeApple:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def revoke(self, token, hint="refresh_token"):
        self.calls.append((token, hint))
        return {"ok": True} if self.ok else {"ok": False, "error": "HTTP 400 {\"error\":\"invalid_client\"}"}


def test_token_is_stored_encrypted_only(state, key):
    from src.auth import apple_tokens as AT
    assert AT.save("u-ap", "r.secret-refresh")
    raw = str(state["apple_tokens"])
    assert "r.secret-refresh" not in raw and AT.has("u-ap")


def test_no_key_means_not_stored(state, monkeypatch):
    from src.auth import apple_tokens as AT
    import src.seller_console.market_credentials as MC
    monkeypatch.setattr(MC, "_fernet", lambda: None)
    assert AT.save("u-ap2", "r.x") is False and not state.get("apple_tokens")


def test_revoke_calls_apple_and_forgets(state, key):
    from src.auth import apple_tokens as AT
    AT.save("u-ap", "r.secret-refresh")
    fa = FakeApple()
    out = AT.revoke("u-ap", provider=fa)
    assert out["ok"] and "폐기" in out["step"] and fa.calls == [("r.secret-refresh", "refresh_token")]
    assert not AT.has("u-ap")


def test_revoke_failure_is_reported_raw(state, key):
    from src.auth import apple_tokens as AT
    AT.save("u-ap", "r.t")
    out = AT.revoke("u-ap", provider=FakeApple(ok=False))
    assert out["ok"] is False and "invalid_client" in out["step"] and AT.has("u-ap")   # 실패면 지우지 않는다(다시 시도)


def test_non_apple_user_is_not_a_failure(state, key):
    from src.auth import apple_tokens as AT
    out = AT.revoke("u-email-only")
    assert out["ok"] and "토큰 없음" in out["step"]


def test_account_delete_execute_includes_apple_step(state, key, monkeypatch):
    from src.auth import apple_tokens as AT
    from src.services import account_delete as AD
    AT.save("u-del-ap", "r.t")
    import src.auth.providers.apple as AP
    fa = FakeApple()
    monkeypatch.setattr(AP, "AppleProvider", lambda: fa)
    rec = AD.request("u-del-ap", "")
    out = AD.execute(rec["id"], by="owner")
    assert "apple" in out["steps"] and "폐기" in out["steps"]["apple"] and fa.calls


def test_callback_saves_refresh_token(state, key):
    """콜백 코드에 저장 호출이 있다(AST — 소스 글자 읽기 금지 래칫)."""
    from tests._ast_probe import importers_of
    assert "src/auth/views.py" in importers_of("apple_tokens")
