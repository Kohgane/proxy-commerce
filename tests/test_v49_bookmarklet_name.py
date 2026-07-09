"""tests/test_v49_bookmarklet_name.py — v49 STEP3: 북마클릿 파일 이름 버그 수리(U+200B→'고가수집').

근원(오너 실기기): NETSCAPE 파일의 <A> 앵커 텍스트가 제로폭 공백(U+200B)이라 가져오기 후 북마크
이름이 '투명/빈칸'으로 보여 사용자가 못 찾음. 수리: 가시 문자열 '고가수집'. 생성 파일을 파싱해
앵커 텍스트가 가시 문자인지 검증. 병행: 코드 복사 방식(Ctrl+Shift+O) 1순위 안내.
"""
from __future__ import annotations

import re
from pathlib import Path

VIEWS_SRC = Path("src/seller_console/views.py").read_text(encoding="utf-8")
TPL = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")

_ZW = "​"


def test_generated_anchor_text_is_visible():
    from src.seller_console.views import _bookmarklet_js, _netscape_bookmark
    href = _bookmarklet_js("https://x.com", "TOK", True)
    nb = _netscape_bookmark(href, "data:image/png;base64,ABCD")
    # 앵커 텍스트 추출
    m = re.search(r'ICON="[^"]*">(.*?)</A>', nb, re.S)
    assert m, "앵커 텍스트를 찾지 못함"
    label = m.group(1)
    # 가시 문자열 — 제로폭/공백만 있으면 안 됨
    assert _ZW not in label, "제로폭 U+200B 잔존(투명 이름 버그)"
    assert label.strip() != "", "앵커 텍스트가 공백뿐(투명)"
    assert "고가수집" in label
    # 빈 문자열 아님 → 크롬이 javascript: URL을 이름으로 폴백하지 않음
    assert "javascript:" not in label


def test_netscape_default_label_visible():
    # 기본 라벨이 가시 문자열(제로폭 아님)
    src = VIEWS_SRC
    i = src.index("def _netscape_bookmark")
    sig = src[i:i + 120]
    assert _ZW not in sig, "기본 라벨에 제로폭 U+200B 잔존"
    assert 'label: str = "고가수집"' in sig


def test_copy_method_guide_and_address_bar_warning():
    # 코드 복사 방식(Ctrl+Shift+O 북마크 관리자) 안내 + 주소창 붙여넣기 경고
    assert "Ctrl+Shift+O" in TPL or "북마크 관리자" in TPL
    assert "새 북마크 추가" in TPL
    assert "주소창" in TPL and "javascript:" in TPL       # 주소창은 접두어 지움 경고
    # 파일 방식: 가져온 항목 폴더 → 북마크바로 꺼내는 안내 유지
    assert "가져온 항목" in TPL and "북마크바" in TPL
