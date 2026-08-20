"""tests/test_design_console_v32_part3.py — v32 PART3: 콘솔 디자인 실집행(대시보드 KPI 격상)."""
from __future__ import annotations

from pathlib import Path

CSS = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")
DASH = Path("src/seller_console/templates/dashboard.html").read_text(encoding="utf-8")


def test_kpi_value_is_serif_large_number():
    block = CSS[CSS.index(".console-stat-value"):CSS.index(".console-stat-value") + 320]
    assert "var(--font-display)" in block          # 세리프(잡지 통계)
    assert "clamp(" in block                        # 대형(반응형)


def test_overline_kpi_label_defined_and_used():
    assert ".console-kpi-label" in CSS
    lbl = CSS[CSS.index(".console-kpi-label"):CSS.index(".console-kpi-label") + 220]
    assert "uppercase" in lbl and "letter-spacing" in lbl
    assert "var(--gold-ink)" in lbl
    assert "console-kpi-label" in DASH              # 템플릿에서 실제 사용


def test_no_thick_borders_or_hardcoded_brand_hex_in_kpi():
    # v26: 두꺼운 보더 금지(4px) → 얇은 2px, 하드코딩 보라/인디고 제거 → 토큰
    assert "border-left: 4px" not in CSS
    assert "border-left: 2px solid transparent" in CSS
    for hx in ("#5b3df5", "#4338ca", "#eef2ff"):
        assert hx not in CSS, f"하드코딩 hex {hx} 잔존(토큰으로 치환 필요)"
    for tok in ("var(--teal)", "var(--warn)", "var(--danger)", "var(--success)"):
        assert tok in CSS


def test_kpi_uses_token_shadow_and_reduced_motion():
    # 디자인 시스템 v2(v40-2): KPI 호버 그림자가 --shadow-lg → 뉴모피즘 토큰 --nm-up-lg로 승계(단일소스 유지).
    assert "box-shadow: var(--nm-up-lg)" in CSS or "box-shadow: var(--shadow-lg)" in CSS
    assert "prefers-reduced-motion: reduce" in CSS


def test_dashboard_has_gold_hairline_divider():
    assert "pc-hairline" in DASH                    # 금 헤어라인 구분선
