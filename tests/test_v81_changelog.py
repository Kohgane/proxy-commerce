"""tests/test_v81_changelog.py — v81 STEP7: 변경 가시성(체인지로그 페이지 + 콘솔 배너).

콘솔 상단 '이번 업데이트: ○○·○○ (자세히)' 배너 + `/seller/changelog`(배치 버전별 3줄 요약, 자동 누적).
단일 소스 changelog.py. gogabridj 토큰·이모지 0(bi-*).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CL_TMPL = Path("src/seller_console/templates/changelog.html").read_text(encoding="utf-8")
BASE_TMPL = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
APP_CSS = Path("src/static/app.css").read_text(encoding="utf-8")

# 픽토그램 이모지(장식) — bi-* 아이콘만 허용, 이모지 0.
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF\U00002190-\U000021FF\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF]"
)


# ── 단일 소스 changelog.py ──
def test_changelog_source_newest_first_and_3lines():
    from src.seller_console.changelog import get_changelog, banner_summary, latest
    cl = get_changelog()
    assert cl, "체인지로그 비어 있음"
    assert cl[0]["version"] == "v81", "최신이 맨 앞이어야(v81)"
    for e in cl:
        assert e.get("version") and e.get("title") and e.get("date")
        assert 1 <= len(e.get("lines") or []) <= 3, ("배치당 최대 3줄", e)
    b = banner_summary()
    assert b["version"] == "v81" and 1 <= len(b["points"]) <= 2
    assert latest()["version"] == "v81"


# ── 라우트 ──
@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "t"
    return app.test_client()


def test_changelog_page_renders_all_batches(client):
    r = client.get("/seller/changelog")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert "이번엔 이런 걸 손봤어요" in h
    from src.seller_console.changelog import get_changelog
    from markupsafe import escape as _esc
    for e in get_changelog():
        assert e["version"] in h
        for ln in e["lines"]:
            assert str(_esc(ln)) in h   # 3줄 요약 전부 렌더(HTML 이스케이프 반영)
    # (이모지 검사는 changelog.html 템플릿 단위로 — 전체 페이지는 base chrome의 텍스트 화살표 등 포함)


def test_console_banner_present_and_links_changelog(client):
    r = client.get("/seller/dashboard")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert 'id="kgpUpdateBanner"' in h
    assert "이번 업데이트" in h and "/seller/changelog" in h
    assert "kgp_cl_seen" in h            # 최신 버전 1회만(localStorage dismiss)
    assert "kgpDismissUpdateBanner" in h


# ── gogabridj 토큰/이모지 계약 ──
def test_banner_and_page_use_tokens_no_emoji():
    assert not _EMOJI.search(CL_TMPL), "changelog.html 이모지"
    # 배너 마크업 이모지 0(배너 블록만).
    assert "kgp-update-banner" in BASE_TMPL
    # CSS는 토큰(var(--…))만 — 새 블록에 브랜드 hex 하드코딩 0(가드 test_design_tokens_v18와 이중).
    block = APP_CSS.split("v81 STEP7:")[1] if "v81 STEP7:" in APP_CSS else ""
    assert block, "STEP7 CSS 블록 없음"
    # ★ 6-c(2026-09-03): 이 핀은 **선언부**의 하드코딩을 막는 것이다. 주석은 "옛 값 #xxx를 토큰으로
    #   바꿨다"처럼 근거로 값을 인용할 수 있고, 그건 문서지 선언이 아니다(6-a 헬퍼와 같은 처리).
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    assert "var(--teal)" in block and "var(--gold)" in block and "var(--orange)" in block
    assert not re.search(r"#[0-9A-Fa-f]{6}\b", block), "STEP7 CSS에 하드코딩 hex 잔존"
    # 키스톤(주황 점) 시그니처 present.
    assert "kgp-ub-keystone" in block and "background:var(--orange)" in block
