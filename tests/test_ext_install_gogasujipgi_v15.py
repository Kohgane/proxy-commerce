"""tests/test_ext_install_gogasujipgi_v15.py — v15 P0-3 확장 설치 '고가수집기' 친절화 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

EXT = Path("src/seller_console/templates/extension_install.html").read_text(encoding="utf-8")


def test_tool_named_gogasujipgi():
    assert "고가수집기" in EXT
    assert "gogasujipgi" in EXT          # 파일명 표기


def test_why_install_why_token_explainer():
    assert "고가수집기가 뭐예요" in EXT     # 왜 설치
    assert "토큰은 왜 넣어요" in EXT        # 왜 토큰
    assert "열쇠" in EXT                    # 비유


def test_no_endpoint_dev_note_anywhere():
    # '기존 수집기 엔드포인트를 그대로 사용합니다' 개발 문구가 어디에도 없어야 함
    import subprocess
    src = Path("src")
    for p in src.rglob("*.html"):
        assert "기존 수집기 엔드포인트" not in p.read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_download_filename_is_gogasujipgi(client):
    r = client.get("/seller/extension/download")
    assert r.status_code == 200
    assert "gogasujipgi-v" in r.headers.get("Content-Disposition", "")
    assert ".zip" in r.headers.get("Content-Disposition", "")
