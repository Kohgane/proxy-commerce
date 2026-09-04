"""tests/test_v39_g2_market_cards.py — v39 G(개정): 마켓 등록 카드 레이아웃.

좁은 드로어에서 라벨이 세로로 한 글자씩 쪼개지던 것 → 균등 폭 그리드 + nowrap 라벨.
하드코딩 hex(보라 #6f42c1) 제거 → 토큰(var(--teal) 등). 카드 = [체크박스][마켓명][상태배지] 한 줄.
"""
from __future__ import annotations

from pathlib import Path

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
CSS_S6C = Path("src/static/app.css").read_text(encoding="utf-8")
# ★ Stage 6-c(2026-09-03): 이 화면들의 CSS가 템플릿 `<style>`/인라인 → **app.css로 이관**됐다.
#   핀이 보는 건 "그 규칙이 살아 있나"이지 "어느 파일에 있나"가 아니다 — 소스만 갈아끼운다.



def test_uses_even_grid_not_bootstrap_cols():
    # col-6 col-md-4(좁아지면 글자 쪼개짐) 폐기 → 최소폭 보장 균등 그리드
    assert "market-grid" in PREVIEW
    assert "repeat(auto-fill, minmax(170px, 1fr))" in CSS_S6C
    assert "col-6 col-md-4" not in PREVIEW          # 옛 좁은 칸 마크업 잔존 0


def test_label_nowrap_no_vertical_char_split():
    # 마켓명은 가로 한 줄 고정(세로 한 글자씩 쪼개짐 방지)
    assert ".market-tile .market-name" in CSS_S6C
    block = CSS_S6C.split(".market-tile .market-name")[1][:280]
    assert "white-space: nowrap" in block
    assert "text-overflow: ellipsis" in block
    # word-break:break-all(글자 단위 줄바꿈 유발) 미사용
    assert "word-break: break-all" not in CSS_S6C.split(".market-tile")[1][:900]


def test_tokenized_no_hardcoded_purple():
    # 하드코딩 보라(#6f42c1) 제거 → 토큰
    assert "#6f42c1" not in PREVIEW and "#6f42c1" not in CSS_S6C
    assert "var(--teal" in CSS_S6C


def test_card_has_checkbox_name_badge():
    assert "market-upload-check" in PREVIEW
    assert "market-name" in PREVIEW
    assert "market-badge" in PREVIEW
    assert "스마트스토어" in PREVIEW and "코가네멀티샵" in PREVIEW
