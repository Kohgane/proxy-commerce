"""tests/test_v39_d2_placeholder_kill.py — v39 D(개정): 플레이스홀더 토큰 박멸.

소스 사이트가 미치환한 템플릿 토큰({REGION_NAME - Temu Republic of Korea} 등)이
사용자 노출 제목/상세에 절대 남지 않게. 치환 실패 시 토큰 제거(가짜값 금지).
"""
from __future__ import annotations

from src.collectors.universal_scraper import strip_placeholder_tokens as strip


def test_strips_caps_template_token():
    out = strip("러기지 캐리어 {REGION_NAME - Temu Republic of Korea}")
    assert "{" not in out and "REGION_NAME" not in out
    assert "러기지 캐리어" in out
    assert out == "러기지 캐리어"           # 토큰+꼬리 구분자 정리


def test_strips_double_brace_and_percent_and_dollar():
    assert "{{" not in strip("상품 {{title}} 설명")
    assert "%" not in strip("이름 %PRODUCT_NAME% 끝") or "PRODUCT_NAME" not in strip("이름 %PRODUCT_NAME% 끝")
    assert "${" not in strip("가격 ${price} 원")


def test_keeps_normal_text_and_legit_braces():
    # CAPS 토큰이 없는 일반 중괄호/텍스트는 보존(오탐 최소 — 보수적)
    assert strip("정품 가죽 가방 (블랙)") == "정품 가죽 가방 (블랙)"
    assert strip("사이즈 {s} 선택") == "사이즈 {s} 선택"   # 소문자 단일 토큰은 미제거(보수적)


def test_empty_and_none_safe():
    assert strip("") == ""
    assert strip(None) == ""


def test_collapses_whitespace_after_removal():
    out = strip("앞부분 {REGION_CODE} 뒷부분")
    assert "  " not in out
    assert out == "앞부분 뒷부분"
