"""tests/test_v70_gallery_scope.py — v70 STEP3: 아마존 갤러리 스코프(현행범 버그③).

증상: 이미지 58장 — 갤러리 스코프 실패(관련상품·스프라이트 혼입).
수리: 아마존은 #altImages + #imgTagWrapper 한정, hiRes/data-old-hires/data-a-dynamic-image 고해상 승격,
관련상품·스프라이트·1px 배제 → 자기 상품 이미지만(5~15장).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.137"


def test_source_contract():
    assert "function _amazonGallery()" in EX
    assert "function _amazonDynMax(im)" in EX
    # 스코프: altImages + imgTagWrapper만.
    assert "#altImages img" in EX and "#imgTagWrapperId img" in EX
    # data-a-dynamic-image 고해상 승격.
    assert 'im.getAttribute("data-a-dynamic-image")' in EX
    # 아마존 분기: 브로드 제네릭 스코프 건너뛰고 early-return.
    assert "if (/(^|\\.)amazon\\.[a-z.]+$/.test(_host)) {" in EX
    assert "return { images: out, detailImages: det };   // 브로드 제네릭 스코프 건너뜀" in EX


def _fn(name):
    m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{.*?\n  \}", EX, re.S)
    assert m, name + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_amazon_gallery_scoped_hires_node():
    """스코프 밖 관련상품 53장을 무시하고 #altImages/#imgTagWrapper 자기 상품 5장만 + hi-res 승격."""
    deps = "\n".join([
        "var NONPROD_IMG = " + re.search(r"var NONPROD_IMG = (/.*/i);", EX).group(1) + ";",
        _fn("isProductImg"),
        _fn("hiRes"),
        _fn("uniqPush"),
        _fn("_bestImgSrc"),
        _fn("_galleryExcluded"),
        _fn("_amazonDynMax"),
        _fn("_amazonGallery"),
    ])
    harness = deps + "\n" + r"""
function img(o){
  o.parentElement = null;
  o.getAttribute = function(k){ return (o.attrs && o.attrs[k]) || null; };
  o.querySelector = function(){ return null; };
  o.naturalWidth = o.naturalWidth || 0; o.naturalHeight = o.naturalHeight || 0;
  o.width = o.width || 0; o.height = o.height || 0;
  o.currentSrc = o.currentSrc || ""; o.src = o.src || ""; o.srcset = o.srcset || "";
  return o;
}
var B = "https://m.media-amazon.com/images/I/";
// 메인: data-a-dynamic-image(1500 vs 500) → 1500 승격.
var main = img({ id:"landingImage", naturalWidth:500, naturalHeight:500,
  attrs:{ "data-a-dynamic-image": JSON.stringify({ ["" + B + "MAIN._AC_SL500_.jpg"]:[500,500], ["" + B + "MAIN._AC_SL1500_.jpg"]:[1500,1500] }) },
  src: B + "MAIN._AC_SL500_.jpg" });
// 썸네일 4장(._SS40_ → hiRes 원본 승격).
var thumbs = [1,2,3,4].map(function(n){ return img({ naturalWidth:40, naturalHeight:40, currentSrc: B + "T" + n + "._SS40_.jpg" }); });
// 스프라이트 아이콘(1px) — 배제.
var sprite = img({ naturalWidth:1, naturalHeight:1, currentSrc: B + "sprite-play-icon.png" });
var scoped = [main].concat(thumbs).concat([sprite]);
// 관련상품 53장(스코프 밖) — 브로드 img 셀렉터에만 걸림.
var related = [];
for (var i=0;i<53;i++) related.push(img({ naturalWidth:300, naturalHeight:300, currentSrc: B + "REL" + i + ".jpg" }));

global.document = {
  querySelectorAll: function(sel){
    if (/altImages|imgTagWrapper|landingImage|imageBlock|ivLargeImage|main-image-container/.test(sel)) return scoped;
    return scoped.concat(related);   // 브로드 셀렉터라면 58장(관련상품 포함) — _amazonGallery는 스코프만 봐야 함
  }
};
var out = _amazonGallery();
process.stdout.write(JSON.stringify(out) + "\n");
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    # 자기 상품 5장(메인+썸네일4), 관련상품 53·스프라이트 배제 → 5~15 범위.
    assert 5 <= len(out) <= 15, (len(out), out)
    assert len(out) == 5, out
    # 관련상품(REL) 혼입 0.
    assert not any("REL" in u for u in out), out
    # 스프라이트 배제.
    assert not any("sprite" in u for u in out), out
    # hi-res 승격: 메인은 SL1500에서 파생(썸네일 SS40/SL500 아님) — hiRes로 크기토큰 제거.
    assert any("MAIN" in u for u in out), out
    assert not any("_SL500_" in u or "_SS40_" in u for u in out), out   # 크기토큰 제거됨
