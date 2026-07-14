"""tests/test_v67_option_badge.py — v67 STEP3: 옵션 미수집 문구 검증.

'옵션 미수집' 배지가 무옵션 상품(단일 상품)과 추출 실패를 구분 — 무옵션은 '단일 상품' 중립 표기,
추출 실패만 경고색. 핵심 필드(가격·이미지) 판독 여부로 구분.
"""
from __future__ import annotations

from pathlib import Path

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


def test_option_badge_distinguishes_single_vs_fail():
    # 핵심 필드 판독 여부(coreOk)로 무옵션 vs 추출 실패 구분.
    assert "var coreOk = _imgOk && _priceOk" in PREVIEW
    # 무옵션 = 중립('단일 상품', 한지/muted 토큰 — 경고색 아님).
    assert "단일 상품" in PREVIEW
    assert "background:var(--hanji,#f5efe3);color:var(--muted,#8a8275)" in PREVIEW
    # 추출 실패 = 경고색(주황 warn).
    assert "옵션 미수집" in PREVIEW
    assert "background:color-mix(in srgb,var(--warn,#f5821f) 14%,transparent);color:var(--warn,#f5821f)" in PREVIEW


def test_price_status_gate():
    # needs_check 가격은 '핵심 판독'으로 안 침(정직 — 가짜 성공 방지).
    assert "_EXTRA.price_status !== 'needs_check'" in PREVIEW


def test_both_paths_offer_manual_add():
    # 두 경우 모두 '+ 옵션 추가' 직접 입력 유도(막다른 길 없음).
    assert PREVIEW.count("+ 옵션 추가") >= 2


def test_preview_page_renders(flask_client):
    # 편집 페이지(드로어 임베드) 렌더 200 — 템플릿 문법 오류 없음.
    r = flask_client.get("/seller/collect/preview/nonexistent-xyz?drawer=1")
    assert r.status_code == 200   # 미존재는 '수집 실패' 빈 상태(v39 F), 404 아님
