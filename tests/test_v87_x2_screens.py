"""tests/test_v87_x2_screens.py — v87-X2 STEP3 화면 순회(에디토리얼 격상).

## 오너 정책(불변)
- 퍼센티 정보구조 × 한지 토큰. 문구·색 복제 금지. gogabridj-design 강제.
- 스타일·정보구조 개편이지 다운그레이드 아님(기능 0 제거). 개발표기·mock 0.

## 이 파일이 못박는 것(화면당)
- 오버라인 금 라벨 + 세리프 헤더 + 금 헤어라인(P~T 계보).
- 부트스트랩 alert/badge/파랑 잔재 0 → pc-status·pc-badge·text-teal 토큰.
- 렌더 200(회귀 게이트).
"""
from __future__ import annotations

from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates")


# ── 화면 1: 상품 수집(manual_collect) ────────────────────────────────
def test_collect_has_editorial_header():
    t = (TPL / "manual_collect.html").read_text(encoding="utf-8")
    assert 'class="console-kpi-label' in t          # 오버라인 금 라벨
    assert "해외 상품, 한 번에 담기" in t             # 세리프 헤더
    assert "pc-hairline" in t                         # 금 헤어라인


def test_collect_no_bootstrap_alert_or_primary():
    t = (TPL / "manual_collect.html").read_text(encoding="utf-8")
    # 부트스트랩 alert-*·text-primary(파랑)·하드코딩 회색 hex 잔재 0.
    assert "alert alert-" not in t
    assert "text-primary" not in t
    assert "#e5e7eb" not in t
    # 토큰 대체 확인.
    assert "pc-status" in t and "text-teal" in t
