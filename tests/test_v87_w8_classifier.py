"""tests/test_v87_w8_classifier.py — v87-W8 item1: 자동 분류 오류(제목 우선).

오너 실증: 그릇→디지털·폰그립→홈/가구/주방(역방향). 원인 = 제목·설명·키워드 동등 가중 substring →
설명 속 부수 카테고리어가 제목의 실제 상품어를 눌러 오분류. 수리 = 제목 우선(설명 노이즈 차단),
제목 약할 때만 설명 종합. 확신 없으면 GEN+수동(오분류 확신 찍기 금지).
"""
from __future__ import annotations

import pytest

from src.seller_console.category_classifier import classify


def test_phone_grip_title_wins_over_desc_noise():
    r = classify("스마트폰 그립톡 폰그립", "책상이나 주방 어디서든 거치 그릇 모양")
    assert r["code"] == "DIG" and r["basis"] == "title" and r["needs_manual"] is False


def test_bowl_title_wins_over_desc_noise():
    r = classify("도자기 그릇 세트", "충전기 케이블 usb 태블릿 거치")
    assert r["code"] == "HOM" and r["basis"] == "title"


def test_title_gen_falls_back_to_desc():
    # 제목이 무매칭(원문 영문 등) → 설명(한국어)로 종합 분류.
    r = classify("SUPERONE phone grip", "스마트폰 그립 거치대 휴대폰 액세서리")
    assert r["code"] == "DIG" and r["basis"] == "combined"


def test_low_confidence_is_manual_not_confident_wrong():
    # 근거 약하면 확신 찍지 말고 기타+수동(정직).
    r = classify("차")
    assert r["code"] == "GEN" and r["needs_manual"] is True


def test_no_match_gen_zero_conf():
    r = classify("zzzz qqqq 1234")
    assert r["code"] == "GEN" and r["confidence"] == 0.0 and r["needs_manual"] is True


def test_regression_car_desk_and_tea_preserved():
    assert classify("접이식 차량용 책상")["code"] == "HOM"
    assert classify("제주 녹차 선물세트")["code"] == "FOD"
    assert classify("원목 5단 옷장 수납장")["code"] == "HOM"
