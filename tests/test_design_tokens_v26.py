"""tests/test_design_tokens_v26.py — v26 네오-클래식 리프레시 토큰/유틸 단일소스 가드."""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path("src/static/app.css").read_text(encoding="utf-8")


def test_v26_tokens_defined_in_root():
    for tok, val in {
        "--ink-2": "#2A241E",
        "--gold-soft": "#E0C588",
        "--display-2-size": "clamp(44px, 7vw, 84px)",
        "--space-10": "128px",
        "--grain-opacity": "0.035",
    }.items():
        assert re.search(rf"{re.escape(tok)}\s*:\s*{re.escape(val)}\s*;", CSS, re.I), f"{tok}:{val} 누락"
    assert "--hairline-color:" in CSS
    assert "--lift:" in CSS


def test_v26_utilities_present():
    for cls in (".pc-display-2", ".pc-overline", ".pc-hairline", ".pc-num",
                ".pc-section", ".pc-lift", ".pc-link", ".pc-enter"):
        assert cls in CSS, f"{cls} 유틸 누락"


def test_v26_grain_and_reduced_motion_guard():
    assert "body::before" in CSS                 # 미세 그레인 전역 오버레이
    assert "fractalNoise" in CSS                  # SVG 노이즈(이미지 의존 0)
    assert "prefers-reduced-motion: reduce" in CSS
    # reduced-motion에서 그레인/모션 정지
    rm = CSS[CSS.index("prefers-reduced-motion: reduce"):]
    assert "body::before { display: none" in rm


def test_v18_display_size_unchanged_no_regression():
    # v26은 --display-2-size를 새로 추가(별도). 기존 v18 --display-size는 그대로(회귀 0).
    assert "--display-size: clamp(40px, 6vw, 72px)" in CSS


def _outside_root() -> str:
    spans, css = [], CSS
    for m in re.finditer(r":root\s*\{", css):
        i = m.end(); d = 1
        while i < len(css) and d > 0:
            if css[i] == "{": d += 1
            elif css[i] == "}": d -= 1
            i += 1
        spans.append((m.start(), i))
    out, p = "", 0
    for a, b in spans:
        out += css[p:a]; p = b
    return out + css[p:]


def test_v26_utilities_use_tokens_not_hardcoded_hex():
    body = _outside_root().lower()
    # v26 신규 브랜드 음영도 :root 밖 하드코딩 금지(토큰 var()만)
    for hx in ("#2a241e", "#e0c588"):
        assert hx not in body, f"v26 hex {hx} 가 :root 밖에 하드코딩됨"
