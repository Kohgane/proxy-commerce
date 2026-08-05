# v87-S7: 이 모듈들이 relay_request(단일 관문)를 타면서 직결도 requests.request로 나간다.
#   그래서 목 대상도 requests.post/get → requests.request 로 옮긴다(동작 동일, 경로만 통일).
from __future__ import annotations

import base64


def test_build_client_secret_sign_returns_base64(monkeypatch):
    import bcrypt
    from src.markets.adapters.naver_commerce_auth import _build_client_secret_sign

    sign = _build_client_secret_sign("client-id", bcrypt.gensalt().decode("utf-8"), "1715000000000")
    decoded = base64.b64decode(sign.encode("utf-8"))
    assert decoded


def test_get_access_token_uses_cache(monkeypatch):
    import bcrypt
    import src.markets.adapters.naver_commerce_auth as mod

    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", bcrypt.gensalt().decode("utf-8"))
    mod._TOKEN_CACHE.clear()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "token-1", "expires_in": 300}

    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return FakeResponse()

    monkeypatch.setattr("requests.request", fake_post)
    token1 = mod.get_access_token()
    token2 = mod.get_access_token(now=0)
    assert token1 == "token-1"
    assert token2 == "token-1"
    assert calls["count"] == 1
