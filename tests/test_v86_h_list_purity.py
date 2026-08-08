"""tests/test_v86_h_list_purity.py — v86-H: 목록 페이지가 상품 필드를 오염시키는 갈래를 끊는다.

■ 오너 채점 확정(재조사 금지) — 1.5.138 리스트 진단 3소스
UI 계층은 전부 그린(타일 부착 100%·rest 0·hover 1·violations 0). 결함은 **extracted 단일 갈래**:
pageType=list인데 tier2/3가 페이지 UI를 상품 필드로 오인했다.
  · 라쿠텐: options=도도부현 47+정렬 8+리뷰필터 / price=5.3 JPY(오인) / title="ソーシャルギフト"(네비)
  · 아마존: options=정렬 드롭다운 / desc="Automate shopping…"(Rufus) / title=검색어(tier3)
  · 알리: images 154장에 48x48 아이콘·배너 혼입

■ 이 파일이 쓰는 증거
추측이 아니라 **오너가 커밋한 실제 진단 스냅샷**(fixtures/realpages/diag/kgp-snapshot-*)에
라이브 kgp-extractor.js를 물려 돌린 결과로 계약한다.

■ 두 겹의 수리와, 각 겹이 지키는 것
1) 억제 — 목록에는 상품이 하나가 아니다. tier2/3 DOM 폴백으로 상품 단위 필드를 채우는 행위 자체가
   정의상 오답이므로 비운다. 빈 값은 `suppressed:{reason:"list", fields:[...]}`로 사유를 남긴다.
2) tier1 예외의 조건 — "tier1이면 믿는다"는 목록에서 성립하지 않는다. 실측 3소스 모두 JSON-LD
   `@type:Product`가 **0건**이고, 라쿠텐의 title/price는 스키마 무관 상태 딥워크가 집은 네비·프로모 값이다.
   그래서 예외는 **Product 선언이 실제로 기여했을 때(ldProduct)** 로만 좁힌다.
3) 이미지 — 비우지 않고 크기 게이트만(목록에도 상품 이미지는 실재). 오프라인 스냅샷·CI에서도 재도록
   **URL 크기 토큰**을 1순위로 쓴다(렌더가 없으면 naturalWidth=0이라 렌더 크기만으론 계약이 공허해진다).

■ 상세 경로 불가침
억제 블록은 `pageType==='list'`에서만 실행된다. 상세 픽스처 계약이 그대로 그린임을 같은 파일에서 못박는다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(".").resolve()
EXT = Path("extensions/chrome-collector")
EXTRACTOR = (EXT / "kgp-extractor.js").read_text(encoding="utf-8")
DETECT = (EXT / "kgp-detect.js").read_text(encoding="utf-8")
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
MAIN = (EXT / "kgp-main.js").read_text(encoding="utf-8")
DIAG = Path("fixtures/realpages/diag")

_REQUIRE_BROWSER = os.getenv("KGP_REQUIRE_BROWSER", "") == "1"

# 오너 커밋 스냅샷(실측 3소스). 파일명이 길어 상수로 고정 — 없으면 계약이 공허해지므로 존재를 단언한다.
SNAP_RAKUTEN = DIAG / "kgp-snapshot-search-rakuten-co-jp-search-mall-ED-82-A4-EB-A6-AC-ED-9E-88-.html"
SNAP_AMAZON = DIAG / "kgp-snapshot-www-amazon-com-s-k-ultraslim-phone-grip-crid-3T81T8A1LNTXL-s.html"
SNAP_ALI = DIAG / "kgp-snapshot-ko-aliexpress-com-w-wholesale-craighill-summit-2525252dcard-.html"
URL_RAKUTEN = "https://search.rakuten.co.jp/search/mall/x/"
URL_AMAZON = "https://www.amazon.com/s?k=ultraslim+phone+grip"
URL_ALI = "https://ko.aliexpress.com/w/wholesale-x.html"


def _jsdom_path() -> str:
    """jsdom 경로. KGP_REQUIRE_BROWSER=1이면 **skip 대신 실패** — 계약이 조용히 안 돌면 그린이 거짓이다."""
    if not shutil.which("node"):
        if _REQUIRE_BROWSER:
            pytest.fail("KGP_REQUIRE_BROWSER=1인데 node가 없다 — 목록 오염 계약이 실행되지 않는다")
        pytest.skip("node 미설치")
    probe = subprocess.run(
        ["node", "-e", "try{console.log(require.resolve('jsdom'))}catch(e){console.log('')}"],
        capture_output=True, text=True, encoding="utf-8", timeout=60)
    p = (probe.stdout or "").strip()
    if not p:
        if _REQUIRE_BROWSER:
            pytest.fail("KGP_REQUIRE_BROWSER=1인데 jsdom이 없다 — 목록 오염 계약이 실행되지 않는다")
        pytest.skip("jsdom 미설치")
    return p


_RUNNER = """
"use strict";
const fs = require("fs");
const { JSDOM } = require(%(JSDOM)s);
const EX = %(EX)s;
const HTML = fs.readFileSync(%(FILE)s, "utf-8");
const dom = new JSDOM(HTML, { url: %(URL)s, runScripts: "outside-only", pretendToBeVisual: true });
const w = dom.window;
const extract = new w.Function("global", EX + "\\n;return window.kgpExtractProduct;")(w);
const m = extract(%(OPTS)s);
const opt = (m.options || []);
console.log("RESULT " + JSON.stringify({
  title: m.title || "", price: m.price || "", desc: (m.description || "").slice(0, 80),
  optAxes: opt.map((o) => o.name), optValues: opt.reduce((a, o) => a.concat(o.values), []),
  specs: (m.detail_specs || []).length, skus: (m.skus || []).length,
  reviews: (m.reviews || []).length, rating: m.rating || "", images: m.images || [],
  field_sources: m.field_sources || {}, page_type: m.page_type || "",
  suppressed: m.suppressed || null, ldProduct: undefined,
}));
"""


def _extract(file: Path, url: str, opts: str = "undefined", src: str | None = None) -> dict:
    jsdom = _jsdom_path()
    assert file.exists(), f"오너 진단 스냅샷 미커밋: {file.name} — 이 계약은 실측 없이는 의미가 없다"
    script = _RUNNER % {
        "JSDOM": json.dumps(jsdom), "EX": json.dumps(src if src is not None else EXTRACTOR),
        "FILE": json.dumps(str(file)), "URL": json.dumps(url), "OPTS": opts,
    }
    f = tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8")
    f.write(script)
    f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=600)
        assert r.returncode == 0, r.stderr[-2000:]
        for line in r.stdout.splitlines():
            if line.startswith("RESULT "):
                return json.loads(line[len("RESULT "):])
        raise AssertionError("하네스 출력에 RESULT 없음:\n" + r.stdout[-2000:])
    finally:
        Path(f.name).unlink(missing_ok=True)


# ── 1) 라쿠텐 검색: 도도부현·정렬·리뷰필터 오염이 사라진다 ────────────────────

# 실측 오염 표본(오너 증거) — 이 값이 옵션에 남아 있으면 그대로 오염이다.
_RAKUTEN_JUNK = ["北海道", "青森", "東京都", "沖縄"]


def test_rakuten_list_pollution_is_reproducible_without_the_gate():
    """★먼저 **오염을 재현**한다 — 억제 없이 돌리면 도도부현이 옵션에 실린다(계약의 전제 확인)."""
    got = _extract(SNAP_RAKUTEN, URL_RAKUTEN)          # pageType 미전달 → 억제 없음
    vals = " ".join(got["optValues"])
    assert len(got["optValues"]) >= 40, ("도도부현 오염이 재현되지 않는다 — 이 계약의 전제가 틀렸다", got["optAxes"], len(got["optValues"]))
    assert any(j in vals for j in _RAKUTEN_JUNK), ("도도부현 값이 안 보인다 — 표본이 바뀌었다", vals[:200])
    assert got["suppressed"] is None, "억제를 안 켰는데 suppressed가 붙었다"


def test_rakuten_list_fields_are_suppressed():
    """★목록 판정이면 상품 단위 필드가 비고, 사유가 남는다(조용한 오염도 조용한 공백도 금지)."""
    got = _extract(SNAP_RAKUTEN, URL_RAKUTEN, opts='{pageType:"list"}')
    assert got["optValues"] == [], ("도도부현·정렬·리뷰필터가 옵션에 남아 있다", got["optAxes"], got["optValues"][:10])
    assert got["title"] == "", ("네비 문구가 제목으로 남았다", got["title"])
    assert got["price"] == "", ("오인 가격(5.3)이 남았다", got["price"])
    assert got["desc"] == "", ("목록 안내문이 상세설명으로 남았다", got["desc"])
    assert got["suppressed"] and got["suppressed"]["reason"] == "list", ("억제 사유 미기록", got["suppressed"])
    for f in ("title", "price", "options", "description"):
        assert f in got["suppressed"]["fields"], (f + " 억제가 기록되지 않았다", got["suppressed"])
    assert got["page_type"] == "list"


def test_amazon_list_fields_are_suppressed():
    """아마존 검색: 정렬 드롭다운·Rufus 문구·검색어 제목이 상품 필드로 남지 않는다."""
    got = _extract(SNAP_AMAZON, URL_AMAZON, opts='{pageType:"list"}')
    assert got["title"] == "" and got["price"] == "", ("검색어/가격이 상품 값으로 남았다", got["title"], got["price"])
    assert got["optValues"] == [], ("정렬 드롭다운이 옵션으로 남았다", got["optAxes"])
    assert "Automate shopping" not in got["desc"], ("Rufus 문구가 상세설명으로 남았다", got["desc"])
    assert got["suppressed"] and got["suppressed"]["reason"] == "list"


def test_tier1_exception_requires_a_declared_product():
    """★tier1 예외의 조건 — 실측 3소스엔 JSON-LD `@type:Product`가 0건이라 예외가 열리면 안 된다.

    이 단언이 없으면 "tier1이니까 믿는다"가 라쿠텐 네비 값(title/price)을 그대로 통과시킨다(실측 재현됨).
    """
    for snap in (SNAP_RAKUTEN, SNAP_AMAZON, SNAP_ALI):
        assert snap.exists(), f"스냅샷 미커밋: {snap.name}"
        txt = snap.read_text(encoding="utf-8", errors="ignore")
        assert '"@type":"Product"' not in txt.replace(" ", ""), \
            (snap.name + ": Product 선언이 생겼다 — 이 계약의 전제(예외가 안 열림)를 재검토해야 한다")
    src = EXTRACTOR
    assert "ldProduct" in src, "tier1 출처 구분 플래그가 없다"
    seg = src.split("if (_pageType === \"list\")", 1)[1].split("var fieldSources", 1)[0]
    assert "_t1 = !!j.ldProduct" in seg, "목록 억제가 ldProduct로 tier1 예외를 좁히지 않는다"
    assert seg.count("_t1 &&") >= 6, ("일부 필드가 여전히 무조건 tier1 예외를 받는다", seg.count("_t1 &&"))


# ── 2) 이미지 크기 게이트 (리스트 갈래 전용) ────────────────────────────────

def test_ali_list_image_gate_drops_icons_keeps_products():
    """★알리 목록 실측 — 48x48·60x60·154x64 아이콘/배너는 빠지고 480x480 상품 이미지는 남는다."""
    got = _extract(SNAP_ALI, URL_ALI, opts='{pageType:"list"}')
    imgs = got["images"]
    assert imgs, "이미지가 통째로 사라졌다 — 게이트가 과잉 차단"
    bad = [u for u in imgs if "/48x48." in u or "/60x60." in u or "/154x64." in u or "/45x60." in u]
    assert not bad, ("아이콘·배너가 갤러리에 남았다", bad[:5])
    good = [u for u in imgs if "480x480" in u]
    assert len(good) >= 20, ("상품 이미지(480x480)가 과잉 제거됐다", len(good), len(imgs))
    assert got["suppressed"] and got["suppressed"]["images_dropped"] >= 5, \
        ("제외 장수가 기록되지 않았다(조용한 삭제 금지)", got["suppressed"])


def test_url_size_token_is_the_primary_measure():
    """URL 크기 토큰이 1순위 — 오프라인/CI엔 렌더가 없어 naturalWidth로만 재면 계약이 공허해진다."""
    src = EXTRACTOR
    seg = src.split("function _listImageGate", 1)[1].split("return { images: kept", 1)[0]
    assert "_urlSize(u) || dim[" in seg, "URL 토큰을 렌더 크기보다 먼저 보지 않는다"
    assert "if (!d) return true" in seg, "측정 불가를 제외로 단정한다(정직 위반)"
    # 실측 토큰 형태가 모두 잡히는지 — 알리 상품/아이콘/배너 3형태.
    assert "[_/](\\d{2,4})x(\\d{2,4})" in src, "크기 토큰 정규식이 경로형(/48x48.)을 못 잡는다"


# ── 3) 인위회귀 — 게이트를 무력화하면 오염이 되살아난다 ──────────────────────

def test_disabling_the_gate_brings_the_pollution_back():
    """★인위회귀 — 억제 분기를 죽이면 라쿠텐 도도부현 오염이 **재현되어야** 한다.

    실패하면 위 그린은 수리가 아니라 하네스가 원래 통과했다는 뜻이다.
    """
    broken = EXTRACTOR.replace('if (_pageType === "list") {', 'if (_pageType === "__never__") {', 1)
    assert broken != EXTRACTOR, "억제 분기 주입 지점을 못 찾았다"
    got = _extract(SNAP_RAKUTEN, URL_RAKUTEN, opts='{pageType:"list"}', src=broken)
    vals = " ".join(got["optValues"])
    assert any(j in vals for j in _RAKUTEN_JUNK), \
        ("게이트를 죽였는데도 오염이 없다 — 이 계약이 지키는 게 없다는 뜻", got["optAxes"], vals[:200])
    assert got["suppressed"] is None, "무력화했는데 suppressed가 붙었다"


# ── 4) 상세 페이지 불가침 ──────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["ali-detail", "rakuten-detail", "synthetic-amazon-dp"])
def test_detail_extraction_untouched(name):
    """상세 픽스처는 억제 블록을 타지 않는다 — 필드가 살아 있고 suppressed가 붙지 않는다."""
    fx = Path("fixtures/realpages") / (name + ".html")
    spec = json.loads((Path("fixtures/realpages") / (name + ".expected.json")).read_text(encoding="utf-8"))
    got = _extract(fx, spec["url"])
    assert got["suppressed"] is None, ("상세인데 목록 억제가 걸렸다", got["suppressed"])
    assert got["title"], ("상세 제목이 사라졌다", got)
    if spec.get("price"):
        assert got["price"] == spec["price"], ("상세 가격 회귀", got["price"], spec["price"])


def test_suppression_block_is_list_only():
    """소스 계약 — 억제·이미지 게이트는 `pageType==='list'` 블록 안에서만 호출된다(상세 무영향)."""
    src = EXTRACTOR
    body = src.split("function kgpExtractProduct", 1)[1]
    i_if = body.index('if (_pageType === "list") {')
    i_fs = body.index("var fieldSources")
    block = body[i_if:i_fs]
    assert "_listImageGate(" in block, "이미지 게이트가 목록 블록 밖에 있다"
    assert body.count("_listImageGate(") == 1, "이미지 게이트가 목록 밖에서도 호출된다(상세 오염 위험)"
    assert body.count("_suppressed = {") == 1


# ── 5) pageType 전달 배선 — 억제가 실기기에서 실제로 켜지는가 ────────────────

def test_page_type_is_wired_from_isolated_world():
    """격리월드의 권위 판정(kgpPageType)이 추출기와 MAIN world 양쪽에 전달된다.

    MAIN world는 kgpFindCards가 없어 스스로 목록 판정을 못 한다 — 배선이 끊기면 억제가 조용히 꺼진다.
    """
    assert "window.kgpExtractProduct({ pageType: kgpPageType() })" in CS, \
        "격리월드 추출 진입에 pageType 미전달"
    assert "__kgpReq: reqId, pageType:" in CS, "MAIN world 요청에 pageType 미동봉"
    assert "_run({ pageType: (e.data && e.data.pageType) || \"\" })" in MAIN, \
        "MAIN 브릿지가 pageType을 추출기에 넘기지 않는다"
    assert "function _extractPageType(opts)" in EXTRACTOR
    # 호출자가 안 주면 KGPDetect로 폴백하고, 그것도 없으면 ""(=억제 안 함)여야 한다(북마클릿 무회귀).
    seg = EXTRACTOR.split("function _extractPageType(opts)", 1)[1].split("\n  }", 1)[0]
    assert "KGPDetect" in seg and 'return ""' in seg, "폴백 사다리가 없다"
