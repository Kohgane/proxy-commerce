"""tests/test_extension_install.py — 크롬 확장 설치 가이드/다운로드 + PWA 공유 수집."""
from __future__ import annotations

import io
import os
import sys
import zipfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_extension_guide_page(client):
    r = client.get("/seller/extension")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "압축해제된" in html
    assert "chrome://extensions" in html
    assert "/seller/extension/download" in html


def test_extension_download_zip(client):
    r = client.get("/seller/extension/download")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/zip"
    assert ".zip" in r.headers.get("Content-Disposition", "")
    z = zipfile.ZipFile(io.BytesIO(r.data))
    names = z.namelist()
    for need in ("manifest.json", "content_script.js",
                 "background.js"):
        assert need in names
    assert any(n.startswith("icons/") for n in names)
    assert z.testzip() is None


def test_pwa_manifest_has_share_target():
    import json
    with open("src/seller_console/static/manifest.webmanifest", encoding="utf-8") as f:
        m = json.load(f)
    st = m.get("share_target")
    assert st and st["action"] == "/seller/collect/share"   # v39-M M2: 공유→수집→편집 드로어
    assert st["params"]["url"] == "u"


def test_quick_collect_accepts_shared_text_url(client):
    """모바일 공유(share_target)가 text에 URL을 담아 보내도 수집된다."""
    draft = {"title_ko": "t", "title": "t", "images": ["https://i/1.jpg"],
             "price_original": "10", "currency": "USD", "source": "x"}
    with patch("src.seller_console.views._collect_real_draft", return_value=draft), \
         patch("src.seller_console.collect_history_store.append", return_value="qid"):
        r = client.get("/seller/collect/quick?text=" + "good%20https://shop.example/p/1%20deal")
    assert r.status_code == 200
    assert "수집 완료" in r.get_data(as_text=True)
