"""tests/test_v38_brand_gogabridj.py — v38: 영문 표기 'gogabridj' 동시반영(띄어쓴 옛 표기 0)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def test_brand_en_default_lowercase_nospace():
    from src.utils.branding import get_brand_name
    assert get_brand_name() == "gogabridj"


def test_no_spaced_english_brand_in_source():
    # 사용자 노출 영문 표기에 'Goga Bridj'·'GOGA BRIDJ'(띄어쓴 옛 표기) 잔존 0 (소스 전수, tests 제외)
    res = subprocess.run(
        ["grep", "-rIn", "-e", "Goga Bridj", "-e", "GOGA BRIDJ", "src/", "extensions/"],
        capture_output=True, text=True,
    )
    assert res.stdout.strip() == "", f"띄어쓴 영문 표기 잔존:\n{res.stdout}"


def test_manifest_name_is_gogabridj():
    for fn in ("manifest.json", "manifest.webmanifest"):
        m = json.loads(Path(f"src/seller_console/static/{fn}").read_text(encoding="utf-8"))
        assert m["name"] == "gogabridj", fn


def test_console_sidebar_shows_gogabridj():
    import os
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        html = c.get("/seller/dashboard").get_data(as_text=True)
    assert "gogabridj" in html
    assert "Goga Bridj" not in html and "GOGA BRIDJ" not in html
