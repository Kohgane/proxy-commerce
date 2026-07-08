"""tests/test_v47_bookmarklet_code.py — v47 STEP3: 북마클릿 코드 복사 → 북마크 편집창 URL칸.

진단: 크롬 '북마크 가져오기'(파일)는 최신 크롬서 javascript: HREF 드롭·묻힘 사례 + 주소창 붙여넣기는
javascript: 접두어 제거(anti-XSS). 유일 안전 경로 = 북마크 편집 대화상자 URL 칸에 붙여넣기.
→ /seller/bookmarklet/code 가 토큰 발급 후 javascript: 코드를 텍스트로 반환(복사용). 파일은 대체.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
TPL = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _mem():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    yield


def test_code_route_returns_javascript_code():
    from src.order_webhook import app
    with patch("src.auth.personal_tokens.generate_token", return_value={"raw_token": "TOK123"}):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
            r = c.post("/seller/bookmarklet/code", data={"translate": "1"})
            d = r.get_json()
            assert r.status_code == 200 and d["ok"] is True
            assert d["code"].startswith("javascript:")
            assert "TOK123" in d["code"]                 # 내 토큰 baked
            assert "/api/v1/collect/extension" in d["code"]


def test_code_route_honest_failure_on_token_error():
    # 토큰 저장 실패 → 코드도 안 준다(가짜 성공 0, 503)
    from src.order_webhook import app
    with patch("src.auth.personal_tokens.generate_token", side_effect=RuntimeError("db down")):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
            r = c.post("/seller/bookmarklet/code", data={"translate": "1"})
            assert r.status_code == 503
            assert r.get_json()["ok"] is False


def test_code_route_requires_auth():
    # _AUTH_ENABLED는 import 시점 캐시 → 런타임 env 대신 모듈 속성/체크 헬퍼를 패치.
    from src.order_webhook import app
    with patch("src.seller_console.views._check_auth", return_value=False):
        with app.test_client() as c:
            r = c.post("/seller/bookmarklet/code", data={"translate": "1"})
            assert r.status_code == 401
            assert r.get_json()["ok"] is False


def test_page_primary_is_copy_paste_method():
    # 주 방법=코드 복사→URL칸 붙여넣기. 주소창 javascript: 제거 우회 안내.
    assert "북마클릿 코드 복사" in TPL
    assert "URL 칸" in TPL and "주소창" in TPL and "javascript:" in TPL
    assert "copyBookmarkletCode" in TPL
    assert "/seller/bookmarklet/code" in TPL
    # 파일 가져오기는 대체 방법으로 보존
    assert "대체 방법" in TPL and "downloadBookmarkFile" in TPL
