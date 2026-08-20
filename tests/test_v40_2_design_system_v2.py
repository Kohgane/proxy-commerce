"""tests/test_v40_2_design_system_v2.py — 디자인 시스템 v2 (Swiss×Bauhaus×Neumorphism) 파운데이션 가드.

Stage 1: app.css 뉴모피즘 토큰 + Bauhaus 유틸 단일소스 + 콘솔 KPI 카드 뉴모피즘 표면.
뿌리(토큰) 불변 · 강조색은 기존 3토큰(금·청록·주황)만 · 그림자는 텍스트 대비 불변(AA).
"""
from __future__ import annotations

from pathlib import Path

APP = Path("src/static/app.css").read_text(encoding="utf-8")
CONSOLE = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")


def test_neumorphism_tokens_single_source():
    for tok in ("--nm-up:", "--nm-up-sm:", "--nm-up-lg:", "--nm-in:"):
        assert tok in APP, f"{tok} 뉴모피즘 토큰 누락(app.css 단일소스)"
    # 이중 그림자(광원 좌상단: 밝은 흰 + 어두운 먹) 형태 확인.
    assert "rgba(255, 255, 255" in APP and "rgba(26, 23, 20" in APP


def test_bauhaus_geo_utilities_use_brand_tokens():
    for cls in (".pc-geo-circle", ".pc-geo-square", ".pc-geo-tri"):
        assert cls in APP, f"{cls} Bauhaus 유틸 누락"
    # 원=금, 사각=청록, 삼각=주황(원색은 기존 3토큰만 — 신 원색 도입 0)
    assert "solid var(--gold)" in APP
    assert "background: var(--teal)" in APP
    assert "solid var(--orange)" in APP


def test_neu_utilities_and_reduced_motion():
    for cls in (".pc-neu ", ".pc-neu-sm", ".pc-neu-in", ".pc-neu-lift"):
        assert cls in APP, f"{cls} 뉴모피즘 유틸 누락"
    # 모션 접근성: reduced-motion에서 lift 정지.
    assert "prefers-reduced-motion" in APP
    seg = APP.split(".pc-neu-lift", 1)[1]
    assert "prefers-reduced-motion" in seg


def test_console_kpi_card_uses_neumorphism_tokens():
    # KPI 카드가 하드 그림자/보더 대신 단일소스 뉴모피즘 토큰 사용(전 KPI 화면 일괄 적용).
    block = CONSOLE.split(".console-kpi-card {", 1)[1].split("}", 1)[0]
    assert "var(--nm-up)" in block
    assert "border: 0" in block and "var(--radius-xl)" in block
    hov = CONSOLE.split(".console-kpi-card:hover", 1)[1].split("}", 1)[0]
    assert "var(--nm-up-lg)" in hov          # 호버도 토큰(하드코딩 그림자 0)


def test_root_palette_unchanged_aa_safe():
    # 뿌리 토큰 불변(강조 3색) — 그림자만 추가, 팔레트 재정의 아님.
    assert "--gold: #C9A24B" in APP and "--teal: #119A8E" in APP and "--orange: #F5821F" in APP
