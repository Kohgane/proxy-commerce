"""tests/test_v71_fold_expand.py — v71 STEP3: 상세이미지 접힘 펼침(버그③ 상세이미지 0).

증상: 상세이미지 0 — 접힘 뒤 콘텐츠(경고는 정상 출력). 수리: 보강 창에서 더보기/펼치기 버튼 자동 클릭
→ 변이 대기 → 상세 영역 이미지 수집(kgpRevealDetailFolds). 테무·CJK 펼침 라벨 + 상세 컨테이너 스코프 보강.
tier1 JSON 상세 갤러리가 있으면 그걸 우선(펼침 불요, v57 DET_KEY 유지).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.92"


def test_source_contract():
    # 테무·CJK 펼침 라벨 + 상세 컨테이너 스코프.
    assert "상품\\s*상세" in EX and "查看更多" in EX and "もっと見る" in EX
    assert '[class*="goods-desc" i] img' in EX and '[class*="decoration" i] img' in EX
    # 이미지/div 기반 펼침 후보(button/a 아님).
    assert '[class*="expand" i]' in EX and '[class*="viewmore" i]' in EX
    # tier1 상세 갤러리 우선(DET_KEY 라우팅 유지).
    assert "var DET_KEY =" in EX


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_fold_re_matches_cjk_labels_node():
    fold_re = re.search(r"var FOLD_RE = (/.*/i);", EX).group(1)
    harness = "var FOLD_RE=" + fold_re + ";\n" + r"""
var hit = ["상품 상세 더보기","상세정보 펼치기","查看更多","全部","もっと見る","view all","show more"];
var miss = ["장바구니 담기","구매하기","리뷰 12개","배송 정보"];
var ok = hit.every(function(t){return FOLD_RE.test(t);}) && miss.every(function(t){return !FOLD_RE.test(t);});
process.stdout.write(ok ? "OK\n" : "FAIL\n");
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
    finally:
        Path(f.name).unlink()
    assert r.stdout.strip().splitlines()[-1] == "OK", r.stdout


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_fold_reveal_collects_detail_images():
    """접힘 뒤 상세이미지(더보기 클릭 시 DOM 주입) → kgpRevealDetailFolds 후 상세이미지 ≥5."""
    from playwright.sync_api import sync_playwright

    mock = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta property="og:title" content="테무 상세 접힘 테스트 상품">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"테무 상세 접힘 테스트 상품",
 "image":["https://img.kwcdn.com/m1.jpg","https://img.kwcdn.com/m2.jpg"],
 "offers":{"@type":"Offer","price":"11235"}}
</script></head><body>
<h1>테무 상세 접힘 테스트 상품</h1>
<div class="goods-desc">
  <button class="view-more" onclick="var c=document.querySelector('.goods-desc');for(var i=1;i&lt;=6;i++){var im=document.createElement('img');im.src='https://img.kwcdn.com/detail-'+i+'.jpg';c.appendChild(im);}this.remove();">상품 상세 더보기</button>
</div>
</body></html>"""
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        p = b.new_context().new_page()
        p.route("**/*", lambda route: route.abort() if route.request.resource_type == "image" else route.continue_())
        p.set_content(mock, wait_until="load")
        res = p.evaluate(
            """async (ex) => {
                (0,eval)(ex);
                const before = (window.kgpExtractProduct().detail_images || []).length;
                await new Promise(r => window.kgpRevealDetailFolds(r));
                const after = (window.kgpExtractProduct().detail_images || []).length;
                return { before, after };
            }""",
            EX,
        )
        b.close()
    # 펼침 전엔 상세이미지 없음(접힘 뒤 콘텐츠) → 펼침 후 ≥5(자동 클릭·변이 수집).
    assert res["before"] < 5, res
    assert res["after"] >= 5, res
