"""tests/test_v64_history_ui.py — v64 STEP7: 수집 이력 UI 정돈(밀도·위계·배지 색 남용 축소).

gogabridj-design: 제목 1줄 말줄임·도메인 칩·가격 우정렬·상태 배지 1개(의미 토큰만).
부트스트랩 색 남용(bg-primary/warning/info) 제거. 폰트·브랜드 토큰 변경 금지 — 배치·밀도만.
"""
from __future__ import annotations

import re
from pathlib import Path

ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
HTML = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
# ★ Stage 6-c(2026-09-03): 이 화면들의 색·치수가 인라인 → **app.css로 이관**됐다.
#   핀이 보는 건 "그 규칙이 살아 있나"이지 "어느 파일에 있나"가 아니다 — 소스만 갈아끼운다.
# 6-k: 주석을 **걷어내고** 읽는다. 이 계약들은 클래스 이름으로 `split()`하는데,
#   app.css 주석이 그 이름을 먼저 언급하면 split이 **설명문에 꽂힌다**(실제로 그렇게 깨졌다).
#   선언만 보는 게 맞다 — 주석은 화면에 안 나온다.
CSS_S6C = re.sub(r"/\*.*?\*/", "", Path("src/static/app.css").read_text(encoding="utf-8"), flags=re.S)



def test_no_bootstrap_color_badges_in_rows():
    # 경로/상태의 부트스트랩 색 배지(파랑/노랑/청록/초록/빨강 채움) 제거 → 토큰만.
    for cls in ["badge bg-primary", "badge bg-warning", "badge bg-info", "badge bg-success", "badge bg-danger", "badge bg-secondary"]:
        assert cls not in ROWS + CSS_S6C, f"부트스트랩 색 배지 잔존: {cls}"


def test_price_right_aligned():
    # Y12-A: 목록 줄에서 가격은 드로어로 — 남은 가격 표(엑셀 가져오기 미리보기)는 헤더·셀 둘 다 우정렬
    assert '<th class="text-end">가격</th>' in HTML and '<td class="text-end">${_esc(p.price)}</td>' in HTML


def test_domain_is_token_chip():
    # Y12-A(오너 결정): 목록 한 줄 = 썸네일·상품명·뱃지·시각 — 도메인 칩은 줄에서 빠졌다(드로어 맨 위)
    assert "ch-url-pill" not in ROWS and "it.domain" not in ROWS


def test_source_single_neutral_chip():
    # Y12-A: 경로 칩도 줄에서 빠졌다(드로어)
    assert "ch-badge-src" not in ROWS and "it.source" not in ROWS


def test_status_badges_use_tokens():
    # Y12-A: 줄의 상태 = 마켓 뱃지 모양(완료 채움·대기 테두리·반려/실패 글자) — 색은 토큰만
    for kind, tok in (("done", "var(--success)"), ("wait", "var(--text-muted)"), ("bad", "var(--danger)"), ("fail", "var(--orange)")):
        assert tok in CSS_S6C.split(f".mk-badge.kind-{kind}")[1][:200], kind


def test_title_truncate_preserved():
    # 제목 1줄 말줄임 — 표 문법(td.cardcell-title) 한 곳에서(슬라이스가 다시 정하지 않는다)
    assert 'class="cardcell-title ch-cell-title ch-c-title"' in ROWS
    assert "text-overflow: ellipsis" in CSS_S6C.split(".pc-swiss-table > tbody > tr > td.cardcell-title")[1][:200]


def test_history_page_renders(flask_client, monkeypatch):
    # 렌더 200(템플릿 문법 오류 없음). 인증 우회는 conftest(SELLER_CONSOLE_AUTH=0).
    r = flask_client.get("/seller/collect/history")
    assert r.status_code == 200
