"""tests/test_v39_m3_mobile_drawer.py — v39-M M3: 모바일 반응형 드로어(풀스크린 바텀시트).

드로어 = 아래에서 올라오는 풀스크린 시트, 하단 고정 액션바(저장/등록 ≥44px), 가로 스크롤 0.
"""
from __future__ import annotations

from pathlib import Path

# ★ Stage 6-c(2026-09-03): 드로어·편집기 CSS가 템플릿 `<style>`에서 **app.css로 이관**됐다.
#   핀은 "그 규칙이 살아 있나"를 보는 것이지 "어느 파일에 있나"가 아니다 — 소스만 갈아끼운다.
HIST = Path("src/static/app.css").read_text(encoding="utf-8")
PREVIEW = Path("src/static/app.css").read_text(encoding="utf-8")
TPL_HIST = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")


def test_drawer_is_bottom_sheet_on_mobile():
    # 모바일 미디어쿼리에서 바텀시트(아래→위) + 풀폭 + 둥근 상단
    assert "@media (max-width: 767.98px)" in HIST
    # app.css엔 767.98 미디어쿼리가 여럿이다 — **드로어 규칙이 든 것**을 골라야 핀이 의미를 갖는다.
    mob = next(b[:600] for b in HIST.split("@media (max-width: 767.98px)")[1:] if ".kgp-drawer" in b[:600])
    assert "translateY(100%)" in mob          # 아래에서 올라옴
    assert "bottom: 0" in mob
    assert "border-radius: var(--radius-2xl) var(--radius-2xl) 0 0" in mob   # 6-c: 토큰화


def test_drawer_close_target_at_least_44():
    # 닫기 버튼 터치 타깃 ≥44px
    assert "width: 44px; height: 44px" in HIST


def test_drawer_grip_handle_present():
    assert "kgp-drawer-grip" in HIST


def test_editor_sticky_action_bar_44px_in_drawer():
    assert "kgp-action-bar" in PREVIEW
    # 드로어 스타일 블록에 sticky 하단 + 44px
    assert "position: sticky; bottom: 0" in PREVIEW
    assert "min-height: 44px" in PREVIEW


def test_editor_no_horizontal_scroll_in_drawer():
    assert "overflow-x: hidden" in PREVIEW
    assert "max-width: 100% !important" in PREVIEW
