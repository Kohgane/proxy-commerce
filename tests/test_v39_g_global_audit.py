"""tests/test_v39_g_global_audit.py — v39 G: 전수 점검(CI 게이트). 같은 유형 결함을 전 화면에서 잡는다.

(a) 죽은 버튼  (b) 가짜 성공  (c) 새 창 이탈  (d) 원문 미번역  (e) 아이콘/globe 잔재
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

HIST = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
BM = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
EXT_CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
EXT_API = Path("src/api/extension_api.py").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


# (a) 죽은 버튼 — 핵심 화면 200 + href="#" 인데 핸들러 없는 빈 앵커 0
def test_a_core_pages_and_no_dead_anchors(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"; s["user_role"] = "admin"
    for path in ("/seller/dashboard", "/seller/collect/history", "/seller/orders",
                 "/seller/markets", "/seller/catalog", "/seller/me/tokens", "/seller/bookmarklet"):
        resp = client.get(path, follow_redirects=True)
        assert resp.status_code == 200, path
        for tag in re.findall(r'<a[^>]*href="#"[^>]*>', resp.get_data(as_text=True)):
            assert "onclick=" in tag or "data-bs-" in tag or "data-act" in tag, f"{path}: 죽은 앵커 {tag[:70]}"


# (b) 가짜 성공 — 수집은 영속 저장(durable) 확인 후에만 ok
def test_b_collect_durable_gated():
    assert "return_durable=True" in EXT_API and "not durable" in EXT_API and "502" in EXT_API


# (c) 새 창 이탈 — 목록 클릭=드로어(원본 사이트 새 탭 0), 북마클릿 window.open 0
def test_c_no_new_window_escape():
    assert "kgp-open-drawer" in HIST
    assert 'target="_blank" rel="noopener noreferrer">{{ it.domain' not in HIST   # 도메인 원본 새 탭 0
    assert "window.open" not in BM


# (d) 원문 미번역 — 편집 페이지에 '한국어로 번역' 액션 + 키 없을 때 정직(가짜 번역 0)
def test_d_translate_action_and_honest():
    assert "한국어로 번역" in PREVIEW and "/seller/collect/bulk-translate" in PREVIEW
    assert "translated || 0) > 0" in PREVIEW          # 실제 번역된 경우에만 반영


# (e) 아이콘/globe 잔재 — favicon 브릿지, 확장 globe 0
def test_e_no_globe_residue():
    fav = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")
    assert "bridge gateway mark" in fav and "globe" not in fav.lower()
    assert "🌐" not in EXT_CS and "globe" not in EXT_CS.lower()


# (f) 수집 상세 404 박멸 — 미존재도 200 '수집 실패'
def test_f_missing_preview_not_404(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/collect/preview/zzz-missing")
    assert r.status_code == 200 and "수집 실패" in r.get_data(as_text=True)
