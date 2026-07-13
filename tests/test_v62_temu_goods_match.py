"""tests/test_v62_temu_goods_match.py — v62 STEP2: 테무 Tier1 goods_id 정확 매칭(간헐 종결).

캡처를 goods_id 키로 보관({goods_id:{response,ts}}, 최근 10·TTL 10분). 수집 클릭 시 현재 페이지 URL의
goods_id와 정확 매칭 — 실패 시 Tier2 폴백 + 원인 토스트. **이전 상품 응답 오채택 금지.**
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

NET = Path("extensions/chrome-collector/kgp-net.js").read_text(encoding="utf-8")
EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MAIN = Path("extensions/chrome-collector/kgp-main.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_source_contract():
    # goods_id 추출 + 키드 보관 + 매칭 조회 API.
    assert "_goodsIdFromUrl" in NET and "_goodsIdFromObj" in NET
    assert "window.__kgpMatchCapture" in NET and "window.__kgpPageGoodsId" in NET
    assert "goods_id: gid" in NET and "ts: Date.now()" in NET     # 키+타임스탬프 저장
    assert "600000" in NET                                        # TTL 10분
    # 추출기: goods_id 페이지면 매칭 캡처만 채택(오채택 방지).
    assert "__kgpMatchCapture(pgid)" in EX and "__kgpTier1Mismatch = true" in EX
    # 진단·토스트: 미포착 원인 명시.
    assert "이 상품의 API 응답 미포착" in CS
    assert "diag.pageGoodsId" in MAIN and "matched" in MAIN


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_goods_id_exact_match_no_wrong_adoption():
    # kgp-net.js를 로드해 __kgpPageGoodsId/__kgpMatchCapture 동작 실증 — 내 goods_id만 채택, 다른 상품 응답 배제.
    harness = (
        "global.window={location:{href:'https://www.temu.com/kr/x-g-601099887766.html'}};"
        "global.Date={now:function(){return 5000000;}};\n"
        + NET.replace("if (window.__kgpNetBound) return;", "if(false){}") + "\n"
        "window.__kgpCaptured=["
        "{goods_id:'601099887766',ts:5000000,url:'api?goods_id=601099887766',score:4,obj:{mine:1}},"
        "{goods_id:'999888777',ts:5000000,url:'other',score:9,obj:{other:1}},"       # 점수 더 높지만 남의 상품
        "{goods_id:'601099887766',ts:4000000,url:'stale',score:2,obj:{oldmine:1}}"   # 같은 상품 구버전(오래됨)
        "];\n"
        "var pgid=window.__kgpPageGoodsId();"
        "var m=window.__kgpMatchCapture(pgid);"
        "var none=window.__kgpMatchCapture('000000');"
        "console.log(JSON.stringify({pgid:pgid, matchedObj:(m&&m.obj), noneNull:(none===null)}));"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert d["pgid"] == "601099887766"
    assert d["matchedObj"] == {"mine": 1}      # 내 goods_id 최신 응답만(남의 고점 응답·오래된 응답 배제)
    assert d["noneNull"] is True               # 매칭 없으면 null(오채택 금지)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_goods_id_from_various_url_patterns():
    a = NET.index("var GID_URL")
    b = NET.index("function _goodsIdFromObj")
    block = NET[a:b].replace("function _goodsIdFromUrl", "function gid")
    harness = block + (
        "var out={};"
        "out.dash=gid('https://www.temu.com/kr/desk-g-601099887766.html');"
        "out.query=gid('https://www.temu.com/api?goods_id=123456789');"
        "out.none=gid('https://www.temu.com/kr/search_result.html?q=desk');"
        "console.log(JSON.stringify(out));"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert d["dash"] == "601099887766" and d["query"] == "123456789" and d["none"] == ""
