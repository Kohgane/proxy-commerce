"""tests/test_v54_collect_discovery.py — v54 STEP2: 수집 자가진단 모드(테무 API 자가발견).

하드코딩 URL 패턴 대신, 가로챈 모든 JSON 응답을 필드 시그니처[가격·이미지배열·sku·리뷰]로 채점(0~4) →
최고점 응답을 상품 소스로 자동 채택. 진단 모드(팝업 토글)면 콘솔 표. sources=tier1:{URL패턴} 기록.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NET = (ROOT / "extensions/chrome-collector/kgp-net.js").read_text(encoding="utf-8")
EX = (ROOT / "extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MAIN = (ROOT / "extensions/chrome-collector/kgp-main.js").read_text(encoding="utf-8")
CS = (ROOT / "extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
POPUP_HTML = (ROOT / "extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
POPUP_JS = (ROOT / "extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def _node(script: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(script); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=25, cwd=str(ROOT))
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()
    finally:
        os.unlink(f.name)


def test_scoring_captures_product_rejects_nonproduct():
    out = _node("""
var P = require("path");
global.window = global;
global.fetch = function(u){ return Promise.resolve({ url:u.__u, headers:{get:function(){return "application/json";}}, clone:function(){return {text:function(){return Promise.resolve(u.__b);}};} }); };
global.XMLHttpRequest = function(){}; global.XMLHttpRequest.prototype = { open:function(){}, send:function(){}, addEventListener:function(){} };
require(P.resolve("extensions/chrome-collector/kgp-net.js"));
var product = JSON.stringify({store:{goods:{goodsName:"책상",
  skuList:[{salePrice:20605,currency:"KRW",specValue:["블랙"]}],
  galleryList:["https://img.temu.com/a.jpg","https://img.temu.com/b.jpg","https://img.temu.com/c.jpg"],
  reviews:[{reviewId:1,rating:5,comment:"좋아요 만족합니다"}]}}});
var nonprod = JSON.stringify({PRERENDER_CONFIG:{a:1},InitialI18nStore:{b:2},nav:["home","cart"]});
window.fetch({__u:"https://www.temu.com/api/goods/detail?goods_id=1", __b:product});
window.fetch({__u:"https://www.temu.com/api/nav", __b:nonprod});
setTimeout(function(){
  var cap = window.__kgpCaptured;
  var top = cap[0] || {};
  console.log("@@" + JSON.stringify({n:cap.length, score:top.score, price:!!top.price, images:!!top.images, sku:!!top.sku, reviews:!!top.reviews, url:top.url, rows:window.__kgpDiagRows().length}));
}, 60);
""")
    d = json.loads([l[2:] for l in out.splitlines() if l.startswith("@@")][-1])
    assert d["n"] == 1                                  # 상품 응답만 채택(비상품 score 0 → 버림)
    assert d["score"] == 4 and d["price"] and d["images"] and d["sku"] and d["reviews"]
    assert "goods/detail" in d["url"]                    # 채택 응답 URL 기록
    assert d["rows"] == 1                                # 진단 표 행


def test_extractor_uses_top_scored_and_records_tier1_source():
    out = _node("""
var P = require("path");
global.window = global;
global.location = { href: "https://www.temu.com/kr/x-g-601099.html" };
global.document = { querySelectorAll:function(){return [];}, querySelector:function(){return null;}, title:"Temu" };
global.__kgpCaptured = [
  { url:"https://www.temu.com/api/goods/detail?g=1", score:4, price:1, images:1, sku:1, reviews:1,
    obj:{ goods:{ goodsName:"접이식 책상", skuList:[{salePrice:20605,currency:"KRW",specValue:["블랙"]}],
      galleryList:["https://img.temu.com/a.jpg","https://img.temu.com/b.jpg"], avgRating:4.7, reviewNum:328,
      reviews:[{rating:5,comment:"좋아요"}] }} },
  { url:"https://www.temu.com/api/reco", score:1, obj:{ list:["x"] } }
];
require(P.resolve("extensions/chrome-collector/kgp-extractor.js"));
var r = window.kgpExtractProduct();
console.log("@@" + JSON.stringify({price:r.price, cur:r.currency, gallery:r.gallery_images.length, tier1:r.tier1_source, src:r.field_sources.price, partial:r.partial}));
""")
    d = json.loads([l[2:] for l in out.splitlines() if l.startswith("@@")][-1])
    assert d["price"] == "20605" and d["cur"] == "KRW"   # 최고점 응답에서 매핑
    assert d["gallery"] == 2 and d["partial"] is False
    assert d["src"] == "tier1"
    assert "goods/detail" in d["tier1"]                  # sources=tier1:{채택 URL}


def test_diag_mode_source_contract():
    # 팝업 토글 + 저장 키 + MAIN 핸들러 + content_script 배선.
    assert 'id="diagToggle"' in POPUP_HTML and "자가진단" in POPUP_HTML
    assert "kgp_diag" in POPUP_JS
    assert "__kgpDiagReq" in MAIN and "console.table" in MAIN
    assert "__kgpDiagRows" in NET                         # 채점 메타 표 데이터
    assert "KGP_DIAG" in CS and "__kgpDiagReq" in CS      # 격리월드 주기 요청
    assert "_kgpScore" in NET and "sig.price" in NET      # 시그니처 채점기


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.62"
