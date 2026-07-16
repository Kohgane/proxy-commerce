"""tests/test_v72b_token_lifecycle.py — v72b STEP2: 북마클릿 토큰 수명 구조.

감사: 발급(파일/코드)이 기존 토큰을 폐기하지 않는지, TTL, 401 유발 조건. 구조: 사용자당 장수명 안정 토큰,
동시 유효 N개(브라우저별) 허용, 파일 재다운로드가 기존 설치본을 죽이지 않게. 401 토스트에 재발급 링크(30초 복구).
"""
from __future__ import annotations

import re
from pathlib import Path

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
EXTAPI = Path("src/api/extension_api.py").read_text(encoding="utf-8")
TOKENS = Path("src/auth/personal_tokens.py").read_text(encoding="utf-8")


# ── 감사: 발급 시 폐기 없음 + TTL ──
def test_generate_token_no_revoke_and_ttl():
    m = re.search(r"def generate_token\(.*?\n(?=def )", TOKENS, re.S)
    assert m, "generate_token 추출 실패"
    body = m.group(0)
    # 발급이 기존 토큰을 폐기하는 호출/변형 없음(동시 유효 N개 허용).
    assert "revoke_token(" not in body and "revoke_all" not in body
    assert 'revoked": True' not in body and "revoked = True" not in body
    # TTL 장수명(≥90일).
    dm = re.search(r"_DEFAULT_EXPIRY_DAYS\s*=\s*(\d+)", TOKENS)
    assert dm and int(dm.group(1)) >= 90
    # 북마클릿 파일도 365일로 발급.
    assert "expires_days=365" in VIEWS


# ── 구조: 2회 연속 발급 후 1회차 생존(폐기 미발생) ──
def test_two_tokens_both_valid_no_revoke():
    from src.auth import personal_tokens as pt
    uid = "u_v72b_lifecycle"
    r1 = pt.generate_token(uid, scopes=["collect.write"])
    r2 = pt.generate_token(uid, scopes=["collect.write"])
    t1, t2 = r1["raw_token"], r2["raw_token"]
    assert t1 and t2 and t1 != t2
    # 2번째 발급(파일 재다운로드)이 1회차 설치본을 죽이지 않음 — 동시 유효.
    v1 = pt.validate_token(t1, required_scopes=["collect.write"])
    v2 = pt.validate_token(t2, required_scopes=["collect.write"])
    assert v1 is not None and str(v1.get("user_id")) == uid
    assert v2 is not None and str(v2.get("user_id")) == uid


# ── 401 토스트: 토큰 재발급 링크 ──
def test_401_reissue_link():
    # collect 401(login_required) 응답에 재발급 페이지 URL.
    assert '"reissue_url": "/seller/bookmarklet"' in EXTAPI
    # 북마클릿 토스트가 재발급 링크를 붙임(30초 복구).
    assert "d.reissue_url" in VIEWS
    assert "[토큰 재발급 열기]" in VIEWS
