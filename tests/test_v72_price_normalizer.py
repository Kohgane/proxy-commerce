"""tests/test_v72_price_normalizer.py — v72 STEP2: 가격 정규화 단일 관문.

증상: "81800."(꼬리 점) → 드로어 0.00(숫자 변환 사망). 수리: 서버 저장 직전 단일 정규화 함수
[꼬리·머리 비숫자 제거·천단위 콤마 제거·소수점 검증]→Decimal. 실패 시 원문 보존+누락(0.00 저장 금지).
"""
from __future__ import annotations

import pytest

from src.collectors.collect_sanitize import (
    normalize_price,
    renormalize_all,
    renormalize_price_field,
    sanitize_price,
    sanitize_payload,
)


@pytest.mark.parametrize("raw,expected", [
    ("81800.", "81800"),      # 꼬리 점 → 정수(드로어 0.00 근원)
    ("1,234", "1234"),        # 천단위 콤마
    ("29.99", "29.99"),       # 소수 유지
    ("₩81,800", "81800"),     # 통화기호 머리 제거
    ("81,800.50", "81800.50"),
    ("  61144 원", "61144"),  # 꼬리 문자 제거
    ("81800.00", "81800.00"), # 소수부 정보 보존
    ("USD 12.50", "12.50"),
])
def test_normalize_price_contract(raw, expected):
    norm, ok = normalize_price(raw)
    assert ok is True and norm == expected, (raw, norm)


@pytest.mark.parametrize("raw", ["", "  ", "0", "0.00", ".", "abc", "없음", None])
def test_normalize_price_failures(raw):
    norm, ok = normalize_price(raw)
    assert ok is False and norm == "", (raw, norm)


def test_sanitize_price_stores_normalized():
    # "81800." + KRW → 정규화 "81800" 저장(꼬리 점 제거, 0.00 아님).
    price, status, warns = sanitize_price("81800.", "KRW")
    assert price == "81800" and status == "", (price, status)
    # 콤마도 제거.
    assert sanitize_price("1,234", "KRW")[0] == "1234"
    # 실패(파싱불가) → 빈값 needs_check(0.00 저장 금지).
    assert sanitize_price("N/A", "KRW") == ("", "needs_check", [])
    # 통화 미상 → 폐기.
    assert sanitize_price("81800.", "")[1] == "needs_check"
    # 비상식 하한(9 KRW) → 폐기(v55 유지).
    assert sanitize_price("9", "KRW")[1] == "needs_check"


def test_sanitize_payload_normalizes_price():
    p = {"price": "81800.", "currency": "KRW"}
    sanitize_payload(p)
    assert p["price"] == "81800" and p["price_status"] == ""
    # 0.00 저장 금지: 파싱 실패 시 빈값.
    p2 = {"price": "정보없음", "currency": "KRW"}
    sanitize_payload(p2)
    assert p2["price"] == "" and p2["price_status"] == "needs_check"


def test_renormalize_price_field_migration():
    # 기저장 오염 재정규화: 폴루션 값 → 정규화(changed True), 이미 깨끗하면 changed False.
    assert renormalize_price_field("81800.") == ("81800", True)
    assert renormalize_price_field("1,234") == ("1234", True)
    assert renormalize_price_field("81800") == ("81800", False)   # 이미 깨끗
    assert renormalize_price_field("") == ("", False)             # 원문 보존(빈값)
    assert renormalize_price_field("N/A") == ("N/A", False)       # 파싱 실패 → 원문 보존(0.00 저장 금지)


def test_renormalize_all_batch():
    # 주입식 배치: 오염 2건만 변경, 깨끗/실패는 미변경.
    items = [("a", "81800."), ("b", "1,234"), ("c", "29.99"), ("d", "정보없음"), ("e", "")]
    updated = {}
    stats = renormalize_all(items, lambda iid, p: updated.__setitem__(iid, p))
    assert stats == {"scanned": 5, "changed": 2}, stats
    assert updated == {"a": "81800", "b": "1234"}   # c 이미 깨끗·d 실패·e 빈값 미변경
