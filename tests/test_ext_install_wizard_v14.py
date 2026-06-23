"""tests/test_ext_install_wizard_v14.py — v14 확장 설치 단계화 + 복사 동작 + 퍼센티 제거 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

EXT = Path("src/seller_console/templates/extension_install.html").read_text(encoding="utf-8")


def test_install_is_stepwise_one_button():
    assert "STEPS" in EXT and "extPrimary" in EXT          # 단계별 + 단계당 버튼 1개
    assert "extPrev" in EXT and "extNext" in EXT           # 이전/다음
    assert "extProgressBar" in EXT                         # 진행 표시


def test_copy_button_real_clipboard():
    assert "navigator.clipboard.writeText" in EXT
    assert 'act === "copy"' in EXT and "pcToast" in EXT    # 복사 후 실제 피드백


def test_no_percenty_in_user_templates():
    tpl_dir = Path("src/seller_console/templates")
    for p in tpl_dir.glob("*.html"):
        assert "퍼센티" not in p.read_text(encoding="utf-8"), f"{p.name}에 '퍼센티' 노출 잔존"


def test_no_dev_endpoint_note():
    mc = Path("src/seller_console/templates/manual_collect.html").read_text(encoding="utf-8")
    assert "기존 수집기 엔드포인트" not in mc                # 개발 노트 제거


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_extension_page_renders(client):
    html = client.get("/seller/extension").get_data(as_text=True)
    assert "설치 단계" in html and "압축해제된" in html and "chrome://extensions" in html
