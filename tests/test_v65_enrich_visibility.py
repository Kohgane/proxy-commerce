"""tests/test_v65_enrich_visibility.py — v65 STEP4: 보강 큐 가시성.

v64 STEP1 큐 UI(팝업 n/총·일시정지·중단) 배포 감사 + 수집 이력 행에 '보강 중…' 스피너 상태
(대기/완료) 추가. 정직: 실제 저장값(enriched) 기준, 단건은 배지 없음(보강 불필요).
"""
from __future__ import annotations

import json
from pathlib import Path

POPUP_JS = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
POPUP_HTML = Path("extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
# ★ Stage 6-c(2026-09-03): 이 화면들의 색·치수가 인라인 → **app.css로 이관**됐다.
#   핀이 보는 건 "그 규칙이 살아 있나"이지 "어느 파일에 있나"가 아니다 — 소스만 갈아끼운다.
CSS_S6C = Path("src/static/app.css").read_text(encoding="utf-8")

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


def test_queue_ui_deployed_audit():
    # v64 STEP1 큐 UI가 실제 배포돼 있는지 감사(팝업 진행률·일시정지·중단).
    assert 'id="enrichPanel"' in POPUP_HTML and 'id="enrichCount"' in POPUP_HTML
    assert 'id="enrichPause"' in POPUP_HTML and 'id="enrichStop"' in POPUP_HTML
    assert "enrichProgress" in POPUP_JS and "enrichState" in POPUP_JS
    # 배경 큐가 진행률 방송 + 일시정지/중단 처리.
    assert "_kgpBroadcastEnrich" in BG
    assert 'msg.action === "enrichPause"' in BG and 'msg.action === "enrichStop"' in BG


def test_row_enrich_status_derivation():
    # 뷰가 enrich_status를 실제 저장값(enriched)+source로 파생.
    assert 'it["enrich_status"] = "done" if _enriched else ("pending" if _pending else "")' in VIEWS
    assert '_enriched = bool(ex.get("enriched"))' in VIEWS


def test_row_enrich_badges():
    # 행 템플릿: 대기=스피너 '보강 중…', 완료='보강 완료'(토큰), 단건은 배지 없음.
    assert 'it.enrich_status == "pending"' in ROWS + CSS_S6C
    assert "보강 중…" in ROWS + CSS_S6C and "spinner-border" in ROWS + CSS_S6C
    assert 'it.enrich_status == "done"' in ROWS + CSS_S6C and "보강 완료" in ROWS + CSS_S6C
    # 토큰 색(청록/한지) — 부트스트랩 색 남용 아님.
    assert "var(--teal)" in ROWS and "kgp-badge-quiet" in ROWS   # 6-c: 한지 칩 → 클래스
    assert "var(--hanji)" in CSS_S6C.split(".kgp-badge-quiet")[1][:160]


def test_enrich_status_values():
    # 파생 규칙: 단건(source=extension)·성공은 배지 없음; 벌크+부분은 pending; enriched=done.
    # (규칙 문자열이 뷰에 존재하는지로 계약 고정 — 런타임은 test_v64_bulk_enrich가 enriched 저장 검증)
    assert 'in ("bulk", "bulk_collect")' in VIEWS
    assert 'cs.get("status") != "성공"' in VIEWS


def test_history_page_renders(flask_client):
    r = flask_client.get("/seller/collect/history")
    assert r.status_code == 200
