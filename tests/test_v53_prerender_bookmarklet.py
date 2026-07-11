"""tests/test_v53_prerender_bookmarklet.py — v53 STEP3(초가속)+STEP4(북마클릿 시인성).

STEP3: Speculation Rules(prefetch·moderate·로그아웃/삭제 제외) + View Transitions(startViewTransition +
@view-transition) + 드로어 hover 선행 로드(동시1). STEP4: 아이콘 부재 안내 + 기본 이름 ⚡고가수집.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
APPCSS = Path("src/static/app.css").read_text(encoding="utf-8")
HIST = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
BM = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")


# ── STEP3 ─────────────────────────────────────────────────────
def test_speculation_rules_present_and_safe():
    m = re.search(r'<script type="speculationrules">\s*(\{.*?\})\s*</script>', BASE, re.S)
    assert m, "speculationrules 스크립트 없음"
    rules = json.loads(m.group(1))
    assert "prefetch" in rules                      # prefetch(문서, JS 미실행 — 스왑 엔진 캐시 워밍)
    rule = rules["prefetch"][0]
    assert rule["eagerness"] == "moderate"
    blob = json.dumps(rule)
    assert "logout" in blob and "delete" in blob    # 로그아웃·삭제(파괴적) 제외


def test_view_transitions_wired():
    assert "document.startViewTransition" in BASE   # 스왑 엔진에 적용
    assert "@view-transition" in APPCSS and "navigation: auto" in APPCSS
    assert "prefers-reduced-motion" in APPCSS and "view-transition-group" in APPCSS  # RM 정지


def test_drawer_hover_preload():
    assert "X-KGP-Prefetch" in HIST and "warm=1" in HIST
    assert "kgp-open-drawer[data-id]" in HIST
    assert "inflight" in HIST                        # 동시 1건 제한


def test_drawer_warm_endpoint_ok():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        r = c.get("/seller/collect/preview/none?drawer=1&warm=1")
        assert r.status_code == 200                  # warm 파라미터 무해(200)


# ── STEP4 ─────────────────────────────────────────────────────
def test_bookmarklet_icon_notice_and_name():
    assert "아이콘이 표시되지 않습니다" in BM        # 아이콘 부재 명시
    assert "파일" in BM and "가져오기" in BM         # 파일 방식 유도
    assert "⚡고가수집" in BM                         # 복사 방식 기본 이름 ⚡ 접두


def test_page_renders():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        assert c.get("/seller/bookmarklet").status_code == 200
        assert c.get("/seller/dashboard").status_code == 200
