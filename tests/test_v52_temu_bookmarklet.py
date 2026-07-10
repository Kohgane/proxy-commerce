"""tests/test_v52_temu_bookmarklet.py — v52 STEP3: 테무 북마클릿 Tier2 클라 추출.

북마클릿이 클릭 시점 렌더 DOM에서 소형 구조 추출을 직접 수행: h1 타이틀·메인영역 판매가(취소선 제외)·
갤러리 스코프 이미지(src+data-src+srcset 최고해상, 추천 제외, naturalWidth 필터 금지). payload 동봉+field_sources.
못 채우는 필드(리뷰·전체 sku)는 '부분 수집 — 확장 권장'(v51 규약).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


def _bm():
    from src.seller_console.views import _bookmarklet_js
    return _bookmarklet_js("https://kohganepercentiii.com", "TOK", True)


def test_bookmarklet_tier2_source_contract():
    js = _bm()
    assert "function GX(" in js and "function BS(" in js and "function PP(" in js and "function PR(" in js
    assert "querySelector('h1')" in js                       # h1 타이틀 우선
    assert "gallery i] img" in js and "swiper i] img" in js  # 갤러리 스코프
    # 이미지 수집 구간(var imgs … var data)에 naturalWidth 필터 없음(추천 오수집 원인 제거).
    img_region = js.split("var imgs=[]")[1].split("var data=")[0]
    assert "naturalWidth" not in img_region
    assert "field_sources:_fs" in js                         # 필드 출처 동봉
    assert "strike" in js and ("정가" in js or "original" in js)  # 취소선/정가 제외
    assert "temu" in js and "크롬 확장" in js                # 테무 부분수집 안내(확장 권장)


def test_bookmarklet_size_within_limit():
    assert len(_bm()) < 6000, f"북마클릿 너무 큼: {len(_bm())}"


def test_price_parse_logic():
    # 북마클릿의 PP(가격 파싱)를 추출해 node로 실증.
    js = _bm()[len("javascript:"):]
    m = re.search(r"function PP\(t\)\{.*?\}(?=function|var )", js, re.S)
    assert m, "PP 함수를 찾지 못함"
    fn = m.group(0)
    harness = fn + """
var out = {};
out.krw = PP('₩89,000');
out.won = PP('89,000원');
out.usd = PP('$12.99');
out.none = PP('재고 5개 남음');
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
