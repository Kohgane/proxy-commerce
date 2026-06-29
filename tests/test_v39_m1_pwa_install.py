"""tests/test_v39_m1_pwa_install.py — v39-M M1: 설치형 PWA 실동작.

manifest name '고가브릿지' · theme #1A1714 · bg #F5EFE3 · 브릿지 아이콘 192/512 maskable ·
standalone · beforeinstallprompt 연결 · iOS apple-mobile-web-app 메타 · SW 앱셸 + 정직 오프라인.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

STATIC = Path("src/seller_console/static")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
SW = (STATIC / "sw.js").read_text(encoding="utf-8")


def _manifest(fn):
    return json.loads((STATIC / fn).read_text(encoding="utf-8"))


@pytest.mark.parametrize("fn", ["manifest.json", "manifest.webmanifest"])
def test_manifest_name_korean_and_colors(fn):
    m = _manifest(fn)
    assert m["name"] == "고가브릿지"
    assert m["short_name"] == "고가브릿지"
    assert m["theme_color"] == "#1a1714"
    assert m["background_color"] == "#f5efe3"
    assert m["display"] == "standalone"


@pytest.mark.parametrize("fn", ["manifest.json", "manifest.webmanifest"])
def test_manifest_maskable_icons(fn):
    m = _manifest(fn)
    sizes = {i["sizes"]: i for i in m["icons"]}
    assert "192x192" in sizes and "512x512" in sizes
    for s in ("192x192", "512x512"):
        assert "maskable" in sizes[s]["purpose"]


def test_install_button_and_beforeinstallprompt_wired():
    assert "pwaInstallBtn" in BASE and "홈 화면에 앱 설치" in BASE
    assert "beforeinstallprompt" in BASE
    assert "deferred['prompt']()" in BASE


def test_ios_apple_meta_present():
    assert 'name="apple-mobile-web-app-capable"' in BASE
    assert 'name="apple-mobile-web-app-title" content="고가브릿지"' in BASE
    assert "apple-touch-icon" in BASE


def test_sw_appshell_only_no_dynamic_cache_honest_offline():
    assert "gogabridj-v39" in SW
    # 앱셸 캐시 목록(STATIC_ASSETS)에 동적 데이터 페이지가 들어가지 않아야 함(스테일 가짜 데이터 방지)
    shell = SW.split("STATIC_ASSETS", 1)[1].split("]", 1)[0]
    assert "/seller/dashboard" not in shell
    assert "/seller/orders" not in shell
    # 오프라인 폴백 = 정직 오프라인 페이지(대시보드 캐시 아님)
    assert "OFFLINE_FALLBACK = '/seller/static/offline.html'" in SW
    # 네비게이션은 네트워크 우선 + 오프라인 폴백
    assert "navigate" in SW


def test_offline_page_is_honest_no_fake_data():
    off = (STATIC / "offline.html").read_text(encoding="utf-8")
    assert "오프라인" in off
    assert "저장된 데이터는 보여드리지 않아요" in off   # 가짜/스테일 데이터 미노출 명시


def test_offline_page_served():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        r = c.get("/seller/static/offline.html")
        assert r.status_code == 200
