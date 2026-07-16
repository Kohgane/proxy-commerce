"""tests/test_v45_collect_ui.py — 나이아 스크럽 성능 수정 + 중앙 수집버튼 1.5배 + 벌크바 +25%.

스크럽 무반응(리플로우) 수정: 위치는 transform(translateY)만·항목 재생성은 버킷 변경 시만·
지오메트리 1회 캐시. 확장 수집 버튼/벌크바 확대(히트영역 ≥66px).
"""
from __future__ import annotations

from pathlib import Path

JS = Path("src/seller_console/static/kgp-fastscroll.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_scrub_transform_only_no_reflow():
    # 위치는 transform(translateY)만 — top 쓰기(리플로우) 금지
    assert "style.transform = \"translateY(" in JS
    assert ".style.top =" not in JS            # 스크럽/버블 top 직접 쓰기 없음
    # 항목 재생성은 버킷 변경 시만(매 move innerHTML 금지)
    assert "if (bucket !== this.cur)" in JS
    # 지오메트리 1회 캐시(강제 리플로우 회피) + touchcancel + 에러 콘솔
    assert "_cacheGeom" in JS and "touchcancel" in JS
    assert "스크럽 오류" in JS


def test_scrub_robust_hit_area():
    # elementFromPoint 여러 x 시도(벤딩 대응) + 캐시 중심 y 최근접 폴백
    assert "elementFromPoint" in JS and "xs = [" in JS
    assert "this._cy" in JS


def test_quick_button_spec_v64():
    # v64 STEP3: 원 과대·글자 과소 수리 — 지름 절반(66→34)·아이콘 축소(21→14)·텍스트 위주 필.
    assert "min-height:34px" in CS
    assert 'font:800 " + (KGP_TOUCH ? "13px" : "15px")' in CS    # 텍스트 위주(아이콘 축소)
    assert "width:14px !important;height:14px !important" in CS   # 아이콘 21→14 (v72b: 자식 격리 !important)


def test_bulk_bar_plus25():
    # 벌크바 글자·버튼 +25%
    assert "font:16px/1.2" in CS                                 # 바 폰트 13→16
    # v72 STEP4: btnBase에 !important·line-height·all:initial 추가 → 개별 속성으로 확인.
    assert "font-size:15px !important" in CS and "min-height:40px !important" in CS   # 버튼 12→15
    assert "width:33px;height:33px" in CS                        # 그립 아이콘 26→33
