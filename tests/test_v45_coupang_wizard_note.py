"""tests/test_v45_coupang_wizard_note.py — 마켓연동 위저드 쿠팡 정직 안내.

쿠팡 카드에만: '키는 판매자당 1개·다른 셀러툴 동시연동 불가', '수정 주 10회·반영 최대 30분'.
"""
from __future__ import annotations

from pathlib import Path

TPL = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")


def test_coupang_note_present_and_scoped():
    assert "m.market == 'coupang'" in TPL          # 쿠팡 카드에만 노출
    assert "mc-note-coupang" in TPL


def test_coupang_note_content():
    assert "판매자당 1개" in TPL
    assert "동시 연동" in TPL
    assert "주 10회" in TPL
    assert "최대 30분" in TPL


def test_coupang_note_uses_tokens_no_emoji():
    i = TPL.index("mc-note-coupang")
    block = TPL[i:i + 700]
    assert "var(--warn" in block                    # 토큰(하드코딩 hex 아님)
    assert "bi-info-circle" in block                # 아이콘(이모지 0)
    # 이모지 없음(대표적인 것만 확인)
    for emo in ("⚠️", "❗", "🚫", "✅"):
        assert emo not in block
