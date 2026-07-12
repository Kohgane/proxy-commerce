"""tests/test_v57_generic_images.py — v57 STEP4: 제네릭 이미지 보강.

서버: 클라(tier1/DOM) + ld+json image + og:image를 **순서 보존 union + 중복 제거**(제네릭 갤러리 누락 0).
클라: 갤러리 셀렉터 확장 — picture>source·인라인 background-image·롤오버/줌 data-*(고해상).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
API = Path("src/api/extension_api.py").read_text(encoding="utf-8")


# ── 서버 union ─────────────────────────────────────────────
def _load_api():
    import importlib
    import src.api.extension_api as m
    importlib.reload(m)
    return m


def test_union_helpers_exist():
    assert "def _union_images" in API and "def _og_images_from_html" in API
    assert "이미지 union" in API


def test_union_order_preserved_dedup():
    m = _load_api()
    client = ["https://x.com/a.jpg", "https://x.com/b.jpg"]
    ld = ["https://x.com/b.jpg", "https://x.com/c.jpg"]     # b 중복 + c 신규
    og = ["https://x.com/d.jpg", "https://x.com/a.jpg"]     # a 중복 + d 신규
    out = m._union_images(client, ld, og)
    # 순서 보존: 클라 먼저(a,b), 그 뒤 미포함분(c,d). 중복 0.
    assert out == ["https://x.com/a.jpg", "https://x.com/b.jpg",
                   "https://x.com/c.jpg", "https://x.com/d.jpg"]


def test_og_images_multi_extract():
    m = _load_api()
    html = ('<meta property="og:image" content="https://x.com/1.jpg">'
            '<meta property="og:image:url" content="https://x.com/2.jpg">'
            '<meta name="og:image" content="https://x.com/1.jpg">')   # 중복
    out = m._og_images_from_html(html)
    assert out == ["https://x.com/1.jpg", "https://x.com/2.jpg"]


def test_union_filters_logos():
    m = _load_api()
    out = m._union_images(["https://x.com/logo.png", "https://x.com/prod.jpg"])
    assert "https://x.com/prod.jpg" in out
    assert all("logo" not in u for u in out)   # filter_product_images가 로고 제거


def test_server_wires_union_in_collect():
    assert "_union_images(_client_g, _client_i, _ld_images, _og_imgs)" in API
    assert '_ld_images = list(_ld["images"])' in API


# ── 클라 셀렉터 확장 ────────────────────────────────────────
def test_extractor_selector_expansion_source():
    # 롤오버/줌 data-* + picture source + background-image.
    for tok in ("data-zoom-image", "data-large", "data-hires", "function _bgImage",
                "picture source", "background-image"):
        assert tok in EX, tok


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_best_img_src_prefers_zoom_and_bg():
    """롤오버 data-zoom-image 우선 + background-image URL 추출(순수 함수 단위)."""
    a = EX.index("function _bestImgSrc")
    b = EX.index("function _domImages")
    block = EX[a:b]
    harness = block + r"""
    function attr(map){ return { getAttribute: function(k){ return map[k] || null; }, src: map.src||'', currentSrc: map.currentSrc||'', srcset: map.srcset||'' }; }
    // 줌 이미지 우선
    var im = attr({ 'data-zoom-image':'https://x.com/ZOOM.jpg', 'data-src':'https://x.com/small.jpg', src:'https://x.com/thumb.jpg' });
    var zoom = _bestImgSrc(im);
    // background-image 추출
    var el = { getAttribute: function(k){ return k==='style' ? "background-image:url('https://x.com/BG.jpg')" : null; } };
    var bg = _bgImage(el);
    console.log(JSON.stringify({ zoom: zoom, bg: bg }));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    import json
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["zoom"] == "https://x.com/ZOOM.jpg", "롤오버 줌 이미지 우선 실패"
    assert out["bg"] == "https://x.com/BG.jpg", "background-image URL 추출 실패"
