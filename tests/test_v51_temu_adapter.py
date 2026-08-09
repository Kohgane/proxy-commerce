"""tests/test_v51_temu_adapter.py — v51 STEP1: 테무 어댑터 3계층(Tier1 API 캡처·Tier2 DOM·Tier3 og).

확정 전제(오너): 테무는 window.rawData/초기상태 전역 없음, og 없음, 데이터는 API 응답으로만 존재.
Tier1(kgp-net.js MAIN document_start): 페이지가 이미 받은 상품 API 응답을 캡처(추가 요청 0) → 확장 최우선.
Tier2: 렌더 DOM 갤러리 스코프(naturalWidth 필터 제거·document.images 전체 금지·추천 제외). Tier3: og/meta.
필드별 sources(tier1/tier2/tier3) → 서버 로그. state_json은 테무 URL서 폐기.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NET = (ROOT / "extensions/chrome-collector/kgp-net.js").read_text(encoding="utf-8")
EX = (ROOT / "extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
VIEWS = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
SJ = (ROOT / "src/collectors/state_json.py").read_text(encoding="utf-8")


def _node(script: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(script); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=25, cwd=str(ROOT))
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()
    finally:
        os.unlink(f.name)


# ── manifest: Tier1 주입 ──────────────────────────────────────
def test_manifest_net_capture_document_start_main():
    nets = [cs for cs in MANIFEST["content_scripts"]
            if cs.get("world") == "MAIN" and cs.get("run_at") == "document_start" and "kgp-net.js" in cs.get("js", [])]
    assert nets, "kgp-net.js MAIN world document_start 항목 없음"


# ── Tier1: 캡처 로직 ──────────────────────────────────────────
def test_net_captures_product_rejects_nonproduct():
    out = _node("""
var P = require("path");
global.window = global;
global.fetch = function(u){ return Promise.resolve({ headers:{get:function(){return u.__ct;}}, clone:function(){return {text:function(){return Promise.resolve(u.__body);}};} }); };
global.XMLHttpRequest = function(){}; global.XMLHttpRequest.prototype = { open:function(){}, send:function(){}, addEventListener:function(){} };
require(P.resolve("extensions/chrome-collector/kgp-net.js"));
window.fetch({__body: JSON.stringify({goods:{skuList:[{salePrice:20605}],galleryList:["a"]}}), __ct:"application/json"});
window.fetch({__body: JSON.stringify({PRERENDER_CONFIG:{x:1},InitialI18nStore:{y:2}}), __ct:"application/json"});
setTimeout(function(){ var e=window.__kgpCaptured[0]||{}; console.log(JSON.stringify({n: window.__kgpCaptured.length, hasGoods: !!(e.obj&&e.obj.goods), bound: !!window.__kgpNetBound})); }, 40);
""")
    d = json.loads(out)
    # v54: 캡처 엔트리는 {obj,score,url} 구조 → obj.goods 확인.
    assert d["n"] == 1 and d["hasGoods"] is True and d["bound"] is True   # 상품만 캡처, 비상품 배제


# ── Tier1: 캡처본 → 추출 ──────────────────────────────────────
def test_extractor_tier1_from_captured_api():
    out = _node("""
global.window = global;
global.location = { href: "https://www.temu.com/kr/goods.html?goods_id=1" };
global.document = { querySelectorAll:function(){return [];}, querySelector:function(){return null;}, title:"Temu" };
global.__kgpCaptured = [{ goods:{ goodsName:"접이식 책상",
  skuList:[{salePrice:20605,currency:"KRW",specValue:["블랙"]},{salePrice:22000,currency:"KRW",specValue:["화이트"]}],
  galleryList:["https://img.temu.com/a.jpg","https://img.temu.com/b.jpg","https://img.temu.com/c.jpg"],
  detailGallery:["https://img.temu.com/d1.jpg"], avgRating:4.7, reviewNum:328,
  reviews:[{reviewId:1,rating:5,comment:"좋아요"}] }}];
require(require("path").resolve("extensions/chrome-collector/kgp-extractor.js"));
var r = window.kgpExtractProduct();
console.log("@@" + JSON.stringify({price:r.price, cur:r.currency, gallery:r.gallery_images.length, detail:r.detail_images.length,
  opts:r.options.length, rating:r.rating, rc:r.review_count, title:r.title, partial:r.partial, src:r.field_sources}));
""")
    d = json.loads([ln[2:] for ln in out.splitlines() if ln.startswith("@@")][-1])
    assert d["price"] == "20605" and d["cur"] == "KRW"       # 첫 유효 sku, 오너 기대 20605
    assert d["gallery"] == 3 and d["detail"] == 1 and d["opts"] == 1
    assert d["rating"] == "4.7" and d["rc"] == "328"
    assert d["partial"] is False
    assert d["src"]["price"] == "tier1" and d["src"]["images"] == "tier1"   # Tier1 출처 표기


# ── Tier2: 갤러리 스코프(추천 제외·naturalWidth 제거) ─────────
def test_tier2_gallery_scope_excludes_recommend_no_naturalwidth():
    # 소스 계약: 페이지 전체 document.images 폴백 루프 제거 + 갤러리 스코프 + 추천 제외.
    assert "var all = document.images" not in EX                 # 옛 전체 폴백 루프 제거
    assert "naturalWidth || 250" not in EX and "naturalWidth || 0) >= 300" not in EX  # 옛 필터 제거
    assert "_galleryExcluded" in EX and "_bestImgSrc" in EX
    assert "recommend" in EX and "related" in EX
    assert "폴백 금지" in EX                                       # 전체 폴백 금지 명시


# ── state_json: 테무 폐기 ─────────────────────────────────────
def test_state_json_deprecated_for_temu():
    from src.collectors.state_json import parse_state_from_html
    html = '<script>window.rawData={"goods":{"skuList":[{"salePrice":20605,"currency":"KRW"}]}}</script>'
    # 테무 URL → 파서 건너뜀(빈 결과)
    assert parse_state_from_html(html, "https://www.temu.com/kr/g.html") == {}
    # 비-테무 URL → 정상 파싱
    r = parse_state_from_html(html, "https://other.com/p")
    assert r and r.get("price") == "20605"


# ── sources 라벨 렌더 + 북마클릿 토스트 + 다운로드 ────────────
def test_source_labels_and_bookmarklet_toast():
    from src.collectors.collect_status import compute_collect_status
    st = compute_collect_status({"title_ko": "A", "price": "100", "price_status": "", "images": ["a"]},
                                sources={"price": "tier1", "images": "tier2", "title": "tier3"})
    labels = {f["key"]: f["source"] for f in st["fields"]}
    assert labels["price"] == "Tier1(API/상태)" and labels["images"] == "Tier2(DOM)" and labels["title"] == "Tier3(og)"
    # 북마클릿 테무 안내 토스트 + 다운로드 ZIP kgp-net.js 포함
    # v53+: ZIP 파일 목록은 src/build_extension.py로 이관됨(views.py는 build_zip_bytes 위임).
    assert "temu" in VIEWS.lower() and "크롬 확장" in VIEWS
    from pathlib import Path as _P
    _BUILD = _P("src/build_extension.py").read_text(encoding="utf-8")
    assert '"kgp-net.js"' in _BUILD
    # state_json 테무 폐기 주석
    assert "테무" in SJ and "폐기" in SJ or "건너뛴" in SJ
