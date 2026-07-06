"""tests/test_v45_drawer_boundary.py — 드로어 백지 방지(렌더 실패 시 '불러오기 실패+재시도').

증상(오너 캡처): 수집이력 상품 클릭 → 드로어 iframe 완전 공백 렌더(Yoshida SHOULDER PACK).
수리: iframe(편집 페이지)이 렌더되면 부모에 postMessage{kgp:'preview-ready'} 핸드셰이크.
부모는 워치독 시간 내 신호가 없거나(백지·XFO차단·네트워크) onload 후 본문이 비면 '불러오기 실패 +
다시 시도' 오버레이를 띄운다(백지 금지). 정상 렌더는 오버레이 숨김.
"""
from __future__ import annotations

from pathlib import Path

HIST = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
PREV = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
MISS = Path("src/seller_console/templates/collect_preview_missing.html").read_text(encoding="utf-8")


def test_iframe_sends_ready_handshake():
    # 편집 페이지가 렌더되면 부모에 준비 신호 — 초기화 예외에도 정적 폼은 살고 신호는 보낸다.
    assert "preview-ready" in PREV
    assert "window.parent.postMessage" in PREV
    assert "_kgpSignalReady" in PREV
    # 초기화 예외를 삼켜 백지가 아니라 폼이 남게 함
    assert "초기화 오류" in PREV and "try { initEditor(); }" in PREV
    # '수집 실패' 빈 상태(정상 렌더)도 신호를 보내 오탐(거짓 실패) 방지
    assert "preview-ready" in MISS


def test_parent_watchdog_and_fail_overlay():
    # 워치독 타이머 + 준비 신호 수신 시 해제
    assert "_kgpDrawerWatch" in HIST and "_kgpDrawerReady" in HIST
    assert "'preview-ready'" in HIST or '"preview-ready"' in HIST
    assert "_KGP_DRAWER_TIMEOUT" in HIST
    # 실패 오버레이 마크업 + 재시도 + 새 탭 폴백(백지 금지)
    assert 'id="kgpDrawerFail"' in HIST
    assert "불러오기" in HIST and "다시 시도" in HIST
    assert "retryItemDrawer" in HIST
    assert 'id="kgpDrawerFailOpen"' in HIST


def test_onload_fallback_for_blocked_frame():
    # postMessage가 아예 안 오는 경우(XFO 차단 등) onload 후 본문 접근 실패 → 즉시 실패 표기
    assert "addEventListener('load'" in HIST
    assert "contentDocument" in HIST
    assert "showDrawerFail" in HIST


def test_retry_reloads_frame_with_cachebust():
    # 재시도는 캐시/SW stale 대비 캐시버스트로 재로딩
    assert "_kgpDrawerLoadFrame" in HIST
    assert "?drawer=1&t=" in HIST
