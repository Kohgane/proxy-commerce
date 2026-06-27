"""tests/test_v33_toast.py — v33 3-3: 네오-클래식 토스트(먹/한지/금·라인 아이콘·이모지 0)."""
from __future__ import annotations

from pathlib import Path

JS = Path("src/seller_console/static/seller.js").read_text(encoding="utf-8")
CSS = Path("src/static/app.css").read_text(encoding="utf-8")


def _pctoast_block() -> str:
    i = JS.index("function pcToast")
    return JS[i:i + 3200]


def test_toast_uses_line_icons_not_emoji():
    blk = _pctoast_block()
    # 라인 아이콘(bi-*) 사용, 이모지 0
    for ic in ("bi-check-circle", "bi-x-circle", "bi-exclamation-triangle", "bi-info-circle"):
        assert ic in blk, f"{ic} 누락"
    for em in ("✅", "❌", "⚠️", "ℹ️"):
        assert em not in blk, f"토스트에 이모지 {em} 잔존"
    assert "pc-toast" in blk and "pc-toast-" in blk


def test_toast_has_manual_and_auto_close():
    blk = _pctoast_block()
    assert "수동 닫기" in blk and "자동 닫기" in blk
    assert "setTimeout(dismiss" in blk


def test_toast_css_neo_classic_tokens():
    # 먹 배경·한지 텍스트·금 보더·유형 좌악센트(토큰 단일소스)
    assert ".pc-toast {" in CSS
    blk = CSS[CSS.index(".pc-toast {"):CSS.index(".pc-toast {") + 700]
    assert "var(--vault-surface)" in blk      # 먹 배경
    assert "var(--vault-text)" in blk          # 한지 텍스트
    assert "var(--gold)" in blk                # 금 보더
    for accent in (".pc-toast-success", ".pc-toast-warning", ".pc-toast-danger"):
        assert accent in CSS
    assert "var(--teal)" in CSS and "var(--orange)" in CSS and "var(--danger)" in CSS


def test_toast_reduced_motion_guard():
    seg = CSS[CSS.index(".pc-toast {"):]
    assert "prefers-reduced-motion: reduce" in seg
    assert "pcToastIn" in CSS                   # 슬라이드-인 키프레임
