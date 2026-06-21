"""tests/test_no_dead_buttons.py — 죽은 버튼/링크 가드 (Phase 260, v6 P0).

오너 v6 P0: "클릭 가능한 모든 것이 실제로 무언가를 한다. 죽은 버튼 0."
주요 화면을 렌더 → 내부 링크(href)를 추출 → 각 링크가 404/500이 아님을 보장(회귀 가드, CI 포함).
"""
from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 크롤 시작점(셀러 핵심 화면 + 풀스크린 진입)
SEED_PAGES = [
    "/seller/dashboard",
    "/seller/collect/history",
    "/seller/markets",
    "/seller/markets/connect",
    "/seller/billing",
    "/seller/about",
    "/seller/start",
    "/seller/guide/business",
    "/seller/m",
]

# 내부 링크 패턴(앵커·동적 라우트 제외용)
_HREF_RE = re.compile(r'href="(/[^"#?]*)"')
# 동적/외부/특수 경로는 가드에서 제외(파라미터 필요 등)
_SKIP_PREFIXES = ("/seller/collect/preview/", "/seller/static/", "/static/", "/auth/logout")


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _internal_links(html):
    links = set()
    for href in _HREF_RE.findall(html):
        if any(href.startswith(p) for p in _SKIP_PREFIXES):
            continue
        if href.startswith("/seller/") or href in ("/privacy", "/terms"):
            links.add(href)
    return links


def test_seed_pages_render(client):
    for path in SEED_PAGES:
        resp = client.get(path)
        assert resp.status_code in (200, 302), f"{path} → {resp.status_code}"


def test_no_dead_internal_links(client):
    """시드 페이지의 모든 내부 링크가 404/500이 아님(죽은 링크 0)."""
    seen = set()
    dead = []
    for path in SEED_PAGES:
        resp = client.get(path)
        if resp.status_code != 200:
            continue
        for link in _internal_links(resp.get_data(as_text=True)):
            if link in seen:
                continue
            seen.add(link)
            r = client.get(link)
            # 404(없는 라우트)·500(서버오류)만 실패로 간주. 200/302/400/401/405는 정상.
            if r.status_code in (404, 500):
                dead.append(f"{link} → {r.status_code} (on {path})")
    assert not dead, "죽은 링크 발견:\n" + "\n".join(dead)


def test_no_empty_anchor_without_handler(client):
    """href='#' 인데 onclick(핸들러)도 없는 죽은 앵커가 핵심 페이지에 없어야 한다."""
    bad = []
    for path in SEED_PAGES:
        resp = client.get(path)
        if resp.status_code != 200:
            continue
        html = resp.get_data(as_text=True)
        # href="#" 직후 같은 태그에 onclick/data-bs-* 가 없으면 의심
        for m in re.finditer(r'<a[^>]*href="#"[^>]*>', html):
            tag = m.group(0)
            if "onclick=" not in tag and "data-bs-" not in tag and "data-act" not in tag:
                bad.append(f"{path}: {tag[:80]}")
    assert not bad, "핸들러 없는 빈 앵커:\n" + "\n".join(bad)
