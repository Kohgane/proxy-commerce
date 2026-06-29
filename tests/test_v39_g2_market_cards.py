"""tests/test_v39_g2_market_cards.py — v39 G(개정): 마켓 등록 카드 레이아웃.

좁은 드로어에서 라벨이 세로로 한 글자씩 쪼개지던 것 → 균등 폭 그리드 + nowrap 라벨.
하드코딩 hex(보라 #6f42c1) 제거 → 토큰(var(--teal) 등). 카드 = [체크박스][마켓명][상태배지] 한 줄.
"""
from __future__ import annotations

from pathlib import Path

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


def test_uses_even_grid_not_bootstrap_cols():
    # col-6 col-md-4(좁아지면 글자 쪼개짐) 폐기 → 최소폭 보장 균등 그리드
    assert "market-grid" in PREVIEW
    assert "repeat(auto-fill, minmax(170px, 1fr))" in PREVIEW
    assert "col-6 col-md-4" not in PREVIEW          # 옛 좁은 칸 마크업 잔존 0


def test_label_nowrap_no_vertical_char_split():
    # 마켓명은 가로 한 줄 고정(세로 한 글자씩 쪼개짐 방지)
    assert ".market-tile .market-name" in PREVIEW
    block = PREVIEW.split(".market-tile .market-name")[1][:200]
    assert "white-space: nowrap" in block
    assert "text-overflow: ellipsis" in block
    # word-break:break-all(글자 단위 줄바꿈 유발) 미사용
    assert "word-break: break-all" not in PREVIEW


def test_tokenized_no_hardcoded_purple():
    # 하드코딩 보라(#6f42c1) 제거 → 토큰
    assert "#6f42c1" not in PREVIEW
    assert "var(--teal" in PREVIEW


def test_card_has_checkbox_name_badge():
    assert "market-upload-check" in PREVIEW
    assert "market-name" in PREVIEW
    assert "market-badge" in PREVIEW
    assert "스마트스토어" in PREVIEW and "코가네멀티샵" in PREVIEW
