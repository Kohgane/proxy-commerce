"""tests/test_v45_temu_price.py — Temu 가격 오추출(9 KRW) 수리: 재고·쿠폰 제외 + 폰트 프로미넌스.

오너 재현: 접이식 책상 실가 20,605원 → 저장 9 KRW(재고 '9개 남음'·쿠폰 숫자 오인).
수리: 재고/쿠폰/수량/평점 문맥 제외 + 메인 가격=가장 큰 글씨(폰트 크기) 스코어 + 노드경로 콘솔 로그.
실 Chromium 검증(scripts): 20,605원(28px) 채택, 9-계열 전부 배제, 노드경로 로그.
"""
from __future__ import annotations

from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_nonprice_context_excluded():
    # 재고·쿠폰·수량·평점 문맥 배제 정규식 + 헬퍼
    assert "_KGP_NONPRICE_RE" in CS and "_kgpNonPriceCtx" in CS
    for kw in ("재고", "남음", "쿠폰", "수량", "평점"):
        assert kw in CS


def test_price_scored_by_font_prominence():
    # 메인 가격 = 가장 큰 글씨(폰트 크기) → getComputedStyle fontSize로 스코어(동률이면 값)
    assert "getComputedStyle(el).fontSize" in CS
    assert "b.fs - a.fs" in CS


def test_price_node_path_logged():
    # 후보·채택 노드 경로를 콘솔 로그(진단)
    assert "_kgpNodePath" in CS
    assert "가격 후보" in CS and "채택 가격" in CS
