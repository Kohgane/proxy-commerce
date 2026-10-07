"""Z8(오너 2026-10-07) — 대시보드 API(`src/api` · `require_api_key`)는 `DASHBOARD_API_KEY`가 비면 **닫힌다**.

예전엔 키가 비면 인증을 건너뛰어 비로그인 외부인도 `/api/dashboard/*`(오너 주문·매출)·CRM·리포트를 읽었다.
운영 Render엔 키가 있다(오너 확인) — 이건 env 누락 한 번이 곧 유출이 되지 않게 하는 방어다.
개발·테스트만 `DASHBOARD_API_OPEN=1`로 연다. `APP_ENV=production`이면 그 값도 무시한다.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

PATH = "/api/dashboard/health"


@pytest.fixture
def client():
    import src.order_webhook as wh
    try:
        from src.api import dashboard_bp
        wh.app.register_blueprint(dashboard_bp)
    except Exception:
        pass
    return wh.app.test_client()


def _get(c, headers=None):
    with patch("src.api.auth_middleware._audit") as a:
        a.log.return_value = {}
        return c.get(PATH, headers=headers or {})


def test_empty_key_without_dev_open_is_closed(client, monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("DASHBOARD_API_OPEN", raising=False)
    r = _get(client)
    assert r.status_code == 503 and "DASHBOARD_API_KEY" in r.get_json()["message"]
    monkeypatch.setenv("DASHBOARD_API_KEY", "   ")                    # 공백만 = 빈 키
    assert _get(client).status_code == 503


def test_production_ignores_dev_open(client, monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("DASHBOARD_API_OPEN", "1")
    monkeypatch.setenv("APP_ENV", "production")
    assert _get(client).status_code == 503
    monkeypatch.delenv("APP_ENV")
    assert "DASHBOARD_API_KEY" not in str(_get(client).get_json())         # 개발 레인에선 열림(닫힘 응답 아님)


def test_key_set_behaviour_unchanged(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "k-z8")
    monkeypatch.delenv("DASHBOARD_API_OPEN", raising=False)
    assert _get(client).status_code == 401
    assert _get(client, {"X-API-Key": "nope"}).status_code == 401
    r = _get(client, {"X-API-Key": "k-z8"})
    assert r.status_code != 401 and "DASHBOARD_API_KEY" not in ((r.get_json() or {}).get("message") or "")


def test_dev_open_helper():
    import os
    from src.api.auth_middleware import dev_open
    old = {k: os.environ.get(k) for k in ("APP_ENV", "DASHBOARD_API_OPEN")}
    try:
        os.environ.pop("APP_ENV", None)
        os.environ["DASHBOARD_API_OPEN"] = "0"
        assert dev_open() is False
        os.environ["DASHBOARD_API_OPEN"] = "1"
        assert dev_open() is True
        os.environ["APP_ENV"] = "production"
        assert dev_open() is False
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
