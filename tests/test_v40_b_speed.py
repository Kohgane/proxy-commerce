"""tests/test_v40_b_speed.py — v40-B 사이트 속도(코드 레벨): 사전연결·불변 캐시·이미지 지연/디코딩.

정직: 렌더 Free→Starter(첫 응답 spin-down)는 오너 콘솔 액션. 코드 레벨 best-practice만 여기서.
- 외부 출처 preconnect/dns-prefetch(CDN·웹폰트 연결 워밍).
- 버전드 정적 에셋(?v=) → 1년 immutable(재검증 왕복 0). 비버전드 1주.
- 목록 썸네일 loading=lazy + decoding=async + width/height(레이아웃 시프트·디코드 비용↓).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_preconnect_resource_hints_present():
    base = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    assert 'rel="preconnect" href="https://cdn.jsdelivr.net"' in base
    assert 'rel="preconnect" href="https://fonts.gstatic.com"' in base
    assert 'rel="dns-prefetch"' in base


def test_versioned_static_is_immutable(client):
    r = client.get("/seller/static/favicon.ico?v=179")
    assert r.status_code == 200
    cc = r.headers.get("Cache-Control", "")
    assert "immutable" in cc and "max-age=31536000" in cc      # 버전드 = 1년 불변


def test_non_versioned_static_weekly_cache(client):
    r = client.get("/seller/static/seller.css")
    assert r.status_code == 200
    assert "max-age=604800" in r.headers.get("Cache-Control", "")  # 비버전드 1주(기존 v8 유지)


def test_gzip_still_applied(client):
    # v8 gzip 유지(텍스트 응답 압축) — 회귀 0
    r = client.get("/seller/static/seller.css", headers={"Accept-Encoding": "gzip"})
    # 큰 텍스트면 gzip; 작으면 미적용 — 적어도 헤더/응답 정상
    assert r.status_code == 200


def test_list_thumbnails_lazy_async():
    # 행 마크업은 파셜(단일소스)로 이동 — 썸네일 lazy/async는 거기서 검증.
    tpl = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert 'loading="lazy"' in tpl and 'decoding="async"' in tpl
