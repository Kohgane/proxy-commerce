"""감독 11-23 TestFlight 로그인 화면 정리 — AASA webcredentials · 패스키 오류 한국어 · /auth/* 먹색 통일 · 미설정 소셜 숨김 ·
magic-link 부제 · 가입 G 로고 · 다리 마크 · 랜딩 어절 줄바꿈. 로그인·가입·OAuth 흐름은 불변.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

AUTH_TPL = Path("src/auth/templates/auth")
APP_ID = "J6TH5PRA9L.org.kohgane.gogabridj"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _unset_oauth(monkeypatch):
    for k in ("KAKAO_REST_API_KEY", "KAKAO_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
              "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
              "NAVER_OAUTH_CLIENT_ID", "NAVER_OAUTH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)


def test_aasa_webcredentials_with_app_id_and_applinks_unchanged(client, monkeypatch):
    monkeypatch.setenv("IOS_APP_ID", APP_ID)
    r = client.get("/.well-known/apple-app-site-association")
    assert r.status_code == 200 and r.content_type.startswith("application/json")
    body = json.loads(r.get_data(as_text=True))
    assert body["webcredentials"] == {"apps": [APP_ID]}
    assert body["applinks"] == {"apps": [], "details": [{"appID": APP_ID, "paths": ["/seller/*", "/auth/*"]}]}


def test_aasa_without_app_id_is_empty_not_fake(client, monkeypatch):
    monkeypatch.delenv("IOS_APP_ID", raising=False)
    body = json.loads(client.get("/.well-known/apple-app-site-association").get_data(as_text=True))
    assert body == {"applinks": {"apps": [], "details": []}, "webcredentials": {"apps": []}}


def test_aasa_needs_no_login_and_no_redirect(client, monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "1")
    monkeypatch.setenv("IOS_APP_ID", APP_ID)
    r = client.get("/.well-known/apple-app-site-association")
    assert r.status_code == 200 and "Location" not in r.headers


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
@pytest.mark.parametrize("name, expect", [
    ("NotAllowedError", "패스키 인증이 취소됐거나 이 기기에 등록된 패스키가 없어요. 다른 로그인을 쓰세요."),
    ("AbortError", "패스키 인증이 중간에 멈췄어요"),
    ("SecurityError", "이 주소에서는 패스키를 쓸 수 없어요"),
    ("WeirdBrowserError", "패스키로 마치지 못했어요"),
])
def test_passkey_browser_errors_become_korean(name, expect):
    js = Path("src/seller_console/static/passkey.js").read_text(encoding="utf-8")
    probe = js + f"""
    ;(async () => {{
      const e = new Error("The request is not allowed by the user agent or the platform in the current context");
      e.name = {json.dumps(name)};
      navigator.credentials.get = async () => {{ throw e; }};
      try {{ await window.kgpPasskey.login(); console.log("NO-THROW"); }}
      catch (x) {{ console.log(x.message); }}
      console.log(window.kgpPasskey.friendlyError(e));
    }})();"""
    shim = """var window = globalThis; window.PublicKeyCredential = function () {};
    Object.defineProperty(globalThis, "navigator", { value: { credentials: { create() {}, get() {} } }, configurable: true, writable: true });
    globalThis.fetch = async () => ({ status: 200, json: async () => ({ ok: true, options: { challenge: "AA", allowCredentials: [] } }) });
    globalThis.atob = (s) => Buffer.from(s, "base64").toString("binary");
    globalThis.btoa = (s) => Buffer.from(s, "binary").toString("base64");
    """
    out = subprocess.run(["node", "-e", shim + probe], capture_output=True, text=True, timeout=30)
    lines = out.stdout.strip().splitlines()
    assert len(lines) == 2, out.stderr
    for line in lines:
        assert expect in line and "not allowed" not in line


def test_passkey_server_reason_kept():
    js = Path("src/seller_console/static/passkey.js").read_text(encoding="utf-8")
    assert 'if (name === "Error" && e.message && /[가-힣]/.test(e.message)) return e.message;' in js
    tpl = (AUTH_TPL / "login.html").read_text(encoding="utf-8")
    assert "friendlyError(e)" in tpl and "(e && e.message)" not in tpl


def test_unconfigured_social_hidden_for_visitors_shown_in_diag(client, monkeypatch):
    _unset_oauth(monkeypatch)
    for path in ("/auth/login", "/auth/signup"):
        plain = client.get(path).get_data(as_text=True)
        assert "(설정 필요)" not in plain and "설정 경로" not in plain, path
        diag = client.get(path + "?diag=1").get_data(as_text=True)
        assert "(설정 필요)" in diag and 'data-role="oauth-unconfigured"' in diag, path


def test_configured_social_buttons_unchanged(client, monkeypatch):
    _unset_oauth(monkeypatch)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "g-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "g-secret")
    login = client.get("/auth/login?next=/seller/orders").get_data(as_text=True)
    assert 'href="/auth/google/start?next=/seller/orders"' in login and "Google로 로그인" in login
    assert "social-login-link" in login and 'fill="#4285F4"' in login
    signup = client.get("/auth/signup").get_data(as_text=True)
    assert 'href="/auth/google/start"' in signup and "Google로 가입" in signup and 'fill="#4285F4"' in signup


def test_all_auth_templates_share_the_dark_vault():
    pages = [p for p in AUTH_TPL.glob("*.html") if not p.name.startswith("_")]
    assert len(pages) == 6
    for p in pages:
        src = p.read_text(encoding="utf-8")
        assert '{% include "auth/_auth_head.html" %}' in src, p.name
        assert 'class="auth-page"' in src and "auth-panel" in src, p.name
        assert "<style>" not in src, p.name                                     # 스타일은 app.css 한 곳
        assert "🛒" not in src and "📧" not in src and "🔑" not in src, p.name
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    for sel in (".auth-page {", ".auth-panel {", ".auth-panel .text-muted", ".auth-panel .divider {"):
        assert sel in css
    assert re.search(r"--auth-muted:\s*#b7a98c", css)


def test_bridge_mark_and_copy(client):
    for path in ("/auth/login", "/auth/signup"):
        html = client.get(path).get_data(as_text=True)
        assert '<img src="/seller/static/favicon.svg' in html and "🛒" not in html, path
    magic = client.get("/auth/magic-link").get_data(as_text=True)
    assert "비밀번호 없이 메일로 받은 링크로 로그인합니다." in magic and "OAuth 로그인이 안 될 때" not in magic


def test_auth_muted_contrast_meets_aa():
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    a, b = lum("#b7a98c"), lum("#241f1a")
    assert (max(a, b) + 0.05) / (min(a, b) + 0.05) >= 4.5


def test_landing_hero_breaks_by_word():
    src = Path("src/templates/landing.html").read_text(encoding="utf-8")
    assert ".hero h1, .hero .sub { word-break: keep-all;" in src


def test_auth_css_is_scoped_and_does_not_leak():
    """landing.html에도 `class="divider"`가 있다 — auth 블록의 공용 이름(divider·social-btn)은 .auth-panel 안에만."""
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    block = css[css.index("/* ── 감독 11-23: /auth/*"):]
    for line in block.splitlines():
        if line.lstrip().startswith((".divider", ".social-btn")):
            pytest.fail("범위 없는 auth 규칙: " + line)
