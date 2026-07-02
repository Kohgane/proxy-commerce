"""tests/test_v41_x2_category_misclassify.py — v41 X-2: 자동 카테고리 오분류 수리.

증상: "접이식 차량용 책상" → '식품/차'(FOD). 원인 = 단어 부분일치로 한 글자 '차'(tea)가
'차량'(vehicle) 안에 substring 매칭. 수리: 한 글자 키워드는 독립 토큰일 때만 + 근거 약하면 '직접 선택'.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.seller_console.category_classifier import classify  # noqa: E402


def test_car_desk_is_not_food():
    """오너 보고 케이스: 접이식 차량용 책상 → 식품/차 금지 → 가구(HOM)."""
    r = classify("접이식 차량용 책상")
    assert r["code"] == "HOM", r          # 책상 → 가구/수납
    assert r["code"] != "FOD"
    assert "차" not in r["matched"]        # 한 글자 '차'가 '차량'에 substring 오매칭되지 않음


def test_vehicle_words_do_not_match_tea():
    """차량/주차/세차/기차 등 '차' 포함 복합어는 tea(FOD)로 안 간다."""
    for t in ["차량용 방석", "주차 번호판", "세차 타월", "기차 여행 가방"]:
        assert classify(t)["code"] != "FOD", t


def test_real_tea_still_classifies_food():
    """진짜 차(茶)는 멀티글자 키워드로 FOD 유지(회귀 0)."""
    assert classify("제주 녹차 선물세트")["code"] == "FOD"
    assert classify("홍차 티백 100개입")["code"] == "FOD"
    assert classify("원두 커피 드립백")["code"] == "FOD"


def test_ambiguous_single_char_asks_manual():
    """근거가 동음이의 한 글자뿐이면 확정 대신 직접 선택(정직)."""
    r = classify("차")   # 단독 '차' — 자동차? 茶? 차이? 모호
    assert r["code"] == "GEN"
    assert r.get("needs_manual") is True


def test_multi_char_keeps_confident_category():
    """뚜렷한 멀티글자 근거는 확신 카테고리 유지 + needs_manual False."""
    r = classify("포터 가죽 백팩 데일리")
    assert r["code"] == "BAG" and r["confidence"] >= 0.5
    assert r.get("needs_manual") is False


def test_wardrobe_not_clothes_via_substring():
    """'옷장'(가구)이 한 글자 '옷'(CLO) substring으로 의류 오분류되지 않음."""
    r = classify("원목 5단 옷장 수납장")
    assert r["code"] != "CLO"      # 옷장/수납장 → 가구
    assert r["code"] == "HOM"


def test_no_match_is_gen_zero_conf():
    """무매칭은 GEN·confidence 0.0(기존 계약 유지)."""
    r = classify("zzzz qqqq 1234")
    assert r["code"] == "GEN" and r["confidence"] == 0.0
    assert r.get("needs_manual") is True
