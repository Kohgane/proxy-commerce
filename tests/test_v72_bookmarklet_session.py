"""tests/test_v72_bookmarklet_session.py — v72 STEP1: 북마클릿 인증 뿌리 수술(세션 폴백).

증상: 북마클릿 401 3차 재발(토큰 수명 설계 결함). 수리: Bearer 무효(401)여도 유효한 콘솔 로그인 세션
쿠키면 통과(북마클릿 fetch credentials:'include'). CSRF는 커스텀 헤더 X-KGP=1 요구로 단순 폼 위조 차단.
401+세션도 없으면 로그인 안내 토스트+[열기] 링크. 토큰 재발급 시 기존 폐기 안 함(회귀 금지).
"""
from __future__ import annotations

import re
from pathlib import Path

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
EXTAPI = Path("src/api/extension_api.py").read_text(encoding="utf-8")
WEBHOOK = Path("src/order_webhook.py").read_text(encoding="utf-8")
TOKENS = Path("src/auth/personal_tokens.py").read_text(encoding="utf-8")


# ── source-contract ──
def test_session_fallback_source_contract():
    assert "def _session_user()" in EXTAPI
    assert "def _auth_user(scopes" in EXTAPI
    assert 'request.headers.get("X-KGP") != "1"' in EXTAPI    # CSRF 커스텀 헤더 요구
    assert '"login_required": True' in EXTAPI
    # collect 엔드포인트가 세션 폴백 사용.
    assert 'user = _auth_user(scopes=["collect.write"])' in EXTAPI


def test_cors_and_cookie_contract():
    # 자격 동반 CORS + X-KGP 허용 헤더.
    assert "'supports_credentials': True" in WEBHOOK
    assert "'X-KGP'" in WEBHOOK
    # 프로덕션 SameSite=None; Secure.
    assert 'app.config["SESSION_COOKIE_SAMESITE"] = "None"' in WEBHOOK
    assert 'app.config["SESSION_COOKIE_SECURE"] = True' in WEBHOOK


def test_bookmarklet_fetch_contract():
    v = _import_views()
    js = v._bookmarklet_js("https://x.com", "T", True)
    assert "credentials:'include'" in js          # 세션 쿠키 동반
    assert "'X-KGP':'1'" in js                     # CSRF 헤더
    assert "'Bearer '+T" in js                     # 토큰 우선(기존 유지)
    assert "d.login_required" in js and "[열기]" in js   # 로그인 안내 링크


def test_token_reissue_does_not_revoke():
    # 재발급이 기존 토큰을 폐기하지 않음(회귀 금지) — generate_token 본문에 revoke 호출 없음.
    m = re.search(r"def generate_token\(.*?\n(?=def )", TOKENS, re.S)
    assert m, "generate_token 추출 실패"
    body = m.group(0)
    # 기존 토큰을 폐기하는 호출/변형이 없어야 함('revoked': False 필드 초기화는 신규 토큰 상태라 무관).
    assert "revoke_token(" not in body
    assert 'revoked": True' not in body and "revoked = True" not in body
    assert "revoke_all" not in body
    # 만료 기본값 ≥ 90일(브리프: 90일 이상 — 현재 365).
    dm = re.search(r"_DEFAULT_EXPIRY_DAYS\s*=\s*(\d+)", TOKENS)
    assert dm and int(dm.group(1)) >= 90


def _import_views():
    from src.seller_console import views as v
    return v


# ── behavioral ──
def test_session_fallback_collects(flask_client):
    with flask_client.session_transaction() as s:
        s["user_id"] = "u_session"
        s["user_email"] = "seller@example.com"
    r = flask_client.post(
        "/api/v1/collect/extension",
        json={"url": "https://www.temu.com/goods-1.html", "title": "세션 폴백 테스트",
              "price": "11235", "currency": "KRW"},
        headers={"X-KGP": "1"},
    )
    assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
    assert (r.get_json() or {}).get("ok") is True


def test_session_ignored_without_header(flask_client):
    # 세션은 있지만 X-KGP 헤더 없음 → 세션 폴백 미적용(단순 폼 위조 차단) → 401.
    with flask_client.session_transaction() as s:
        s["user_id"] = "u_session"
    r = flask_client.post("/api/v1/collect/extension",
                          json={"url": "https://x.com/g"}, headers={})
    assert r.status_code == 401, r.get_data(as_text=True)
    assert (r.get_json() or {}).get("login_required") is True


def test_no_auth_returns_login_required(flask_client):
    # 토큰 무효 + 세션 없음 → 401 login_required(로그인 안내).
    r = flask_client.post("/api/v1/collect/extension",
                          json={"url": "https://x.com/g"}, headers={"X-KGP": "1"})
    assert r.status_code == 401
    d = r.get_json() or {}
    assert d.get("login_required") is True and d.get("login_url")
