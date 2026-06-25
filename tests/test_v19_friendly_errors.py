"""tests/test_v19_friendly_errors.py — v19: 친절한 오류 안내 공통 처리기 + 지구본 박멸(글러브 단일 아이콘)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SELLER_JS = Path("src/seller_console/static/seller.js").read_text(encoding="utf-8")


def test_friendly_error_helpers_present():
    for fn in ("function kgpFriendlyError", "function kgpInlineError", "function kgpEscapeForHtml"):
        assert fn in SELLER_JS, f"{fn} 누락"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_friendly_error_mapping_runs():
    # 실제 매핑 동작 검증(개발 메시지 가림 + 코드→쉬운 문장)
    body = SELLER_JS[SELLER_JS.index("function kgpFriendlyError"):]
    body = body[: body.index("\nfunction kgpInlineError")]
    cases = {
        "Cannot read properties of undefined (reading 'x')": "문제가 생겼",
        "undefined": "문제가 생겼",
        "COUPANG_ACCESS_KEY 미설정": "마켓 연동",
        "Failed to fetch": "인터넷 연결",
        "가격이 0입니다": "가격을 못",
        "HTTP 500 Internal Server Error": "문제가 생겼",
        "<!doctype html><html>boom": "문제가 생겼",
    }
    script = body + "\nconst I=" + json.dumps(list(cases.keys()), ensure_ascii=False) + \
        ";console.log(JSON.stringify(I.map(kgpFriendlyError)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    results = json.loads(out.stdout.strip())
    for (raw, expect), got in zip(cases.items(), results):
        assert expect in got, f"{raw!r} → {got!r} (기대 포함: {expect})"
        # 개발 토큰이 화면 문구에 새지 않아야 함
        for leak in ("undefined", "Traceback", "<!doctype", "HTTP 500", "COUPANG_ACCESS_KEY"):
            assert leak not in got


def test_key_flows_use_friendly_handler():
    for tpl in ("manual_collect", "collect_preview", "markets_connect"):
        s = Path(f"src/seller_console/templates/{tpl}.html").read_text(encoding="utf-8")
        assert "kgpFriendlyError" in s or "kgpInlineError" in s, f"{tpl} 친절 핸들러 미적용"
        # 날것 메시지 노출 금지(err.message/data.error를 토스트/알림에 직접)
        assert "+ err.message" not in s, f"{tpl}에 raw err.message 노출 잔존"


# ---- P0-2: 지구본 박멸 — v21 게이트웨이(B) 단일 아이콘 ----
def test_favicon_is_gateway_not_globe():
    low = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8").lower()
    # v23 마스터(브릿지+게이트웨이) 래스터 임베드
    assert "gateway" in low or "bridge" in low
    assert "data:image/png;base64," in low
    # 지구본(globe) 마크업 없음
    assert "<title>지구본" not in low
    assert "globe" not in low


def test_extension_uses_glove_icon():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "KGP_GLOVE_SVG" in cs
    mf = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
    assert mf["icons"]["128"].endswith(".png")        # 코고가네 아이콘 PNG 단독


def test_no_globe_in_head_icon_declarations():
    for p in ("src/seller_console/templates/_base.html", "src/templates/_base_app.html"):
        s = Path(p).read_text(encoding="utf-8")
        # head의 아이콘 선언에 globe/지구본 잔재 없음
        assert "globe" not in s.lower().split("</head>")[0]
