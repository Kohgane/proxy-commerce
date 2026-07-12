"""tests/test_v54_bookmarklet_toolbar.py — v54 STEP1: 북마클릿 파비콘 북마크바 직행.

전제(오너): javascript: 북마크 파비콘은 가져오기 파일 ICON 속성만이 유일 기록 경로. NETSCAPE 파일을
PERSONAL_TOOLBAR_FOLDER="true" 폴더 하위에 배치 → 크롬이 북마크바로 직행 병합. ICON=v181 favicon-32.
페이지 1순위=파일 받기→가져오기(아이콘 포함), 복사=아이콘 없이 빠른 설치로 정직 라벨.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

BM = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")


def test_netscape_personal_toolbar_folder():
    from src.seller_console.views import _netscape_bookmark, _bridge_icon_data_uri
    b = _netscape_bookmark("javascript:void(0)", _bridge_icon_data_uri())
    assert 'PERSONAL_TOOLBAR_FOLDER="true"' in b        # 북마크바 직행
    assert b.count("<DL><p>") == 2                        # 폴더 중첩 구조
    assert 'ICON="data:image/png;base64,' in b           # ICON 속성(유일 파비콘 경로)
    assert "></A>" in b  # v56: 앵커 텍스트 빈 문자열(파비콘만)


def test_icon_is_v181_favicon32_not_stale():
    from src.seller_console.views import _bridge_icon_data_uri
    uri = _bridge_icon_data_uri()
    fav32 = "data:image/png;base64," + base64.b64encode(
        Path("src/seller_console/static/favicon-32.png").read_bytes()).decode("ascii")
    assert uri == fav32                                   # v181 favicon-32(현행), 구 아이콘 아님


def test_page_file_first_copy_secondary():
    # 1순위 = 파일 받기(아이콘 포함), 복사 = '아이콘 없이 빠른 설치'로 강등·정직 라벨.
    assert "① 파일 받기" in BM and "아이콘 포함" in BM
    assert "아이콘 없이 빠른 설치" in BM                  # 복사 방식 정직 라벨
    assert "북마크바로 직행" in BM
    assert "favicon-32.png?v=182" in BM                   # 아이콘 미리보기
    # 파일 카드가 복사 카드보다 앞(1순위)
    assert BM.index("① 파일 받기") < BM.index("아이콘 없이 빠른 설치")
    # 크롬 버전 변수 정직 안내(추측 금지)
    assert "가져온 북마크" in BM or "Imported" in BM


def test_file_download_endpoint():
    from src.order_webhook import app
    from unittest.mock import patch
    with patch("src.auth.personal_tokens.generate_token", return_value={"raw_token": "tok_abc"}):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
            r = c.post("/seller/bookmarklet/file", data={"translate": "1"})
            assert r.status_code == 200
            body = r.get_data(as_text=True)
            assert 'PERSONAL_TOOLBAR_FOLDER="true"' in body and "ICON=" in body
            cd = r.headers.get("Content-Disposition") or ""
            assert "attachment" in cd and (".html" in cd)     # 첨부 다운로드(한글 파일명은 UTF-8 인코딩)
