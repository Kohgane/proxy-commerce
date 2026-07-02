"""tests/test_v42_e1_token_persist.py — v42 E-1: 토큰 영속 + 연결 상태.

증상: 토큰 넣었는데 페이지마다 '인증 필요' 토스트 반복. 수리: 토큰 storage 영속(리셋 없음),
재프롬프트는 401일 때만, 옵션에 '연결됨 ✓ (계정)' 상태 노출.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
OPT_JS = Path("extensions/chrome-collector/options.js").read_text(encoding="utf-8")
OPT_HTML = Path("extensions/chrome-collector/options.html").read_text(encoding="utf-8")


# ── 서버: /api/v1/collect/me (토큰 연결 상태) ──
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_me_valid_token_returns_account(client, monkeypatch):
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1"})

    class _U:
        email = "demo@goga.kr"
        name = "데모 셀러"
    monkeypatch.setattr("src.auth.user_store.get_store",
                        lambda: type("S", (), {"find_by_id": staticmethod(lambda uid: _U())})())
    r = client.get("/api/v1/collect/me", headers={"Authorization": "Bearer good"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["email"] == "demo@goga.kr"


def test_me_invalid_token_401(client, monkeypatch):
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: None)
    r = client.get("/api/v1/collect/me", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401
    assert r.get_json()["ok"] is False


def test_me_cors_allows_get():
    # CORS 설정이 /api/v1/collect/* 에 GET+Authorization 허용(확장 교차출처 호출).
    src = Path("src/order_webhook.py").read_text(encoding="utf-8")
    assert "r'/api/v1/collect/*'" in src
    assert "'GET'" in src and "Authorization" in src


# ── 확장 소스 계약 ──
def test_background_no_auto_notify_on_missing_token():
    """미인증 시 자동 알림(notifications) 남발 금지 — 반환만."""
    # 미인증 분기에서 authRequired 반환 + 그 분기에 notifications.create 없음.
    assert "authRequired: true" in BG
    idx = BG.index("토큰이 설정되지 않았습니다")
    seg = BG[idx - 200:idx + 200]
    assert "notifications.create" not in seg   # 미인증 분기에 자동 알림 없음


def test_background_flags_401_for_reprompt():
    assert "response.status === 401" in BG and "data.authRequired = true" in BG


def test_options_shows_connection_status():
    assert "checkConnection" in OPT_JS
    assert "/api/v1/collect/me" in OPT_JS
    assert "연결됨" in OPT_JS
    assert 'id="connStatus"' in OPT_HTML
    assert "재설정" in OPT_HTML       # 초기화 → 재설정 라벨


def test_token_not_reset_on_load():
    """옵션 로드가 매번 토큰을 지우지 않는다(리셋 로직 없음)."""
    # 로드 경로(readSettings 콜백)에 storage remove/빈 토큰 set 없음.
    load_idx = OPT_JS.index("readSettings((data)")
    seg = OPT_JS[load_idx:load_idx + 400]
    assert "remove(" not in seg
    assert "token: \"\"" not in seg
