"""tests/test_v36_pwa_install.py — v36 PART B: PWA 설치형(콘솔 어디서나 설치)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("src/seller_console/static/manifest.webmanifest").read_text(encoding="utf-8"))
MANIFEST_JSON = json.loads(Path("src/seller_console/static/manifest.json").read_text(encoding="utf-8"))
SW = Path("src/seller_console/static/sw.js").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_manifest_installable_criteria():
    assert MANIFEST["name"] == "gogabridj"
    assert MANIFEST["display"] == "standalone"
    assert MANIFEST["start_url"] == "/seller/dashboard"          # 설치 앱은 전체 콘솔로 시작
    assert MANIFEST["orientation"].startswith("portrait")
    sizes = {i["sizes"] for i in MANIFEST["icons"]}
    assert "192x192" in sizes and "512x512" in sizes             # 브릿지 아이콘 192/512
    assert MANIFEST["background_color"] == "#1a1714"             # 먹 splash
    # 두 매니페스트 파일 동기화
    assert MANIFEST_JSON["start_url"] == MANIFEST["start_url"]


def test_console_wide_install_affordance():
    # 콘솔 드로어에 설치 버튼 + JS(beforeinstallprompt) + iOS 안내
    assert 'id="pwaInstallBtn"' in BASE
    assert "홈 화면에 앱 설치" in BASE
    assert "beforeinstallprompt" in BASE
    assert "window.pwaInstall" in BASE
    assert 'id="pwaIosHint"' in BASE


def test_service_worker_and_manifest_served(client):
    r = client.get("/seller/static/manifest.webmanifest")
    assert r.status_code == 200
    assert client.get("/seller/static/sw.js").status_code == 200
    assert client.get("/seller/static/icon-192.png").status_code == 200
    assert client.get("/seller/static/icon-512.png").status_code == 200
    # 캐시 버전 갱신(클라 SW 새로고침)
    assert "goga-bridj-v36" in SW


def test_dashboard_links_manifest_and_registers_sw(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "manifest.webmanifest" in html
    assert "serviceWorker" in html
