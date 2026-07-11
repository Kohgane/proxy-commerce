"""tests/test_v39b_bookmarklet_favicon.py — 북마클릿 파비콘 + 파일 가져오기(ICON 속성) 방식.

최종 해법(오너): 드래그 방식(크롬이 페이지 파비콘을 상속 → 지구본 위험) 폐기 → **크롬 북마크
가져오기 파일**의 ICON 속성에 브릿지 마크(base64)를 담아 아이콘을 확정한다.
- 설치 페이지 파비콘 링크(상속 경로 잔존 무해) 유지.
- '내 북마클릿 파일 받기' → 서버가 토큰 발급(Supabase) 후 NETSCAPE 북마크 HTML(ICON=data:image/png) 응답.
- 토스트 마크는 서버 생성 북마클릿 코드(_bookmarklet_js)가 우리 favicon으로 그린다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_install_page_favicon_links(client):
    # 설치 페이지 파비콘 = 브릿지 마크(48px PNG + shortcut icon + svg) — head 상속(무해)
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/bookmarklet").get_data(as_text=True)
    assert 'sizes="48x48"' in html and "favicon-48.png" in html
    assert 'rel="shortcut icon"' in html and "favicon.ico" in html
    assert "globe" not in BASE.lower()


def test_file_import_replaces_drag(client):
    # 드래그 방식(지구본 경로) 봉인 — 파일 받기 CTA + POST 라우트로 전환
    assert "내 북마클릿 파일 받기" in TPL
    assert "downloadBookmarkFile" in TPL and "/seller/bookmarklet/file" in TPL
    # 옛 드래그 앵커 잔재 0
    assert "draggable" not in TPL and "bmDragZone" not in TPL
    assert "issueAndBuild" not in TPL and 'id="bookmarkletLink"' not in TPL
    assert "window.open" not in TPL


def test_three_step_import_guidance():
    # v54 STEP1: 주 방법=파일 받기 → 크롬 가져오기(아이콘 포함·북마크바 직행). 복사는 대체(아이콘 없이).
    assert "파일 받기" in TPL and "아이콘 포함" in TPL
    assert "북마크바로 직행" in TPL and "고가수집기" in TPL
    assert "chrome://bookmarks" in TPL and "북마크 가져오기" in TPL
    # 크롬 버전 변수 정직 안내(가져온 북마크 폴더 폴백)
    assert "가져온 북마크" in TPL and "북마크바" in TPL
    # 복사는 대체 방법(아이콘 없이 빠른 설치)
    assert "대체 방법" in TPL and "북마클릿 코드 복사" in TPL


def test_server_builds_netscape_file_with_icon():
    # 서버가 ICON 속성(브릿지 base64) 담은 NETSCAPE 북마크 파일 생성 + 토큰 발급(Supabase) 선행
    assert "NETSCAPE-Bookmark-file-1" in VIEWS
    assert 'ICON="' in VIEWS or "ICON=\\\"" in VIEWS
    assert "data:image/png;base64," in VIEWS
    assert 'PERSONAL_TOOLBAR_FOLDER="true"' in VIEWS   # v54: 북마크바 직행 폴더
    assert 'static", "favicon-32.png"' in VIEWS or "favicon-32.png" in VIEWS   # ICON = v181 favicon-32
    assert "generate_token" in VIEWS               # 토큰 저장(Supabase 1단계) 선행
    assert 'attachment; filename' in VIEWS         # 다운로드 응답
    # 토스트 마크(우리 favicon)를 서버 북마클릿 코드가 그린다
    assert "kgpbm" in VIEWS and "favicon-32.png" in VIEWS


def test_honest_extension_main_kept():
    assert "확장 설치하기(메인)" in TPL
    assert "/seller/extension" in TPL
