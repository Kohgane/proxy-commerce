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
    # v56 STEP1(오너 요청): 앵커 텍스트=빈 문자열(파비콘만 표시). 단 **제로폭 U+200B는 금지**(투명 이름
    #   폴백/javascript: URL 노출 버그의 근원) — 완전 빈 문자열 "" 이어야 하며, ICON이 아이콘을 담당.
    from src.seller_console.views import _bookmarklet_js, _netscape_bookmark
    href = _bookmarklet_js("https://x.com", "TOK", True)
    nb = _netscape_bookmark(href, "data:image/png;base64,ABCD")
    m = re.search(r'ICON="[^"]*">(.*?)</A>', nb, re.S)
    assert m, "앵커 요소를 찾지 못함"
    label = m.group(1)
    assert label == "", "앵커 텍스트는 빈 문자열이어야(파비콘만)"
    assert _ZW not in nb, "제로폭 U+200B 금지"
    assert "ICON=" in nb                                   # 아이콘이 표시를 담당


def test_netscape_empty_anchor_no_zero_width():
    # v56: 앵커 텍스트 빈 문자열(파비콘만) — 제로폭 U+200B는 여전히 금지(폴백 버그 근원).
    from src.seller_console.views import _netscape_bookmark
    nb = _netscape_bookmark("javascript:void(0)", "data:image/png;base64,AB")
    assert "></A>" in nb and _ZW not in nb


def test_copy_method_guide_and_address_bar_warning():
    # 코드 복사 방식(Ctrl+Shift+O 북마크 관리자) 안내 + 주소창 붙여넣기 경고
    assert "Ctrl+Shift+O" in TPL or "북마크 관리자" in TPL
    assert "새 북마크 추가" in TPL
    assert "주소창" in TPL and "javascript:" in TPL       # 주소창은 접두어 지움 경고
    # v54: 파일 방식 폴백 안내 = '가져온 북마크'(Imported) 폴더 → 북마크바
    assert "가져온 북마크" in TPL and "북마크바" in TPL
