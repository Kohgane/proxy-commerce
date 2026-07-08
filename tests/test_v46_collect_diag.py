"""tests/test_v46_collect_diag.py — v46 STEP2: 수집 실패 3지점 진단 + 부분수집 정직 표기.

(a) 페이지 추출 실패 → partial 정직 토스트('성공처럼' 금지) + 콘솔 warn.
(b) API 전송 4xx/5xx → background 콘솔 로그 + HTTP 상태 토스트.
(c) 서버 저장 실패 → 서버 예외스택 로그 + 502. 401=재발급 안내, CSP=확장 안내(북마클릿).
확장·북마클릿 동일 추출기(#441)가 partial 판정 공유.
"""
from __future__ import annotations

from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
API = Path("src/api/extension_api.py").read_text(encoding="utf-8")


def test_a_partial_honest_toast_extension():
    # 부분 수집이면 '수집 완료'가 아니라 '부분 수집' 정직 표기(성공처럼 금지) + 콘솔 warn
    assert "meta.partial" in CS
    assert "부분 수집" in CS
    assert "console.warn" in CS and "부분 수집" in CS
    # 추출기가 partial 판정 + 콘솔 소스 로그
    assert "partial" in EX and "추출 소스=" in EX


def test_a_partial_honest_toast_bookmarklet():
    # 북마클릿도 동일 추출기(data.partial) → 부분 수집 정직 표기
    assert "data.partial" in VIEWS and "부분 수집" in VIEWS


def test_b_api_transport_logged():
    # 전송 실패(4xx/5xx) 콘솔 로그 + HTTP 상태 노출
    assert "POST ${endpoint}" in BG and "response.status" in BG
    assert "httpStatus" in BG and "httpStatus" in CS


def test_c_server_save_failure_and_401_csp():
    # 서버 저장 실패 예외스택 로그 + 502 정직
    assert "logger.exception" in API
    assert "durable" in API
    # 401 재발급 안내(확장) + CSP 안내(북마클릿)
    assert "authRequired" in CS and "토큰을 다시 설정" in CS
    assert "보안정책(CSP)" in VIEWS and "크롬 확장" in VIEWS
