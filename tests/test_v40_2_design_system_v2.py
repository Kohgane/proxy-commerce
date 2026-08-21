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


def test_bauhaus_axis_removed_no_dead_utils():
    # 오너 결정(2026-08-20): Bauhaus 축 제외 → v2 = Swiss × Neumo 2축. 죽은 유틸/토큰 잔류 0.
    for gone in (".pc-geo-circle", ".pc-geo-square", ".pc-geo-tri", "--geo:"):
        assert gone not in APP, f"Bauhaus 잔재 {gone} 제거 안 됨(죽은 코드)"


def test_neu_utilities_and_reduced_motion():
    for cls in (".pc-neu ", ".pc-neu-sm", ".pc-neu-in", ".pc-neu-lift", ".pc-neu-toggle"):
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


def test_stage2_console_cards_buttons_toggle_neumorphism():
    # Stage 2: 콘솔 카드/빈상태/스텝 카드 + 토글 스위치 뉴모피즘, 세컨더리 버튼 종이 표면.
    card = CONSOLE.split(".console-step-card {", 1)[1].split("}", 1)[0]
    assert "var(--nm-up" in card and "border: 0" in card
    assert ".form-switch .form-check-input" in CONSOLE and "var(--nm-in)" in CONSOLE
    gold = APP.split(".btn-gold {", 1)[1].split("}", 1)[0]
    assert "var(--nm-up-sm)" in gold and "border: 0" in gold


def test_stage3_swiss_table_and_empty_state():
    # Stage 3: Swiss 테이블(오버라인 헤더·헤어라인 행) + Swiss 빈 상태 타이포 위계(기하 장식 0).
    assert ".pc-swiss-table > thead th" in CONSOLE
    thead = CONSOLE.split(".pc-swiss-table > thead th", 1)[1].split("}", 1)[0]
    assert "text-transform: uppercase" in thead and "var(--gold-ink" in thead
    assert "var(--hairline-color" in thead                       # 헤어라인 하단선
    assert ".pc-swiss-table > tbody > tr > td" in CONSOLE
    assert ".console-empty-state .pc-empty-title" in CONSOLE and "var(--font-display)" in CONSOLE
    # Bauhaus 기하 장식 없음(회귀 가드).
    assert ".pc-geo" not in CONSOLE


def test_stage4_swiss_table_extended_to_lists():
    # Stage 4: 주문·마켓·카탈로그 리스트에 Swiss 테이블 확대(수집이력과 동일 위계).
    TPL = Path("src/seller_console/templates")
    for name in ("orders.html", "markets.html", "catalog.html"):
        html = (TPL / name).read_text(encoding="utf-8")
        assert "pc-swiss-table" in html, f"{name} Swiss 테이블 미적용"


def test_stage4_onboarding_swiss_tokenized_no_lavender():
    # Stage 4: 온보딩 카드 라벤더 default 제거 → 토큰(청록 현재단계/완료·금 헤어라인). 하드코딩 보랏빛 0.
    for lav in ("#d9d6ff", "#c7bfff", "#bbf7d0", "#f0fdf4", "#f7f6ff", "#3b2bb3", "#5b3df5"):
        assert lav not in CONSOLE, f"온보딩 라벤더 하드코딩 {lav} 잔존(토큰화 필요)"
    ob = CONSOLE.split(".console-onboarding-card {", 1)[1].split("}", 1)[0]
    assert "var(--hairline-color" in ob                      # 금 헤어라인
    nxt = CONSOLE.split(".onboarding-step-card.onboarding-step-next", 1)[1].split("}", 1)[0]
    assert "var(--teal)" in nxt and "var(--nm-up-sm)" in nxt  # 현재단계 청록 + 뉴모 토큰 그림자


def test_root_palette_unchanged_aa_safe():
    # 뿌리 토큰 불변(강조 3색) — 그림자만 추가, 팔레트 재정의 아님.
    assert "--gold: #C9A24B" in APP and "--teal: #119A8E" in APP and "--orange: #F5821F" in APP
