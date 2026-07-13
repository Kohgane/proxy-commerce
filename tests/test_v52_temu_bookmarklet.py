"""tests/test_v52_temu_bookmarklet.py — v52 STEP3: 테무 북마클릿 Tier2 클라 추출.

북마클릿이 클릭 시점 렌더 DOM에서 소형 구조 추출을 직접 수행: h1 타이틀·메인영역 판매가(취소선 제외)·
갤러리 스코프 이미지(src+data-src+srcset 최고해상, 추천 제외, naturalWidth 필터 금지). payload 동봉+field_sources.
못 채우는 필드(리뷰·전체 sku)는 '부분 수집 — 확장 권장'(v51 규약).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


def _bm():
    from src.seller_console.views import _bookmarklet_js
    return _bookmarklet_js("https://kohganepercentiii.com", "TOK", True)


def _run():
    # v56 STEP1: Tier2 추출(GX/BS/PP/PR)은 로더가 주입하는 run.js로 이동.
    from src.seller_console.views import _bookmarklet_run_js
    return _bookmarklet_run_js()


def test_bookmarklet_uses_shared_extractor():
    # v62 STEP1: run.js는 확장과 **동일한 kgp-extractor.js**를 번들(경로별 중복 구현 제거).
    js = _run()
    assert "kgpExtractProduct" in js and "window.__kgpRun=function(cb)" in js
    assert "parsePriceStr" in js and "_domImages" in js       # 공유 추출기 내부(단일 소스)
    assert "gallery" in js.lower()                            # 갤러리 스코프(추출기 내)
    # 옛 경로 전용 재구현(PP/PR/GX/BS 함수) 제거 — 중복 0.
    assert "function PP(t)" not in js and "function PR()" not in js
    assert "크롬 확장" in _bm()                                # 코어 CSP 실패 안내


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_run_js_defines_extractor_api_node():
    js = _run()
    shim = ("global.window=global;"
            "global.document={querySelector:function(){return null;},querySelectorAll:function(){return [];},"
            "documentElement:{outerHTML:''}};"
            "global.location={href:'https://x.com/dp/1',hostname:'x.com'};\n")
    harness = shim + js + "\nconsole.log((typeof window.kgpExtractProduct==='function')&&(typeof window.__kgpRun==='function'));"
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip().splitlines()[-1] == "true"    # 공유 추출기 API 정의됨
    finally:
        os.unlink(f.name)


def test_bookmarklet_size_within_limit():
    assert len(_bm()) < 6000, f"북마클릿 코어 너무 큼: {len(_bm())}"   # v56 로더 코어 ~3KB


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_price_parse_logic():
    # v62 STEP1: 가격 파싱은 공유 추출기(kgp-extractor.js parsePriceStr). run.js 번들에서 추출해 node로 실증.
    ex = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
    a = ex.index("function _sym(")
    b = ex.index("function uniqPush(")
    block = ex[a:b]   # _sym + CODE + PRICE_RE + parsePriceStr
    harness = block + """
var out={};
out.krw=parsePriceStr('₩89,000');
out.won=parsePriceStr('89,000원');
out.usd=parsePriceStr('$12.99');
out.none=parsePriceStr('재고 5개 남음');
console.log(JSON.stringify(out));
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        import json
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(f.name)
    assert d["krw"] == {"price": "89000", "currency": "KRW"}
    assert d["won"] == {"price": "89000", "currency": "KRW"}
    assert d["usd"] == {"price": "12.99", "currency": "USD"}
    assert d["none"] is None                                  # 통화기호 없는 숫자는 가격 아님


def test_server_accepts_bookmarklet_field_sources():
    # 북마클릿이 보낸 field_sources(tier2)를 서버가 수집 로그에 반영.
    import json
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://www.temu.com/kr/g.html", "title": "책상",
                                        "price": "20605", "currency": "KRW", "images": ["https://img.temu.com/1.jpg"],
                                        "field_sources": {"price": "tier2", "images": "tier2", "title": "tier2"}}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            it = ch.get(r.get_json()["item_id"], seller_ids={"u1"})
            ex = json.loads(it["extra_json"])
            srcs = {f["key"]: f["source"] for f in ex["collect_status"]["fields"]}
            assert srcs["price"] == "Tier2(DOM)" and srcs["images"] == "Tier2(DOM)"
            # 리뷰 등 못 채운 필드 → 부분 수집
            assert ex["collect_status"]["status"] in ("부분", "성공")
