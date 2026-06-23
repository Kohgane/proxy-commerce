"""tests/test_design_tokens_v18.py — v18 PART B: 디자인 토큰 단일소스(app.css)."""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path("src/static/app.css").read_text(encoding="utf-8")


def test_color_tokens_defined_with_spec_values():
    spec = {
        "--ink": "#1A1714", "--cream": "#F5EFE3", "--gold": "#C9A24B",
        "--teal": "#119A8E", "--orange": "#F5821F",
        "--text-strong": "#1A1714", "--text": "#3A352F", "--text-muted": "#7A726A",
        "--bg": "#F7F2E8", "--surface": "#FFFFFF", "--border": "#E7DECC",
        "--success": "#2E7D5B", "--warn": "#C9821F", "--danger": "#C2503C",
        "--vault-bg": "#1A1714", "--vault-text": "#F5EFE3",
    }
    for tok, val in spec.items():
        assert re.search(rf"{re.escape(tok)}\s*:\s*{val}\s*;", CSS, re.I), f"{tok}:{val} 누락"


def test_spacing_8px_grid():
    for tok, val in {"--space-1": "4px", "--space-2": "8px", "--space-4": "16px",
                     "--space-6": "32px", "--space-9": "96px"}.items():
        assert f"{tok}: {val}" in CSS


def test_radius_shadow_layout_motion_tokens():
    for tok in ("--radius-sm", "--radius", "--radius-lg", "--radius-pill",
                "--shadow-sm", "--shadow", "--shadow-lg",
                "--sidebar-w", "--content-max",
                "--dur-fast", "--dur", "--dur-slow", "--ease"):
        assert f"{tok}:" in CSS, f"{tok} 누락"


def test_typography_tokens():
    for tok in ("--font-display", "--font-ui", "--display-size", "--h1-size",
                "--body", "--caption"):
        assert f"{tok}:" in CSS
    assert "Noto Serif KR" in CSS and "Pretendard" in CSS and "Inter" in CSS
    assert "clamp(40px, 6vw, 72px)" in CSS


def test_pc_aliases_reference_v18_tokens():
    # 단일 소스: 기존 --pc-* 가 v18 토큰을 참조(하드코딩 hex 재정의 아님)
    assert "--pc-color-primary: var(--teal)" in CSS
    assert "--pc-color-cta: var(--orange)" in CSS
    assert "--pc-color-bg: var(--bg)" in CSS
    assert "--pc-font-body: var(--font-ui)" in CSS


def test_component_baseline_uses_tokens():
    # v18 §7: 타입 스케일 유틸 + 토큰 기반 버튼/입력/카드 베이스라인
    for cls in (".pc-display", ".pc-h1", ".pc-h2", ".pc-body", ".pc-caption", ".pc-stack-4"):
        assert cls in CSS, f"{cls} 유틸 누락"
    assert ".btn { border-radius: var(--radius); }" in CSS
    assert "rgba(17, 154, 142" in CSS          # 청록 포커스 링
    assert "box-shadow: var(--shadow-sm)" in CSS
    # 하드코딩 0 원칙: 베이스라인 섹션은 토큰만(focus 링 rgba는 teal 동일색 허용)
