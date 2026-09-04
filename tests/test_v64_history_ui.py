"""tests/test_v64_history_ui.py — v64 STEP7: 수집 이력 UI 정돈(밀도·위계·배지 색 남용 축소).

gogabridj-design: 제목 1줄 말줄임·도메인 칩·가격 우정렬·상태 배지 1개(의미 토큰만).
부트스트랩 색 남용(bg-primary/warning/info) 제거. 폰트·브랜드 토큰 변경 금지 — 배치·밀도만.
"""
from __future__ import annotations

from pathlib import Path

ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
HTML = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
# ★ Stage 6-c(2026-09-03): 이 화면들의 색·치수가 인라인 → **app.css로 이관**됐다.
#   핀이 보는 건 "그 규칙이 살아 있나"이지 "어느 파일에 있나"가 아니다 — 소스만 갈아끼운다.
CSS_S6C = Path("src/static/app.css").read_text(encoding="utf-8")



def test_no_bootstrap_color_badges_in_rows():
    # 경로/상태의 부트스트랩 색 배지(파랑/노랑/청록/초록/빨강 채움) 제거 → 토큰만.
    for cls in ["badge bg-primary", "badge bg-warning", "badge bg-info", "badge bg-success", "badge bg-danger", "badge bg-secondary"]:
        assert cls not in ROWS + CSS_S6C, f"부트스트랩 색 배지 잔존: {cls}"


def test_price_right_aligned():
    assert 'class="small text-end" data-label="가격"' in ROWS + CSS_S6C   # 가격 셀 우정렬
    assert '<th class="text-end">가격</th>' in HTML              # 헤더 우정렬


def test_domain_is_token_chip():
    # 도메인 = 토큰 칩(한지 배경·line 보더), 평문 muted 아님.
    assert "ch-url-pill" in ROWS                       # 6-c: 인라인 → 클래스
    pill = CSS_S6C.split(".ch-url-pill")[1][:260]
    assert "var(--hanji)" in pill and "var(--border)" in pill and "var(--text-muted)" in pill


def test_source_single_neutral_chip():
    # 경로 = 단일 중립 칩(맵으로 라벨), 5색 배지 아님.
    assert "{'extension':'확장'" in ROWS + CSS_S6C or "'extension':'확장'" in ROWS + CSS_S6C
    assert "ch-badge-src" in ROWS                      # 6-c: 인라인 → 클래스
    assert "var(--ink-soft)" in CSS_S6C.split(".ch-badge-src")[1][:200]


def test_status_badges_use_tokens():
    # 상태: 성공=teal·부분=warn·실패=danger·보관=muted 토큰(색 남용 없음, 행당 1개).
    assert "var(--teal)" in ROWS and "var(--warn)" in ROWS and "var(--danger)" in ROWS


def test_title_truncate_preserved():
    assert "text-truncate" in ROWS + CSS_S6C   # 제목 1줄 말줄임 유지


def test_history_page_renders(flask_client, monkeypatch):
    # 렌더 200(템플릿 문법 오류 없음). 인증 우회는 conftest(SELLER_CONSOLE_AUTH=0).
    r = flask_client.get("/seller/collect/history")
    assert r.status_code == 200
