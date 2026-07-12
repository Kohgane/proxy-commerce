"""tests/test_v59_bookmarklet_percent.py — v59 STEP1: 북마클릿 퍼센트 인코딩(엔티티 SyntaxError 근절).

근원(오너 콘솔): testpage 클릭 시 Uncaught SyntaxError: Unexpected token '&' — 저장된 북마크 URL에
HTML 엔티티(&#39; 등) 미디코드 잔존. 파일 원본 구문은 정상 → 가져오기·저장 경로의 엔티티 디코드 미보장이 근원.
→ javascript: 페이로드를 퍼센트 인코딩해 HTML 특수문자 의존을 제거한다.

계약(CI 게이트): 생성 파일 HREF를 unescape 없이 추출 →
  (a) '&' 문자 0개  (b) URI 디코드 → node --check 구문 통과  (c) 디코드 == 원본 JS 바이트 동일.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


def _views():
    from src.seller_console import views as v
    return v


def test_percent_encode_removes_html_specials():
    v = _views()
    enc = v._percent_encode_js("a'b\"c&d<e>f+g%h가")
    for ch in "&<>\"'+%":
        assert ch not in enc.replace("%2", "").replace("%3", "").replace("%5", "").replace("%6", "").replace("%7", "") or True
    # 직접: 인코딩 결과에 HTML 특수문자(&<>"')가 리터럴로 없어야
    assert "&" not in enc and "<" not in enc and ">" not in enc and '"' not in enc and "'" not in enc
    # 비ASCII(한글) 인코딩됨
    assert "가" not in enc and "%EA" in enc.upper()


def test_percent_encode_roundtrip_bytes_identical():
    v = _views()
    body = v._bookmarklet_js("https://kohganepercentiii.com", "tok_ABC", True)[len("javascript:"):]
    enc = v._percent_encode_js(body)
    assert urllib.parse.unquote(enc) == body, "디코드 != 원본(라운드트립 깨짐)"


def test_file_href_has_zero_ampersand():
    v = _views()
    href = v._bookmarklet_file_href("https://kohganepercentiii.com", "tok_X", True)
    nb = v._netscape_bookmark(href, "data:image/png;base64,AAAA")
    raw = re.search(r'<A HREF="([^"]*)"', nb).group(1)   # unescape 없이 그대로
    assert raw.count("&") == 0, "(a) HREF에 & 잔존"
    for ch in "<>\"'":
        assert ch not in raw, f"(a) HREF에 HTML 특수문자 {ch} 잔존"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_file_href_decodes_to_valid_js():
    v = _views()
    server, token = "https://kohganepercentiii.com", "tok_ABC123"
    href = v._bookmarklet_file_href(server, token, True)
    assert href.startswith("javascript:")
    decoded = urllib.parse.unquote(href[len("javascript:"):])
    # (c) 디코드 == 원본 JS 본문 바이트 동일
    orig = v._bookmarklet_js(server, token, True)[len("javascript:"):]
    assert decoded == orig, "(c) 디코드 != 원본 JS"
    # (b) node --check 구문 통과
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(decoded)
        path = f.name
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0, f"(b) node --check 실패: {r.stderr[:300]}"
    finally:
        os.unlink(path)


def test_code_route_shares_same_payload_source():
    # 복사 방식(/bookmarklet/code)과 파일 방식이 동일 페이로드 소스(_bookmarklet_js) 공유.
    v = _views()
    src = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    # 파일 href는 _bookmarklet_js를 인코딩, code 라우트는 _bookmarklet_js 그대로 → 같은 소스.
    assert "def _bookmarklet_file_href" in src
    assert "js = _bookmarklet_js(server, token, translate)" in src   # file href가 동일 소스 인코딩
    assert "code = _bookmarklet_js(server, raw, translate)" in src   # code 라우트 동일 소스


def test_step2_favicon512_404_fixed():
    # v59 STEP2: testpage가 존재하지 않는 favicon-512.png(404) 대신 실존 icon-512.png 참조.
    tp = Path("src/seller_console/templates/bookmarklet_testpage.html").read_text(encoding="utf-8")
    assert "favicon-512.png" not in tp, "favicon-512.png(404) 참조 잔존"
    assert "icon-512.png" in tp
    assert Path("src/seller_console/static/icon-512.png").exists()   # 참조 대상 실존


def test_step2_reinstall_warning_retained():
    # v58 규약: 북마클릿 페이지에 '기존 북마크 삭제 후 재설치' 경고 유지.
    bm = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
    assert "기존 북마크는 삭제" in bm or "전부 삭제" in bm


def test_loader_and_stamp_features_retained():
    # run.js 로더·ICON v182·PERSONAL_TOOLBAR_FOLDER·빈 앵커 유지(회귀 방지).
    v = _views()
    js = v._bookmarklet_js("https://x.com", "T", True)
    assert "/seller/bookmarklet/run.js" in js and "__kgpRun" in js   # 로더 유지
    nb = v._netscape_bookmark(v._bookmarklet_file_href("https://x.com", "T", True), "ICON")
    assert 'PERSONAL_TOOLBAR_FOLDER="true"' in nb                    # 북마크바 직행
    assert "></A>" in nb                                             # 빈 앵커 텍스트
    src = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert "favicon-32.png?v=182" in src                            # ICON v182
