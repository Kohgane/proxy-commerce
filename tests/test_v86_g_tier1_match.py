"""tests/test_v86_g_tier1_match.py — v86-G(수리): 테무 Tier1이 **왜 통째로 버려졌는가**.

■ 재현된 사실(추측 아님 — 이 파일이 jsdom으로 실제 실행해 보인다)
테무 PDP 렌더 응답은 **내 상품 블록과 추천 캐러셀(다른 goodsId 다수)이 한 응답에 같이** 온다.
종전 `kgp-net.js`는 응답당 goods_id를 **DFS 첫 히트 하나**만 대표 키로 박았다. 그 walk 순서는
객체 키 순서에 좌우되므로, 추천 상품 id가 먼저 잡히면

    __kgpMatchCapture(내 id) → null → __kgpTier1Mismatch = true → Tier1 후보 **전량 폐기**

가 되어 가격·옵션·갤러리가 전부 공백이 된다. 오너 실측의 `merged 0 · tier1 흔적 무`가 이 경로다.
운(키 순서)에 따라 되기도 하고 안 되기도 한다는 점이 '들쭉날쭉'의 정체다.

■ 수리(두 겹)
1) 매칭: 캡처에 **응답 안 goods_id 집합**(goods_ids)을 함께 보관하고, "내 id가 이 응답 안에 있는가"로
   판정한다. 후보가 여럿이면 (URL에 내 id → 시그니처 점수 → 최신) 순.
2) 스코프: 매칭된 응답을 **통짜로** 넘기면 추출기가 추천 상품의 가격·옵션·이미지를 집을 수 있다.
   내 goods 노드에서 위로 올라가되 **외래 goods_id가 섞이는 순간 멈춰** 가장 넓은 순수 조상만 넘긴다.
   축소가 신호를 없애면(score 0) 통짜로 되돌린다 — 스코프가 수집을 악화시키지 않는다.

■ 계약(넓힘의 대가를 함께 못박는다)
매칭을 넓혔으므로 v62의 원래 의도('다른 상품 응답 오채택 금지')가 헐거워질 수 있다. 그래서 아래는
**내 id가 아예 없는 응답은 여전히 채택 0**임을 같은 파일에서 단언한다. 인위회귀 3종으로 게이트가
공허하지 않음을 역검증한다.
"""
from __future__ import annotations

import json
import subprocess
import shutil
import tempfile
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
NET = (EXT / "kgp-net.js").read_text(encoding="utf-8")
EXTRACTOR = (EXT / "kgp-extractor.js").read_text(encoding="utf-8")
MAIN = (EXT / "kgp-main.js").read_text(encoding="utf-8")
CS = (EXT / "content_script.js").read_text(encoding="utf-8")

GID = "601099512345678"
PAGE_URL = f"https://www.temu.com/kr/x-g-{GID}.html"

# 내 상품 블록(sku 2개·갤러리 3장)과 추천 캐러셀(다른 goodsId·다른 가격·다른 옵션값)이 한 응답에.
#   ★키 순서를 '내 상품 먼저'로 둔다 — 종전 DFS 첫 히트가 추천 id를 집던 바로 그 배치다.
MINE = {
    "goods": {"goodsId": GID, "goodsName": "내 상품",
              "gallery": ["https://img.kwcdn.com/product/m1.jpg",
                          "https://img.kwcdn.com/product/m2.jpg",
                          "https://img.kwcdn.com/product/m3.jpg"]},
    "sku": [{"specKeyName": "색상", "specValueName": "블랙", "price": 12900},
            {"specKeyName": "색상", "specValueName": "화이트", "price": 12900}],
    "price": {"amount": 12900, "currency": "KRW"},
}
RECO = {"recommendList": [
    {"goodsId": "999900011112222", "goodsName": "추천 상품",
     "gallery": ["https://img.kwcdn.com/product/r1.jpg", "https://img.kwcdn.com/product/r2.jpg"],
     "sku": [{"specKeyName": "색상", "specValueName": "추천색", "price": 99900}],
     "price": {"amount": 99900, "currency": "KRW"}},
]}
MIXED_BODY = json.dumps({"store": MINE, **RECO})          # 내 상품 먼저
FOREIGN_BODY = json.dumps(RECO)                            # 내 id가 아예 없는 응답


def _jsdom_or_skip() -> str:
    if not shutil.which("node"):
        pytest.skip("node 미설치")
    probe = subprocess.run(
        ["node", "-e", "try{console.log(require.resolve('jsdom'))}catch(e){console.log('')}"],
        capture_output=True, text=True, encoding="utf-8", timeout=60)
    p = (probe.stdout or "").strip()
    if not p:
        pytest.skip("jsdom 미설치(로컬 전용 하네스) — CI 게이트는 소스계약 테스트")
    return p


_RUNNER = """
"use strict";
const { JSDOM } = require(%(JSDOM)s);
const NET = %(NET)s;
const EX = %(EX)s;
const BODY = %(BODY)s;
const OPTS = %(OPTS)s;

(async () => {
  const dom = new JSDOM("<html><body><h1>내 상품</h1></body></html>",
    { url: %(URL)s, runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  // 페이지 소유 fetch — kgp-net.js 로드 전에 존재해야 래핑된다(document_start 계약과 동일 순서).
  w.fetch = (u) => Promise.resolve({
    url: String(u),
    headers: { get: () => "application/json" },
    clone: () => ({ text: () => Promise.resolve(BODY) }),
  });
  new w.Function(NET)();
  if (OPTS.dropScope) w.__kgpScopeToGoods = undefined;      // 인위회귀: 스코프 축소 제거
  if (OPTS.singleIdMatch) {
    // 인위회귀: v86-G 이전 방식(대표 id 1개 == 내 id)으로 되돌린다.
    w.__kgpMatchCapture = function (gid) {
      gid = String(gid || "").replace(/\\D/g, "");
      const cap = w.__kgpCaptured || [];
      for (let i = 0; i < cap.length; i++) if (cap[i].goods_id === gid) return cap[i];
      return null;
    };
  }
  await w.fetch(OPTS.apiUrl || "https://www.temu.com/api/oak/integration/render?scene=goods_detail");
  await new Promise((r) => setTimeout(r, 20));

  const cap = (w.__kgpCaptured || [])[0] || null;
  const meta = new w.Function("global", EX + "\\n;return window.kgpExtractProduct;")(w)();
  console.log(JSON.stringify({
    capture: cap ? { goods_id: cap.goods_id, goods_ids: cap.goods_ids || [], score: cap.score } : null,
    top: (typeof w.__kgpTopCandidate === "function") ? w.__kgpTopCandidate() : null,
    matched: !!(typeof w.__kgpMatchCapture === "function" && w.__kgpMatchCapture(w.__kgpPageGoodsId())),
    mismatch: !!w.__kgpTier1Mismatch,
    scope: w.__kgpTier1Scope || null,
    price: meta.price || "",
    gallery: meta.images || [],
    options: (meta.options || []).map((o) => o.name + "=" + o.values.join("/")),
    field_sources: meta.field_sources || {},
  }));
})();
"""


def _run(body: str = MIXED_BODY, url: str = PAGE_URL, **opts) -> dict:
    jsdom = _jsdom_or_skip()
    script = _RUNNER % {
        "JSDOM": json.dumps(jsdom), "NET": json.dumps(NET), "EX": json.dumps(EXTRACTOR),
        "BODY": json.dumps(body), "URL": json.dumps(url), "OPTS": json.dumps(opts),
    }
    f = tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8")
    f.write(script)
    f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        assert r.returncode == 0, r.stderr
        # 추출기가 콘솔 로그를 남기므로 **마지막** JSON 줄만 취한다.
        for line in reversed([ln for ln in r.stdout.splitlines() if ln.strip()]):
            if line.lstrip().startswith("{"):
                return json.loads(line)
        raise AssertionError("하네스 출력에 JSON 없음:\n" + r.stdout)
    finally:
        Path(f.name).unlink(missing_ok=True)


# ── 1) 재현 → 수리: 추천 동봉 응답에서 Tier1이 살아남는다 ────────────────────

def test_mixed_response_still_matches_my_goods():
    """★핵심 — 내 상품 + 추천이 한 응답에 와도 매칭되고 price·options·gallery가 실린다."""
    got = _run()
    assert got["capture"], ("응답이 캡처조차 안 됐다 — 하네스 전제 붕괴", got)
    assert len(got["capture"]["goods_ids"]) >= 2, \
        ("추천 동봉 응답인데 goods_id가 1개뿐 — 재현 조건이 성립하지 않는다(공허한 그린)", got)
    assert got["matched"] and not got["mismatch"], ("내 상품 응답을 불일치로 버렸다", got)
    # 완료 판정 3종(오너 기준): 가격·옵션·갤러리가 meta에 실린다.
    assert got["price"] == "12900", ("가격 미수집", got)
    assert got["options"], ("옵션 미수집", got)
    assert len(got["gallery"]) == 3, ("갤러리 미수집", got)
    assert got["field_sources"].get("price") == "tier1", ("가격이 Tier1 출처가 아니다", got)


def test_single_id_matching_regresses_the_repair():
    """인위회귀 — 대표 id 1개 매칭으로 되돌리면 **같은 응답이 통째로 버려진다**(버그 재현).

    이 단언이 실패하면 위 그린은 수리가 아니라 하네스가 원래 쉬웠다는 뜻이다.
    """
    got = _run(singleIdMatch=True)
    assert not got["matched"], ("구방식으로 되돌렸는데도 매칭된다 — 재현 조건이 틀렸다", got)
    assert got["mismatch"], ("불일치 신호조차 안 선다", got)
    assert got["price"] == "" and not got["options"] and not got["gallery"], \
        ("Tier1 폐기 상태인데 값이 실렸다 — 재현이 무의미", got)


# ── 2) 스코프: 추천 캐러셀 값이 내 상품 자리로 새지 않는다 ────────────────────

def test_scope_excludes_recommendation_values():
    """매칭 뒤에도 **추천 옵션값이 내 옵션에 섞이면 안 된다**(조용한 오염 차단)."""
    got = _run()
    assert got["scope"] and got["scope"]["scoped"], ("스코프 축소가 안 걸렸다", got)
    joined = " ".join(got["options"])
    assert "추천색" not in joined, ("추천 상품 옵션값이 내 옵션에 유입", got)
    assert "블랙" in joined and "화이트" in joined, ("내 옵션값이 소실됐다", got)
    assert not [u for u in got["gallery"] if "/r" in u.rsplit("/", 1)[-1]], \
        ("추천 이미지가 갤러리에 유입", got)


def test_without_scope_recommendation_leaks():
    """인위회귀 — 스코프를 빼면 실제로 추천값이 샌다(계약이 공허하지 않음을 역검증)."""
    got = _run(dropScope=True)
    assert got["matched"], ("스코프와 무관하게 매칭은 돼야 한다", got)
    assert "추천색" in " ".join(got["options"]), \
        ("스코프 없이도 오염이 없다 — 이 계약이 지키는 게 없다는 뜻", got)


# ── 3) 넓힌 매칭의 대가: 오채택 금지(v62 의도)는 그대로 ──────────────────────

def test_foreign_only_response_is_still_rejected():
    """내 goods_id가 **아예 없는** 응답은 여전히 채택하지 않는다 — 매칭을 넓힌 대가를 봉인."""
    got = _run(body=FOREIGN_BODY)
    assert not got["matched"], ("남의 상품 응답을 채택했다 — v62 오채택 금지가 무너졌다", got)
    assert got["mismatch"], ("불일치 신호 미기록", got)
    assert got["price"] == "", ("남의 응답에서 가격을 집었다", got)


def test_url_hit_wins_over_score():
    """후보가 여럿이면 **URL에 내 id가 박힌 응답**이 이긴다(점수만으로 고르지 않는다)."""
    got = _run(apiUrl=f"https://www.temu.com/api/goods?goods_id={GID}")
    assert got["matched"], ("URL에 내 id가 있는데도 매칭 실패", got)
    assert got["capture"]["goods_id"] == GID, \
        ("URL에서 읽은 대표 id가 응답 walk 결과에 덮였다", got)


# ── 4) 스코프가 신호를 없애면 통짜로 되돌린다(수집 악화 금지) ────────────────

def test_scope_falls_back_when_it_would_lose_the_signal():
    """내 goods 노드만 순수하고 가격·이미지·sku가 형제에 있으면, 축소는 신호를 잃는다 → 통짜 복귀."""
    body = json.dumps({
        # 내 goods 노드의 **형제**에 외래 id를 둬서 어떤 조상도 순수하지 않게 만든다.
        "root": {
            "mine": {"goodsId": GID, "goodsName": "내 상품"},   # 자체 점수 0(가격·이미지·sku 없음)
            "other": {"goodsId": "888800011112222"},
            "price": {"amount": 12900, "currency": "KRW"},
            "gallery": ["https://img.kwcdn.com/product/m1.jpg", "https://img.kwcdn.com/product/m2.jpg"],
        },
    })
    got = _run(body=body)
    assert got["matched"], ("내 id가 응답에 있는데 매칭 실패", got)
    assert got["scope"] and got["scope"]["reason"] == "scope_lost_signal", \
        ("신호를 잃는 축소를 그대로 채택했다 — 스코프가 수집을 악화시킨다", got)
    # 통짜로 되돌아왔으므로 형제에 있던 갤러리가 Tier1으로 살아 있다(좁혔다면 0장이었다).
    assert len(got["gallery"]) == 2 and got["field_sources"].get("images") == "tier1", \
        ("통짜 복귀가 안 돼 Tier1 신호가 사라졌다", got)


# ── 5) 진단 계약: 실기기에서 이 갈래를 읽을 수 있어야 한다 ────────────────────

def test_top_candidate_reports_goods_id_count():
    """`goods_ids_n>1` = 추천 동봉 응답 = 종전 방식이 깨지던 조건. 실기기 판독의 결정적 단서."""
    got = _run()
    assert got["top"] and got["top"].get("goods_ids_n", 0) >= 2, \
        ("최고점 후보 요약에 goods_id 개수가 없다 — 실기기에서 이 갈래를 못 읽는다", got)


_PERF = """
"use strict";
const NET = %(NET)s;
globalThis.window = globalThis;
globalThis.location = { href: "https://www.temu.com/kr/x-g-%(GID)s.html" };
globalThis.XMLHttpRequest = function () {};
globalThis.XMLHttpRequest.prototype = { open() {}, send() {} };
new Function(NET)();

// 현실적 크기: 추천 200개 × 각 20필드 + 내 상품 블록. 스코프 탐색이 여기서 터지면 추출 예산(900ms)을 먹는다.
const reco = [];
for (let i = 0; i < 200; i++) {
  reco.push({ goodsId: "9999" + String(100000000 + i), goodsName: "reco " + i,
              gallery: ["https://img.kwcdn.com/product/r" + i + ".jpg"],
              sku: [{ specKeyName: "색상", specValueName: "c" + i, price: 1000 + i }],
              extra: { a: i, b: "x".repeat(40), c: [1, 2, 3, 4, 5] } });
}
const root = { store: { goods: { goodsId: "%(GID)s", goodsName: "내 상품",
                                 gallery: ["https://img.kwcdn.com/product/m1.jpg", "https://img.kwcdn.com/product/m2.jpg"] },
                        sku: [{ specKeyName: "색상", specValueName: "블랙", price: 12900 }],
                        price: { amount: 12900, currency: "KRW" } },
               recommendList: reco };
const t0 = Date.now();
const r = window.__kgpScopeToGoods(root, "%(GID)s");
const ms = Date.now() - t0;
console.log(JSON.stringify({ ms, scoped: r.scoped, reason: r.reason,
                             hasReco: JSON.stringify(r.obj).indexOf("reco 0") >= 0 }));
"""


_OVERFLOW = """
"use strict";
const NET = %(NET)s;
globalThis.window = globalThis;
globalThis.location = { href: "https://www.temu.com/kr/x-g-%(GID)s.html" };
globalThis.XMLHttpRequest = function () {};
globalThis.XMLHttpRequest.prototype = { open() {}, send() {} };
new Function(NET)();

// 내 상품이 **수집 상한(60개) 뒤**에 오도록 추천 200개를 앞에 둔다 = 대형 실응답의 모양.
const reco = [];
for (let i = 0; i < 200; i++) reco.push({ goodsId: "9999" + String(100000000 + i), goodsName: "r" + i });
const obj = { recommendList: reco,
              store: { goods: { goodsId: "%(GID)s", goodsName: "내 상품",
                                gallery: ["https://img.kwcdn.com/product/m1.jpg", "https://img.kwcdn.com/product/m2.jpg"] },
                       price: { amount: 12900, currency: "KRW" } } };
// stash를 거치지 않고 캡처 배열에 직접 넣어 '수집 목록에 내 id가 없는' 상태를 정확히 만든다.
window.__kgpCaptured = [{ url: "https://www.temu.com/api/render", score: 2, ts: Date.now(),
                          goods_id: reco[0].goodsId, goods_ids: reco.slice(0, 60).map((r) => r.goodsId),
                          obj: obj }];
const m = window.__kgpMatchCapture("%(GID)s");
console.log(JSON.stringify({ matched: !!m, listedIds: 60, hasMine: false }));
"""


def test_match_survives_goods_id_collection_cap():
    """수집 상한을 넘긴 대형 응답에서도 내 id를 찾는다 — 상한이 곧 버그 재발이 되지 않게."""
    _jsdom_or_skip()
    f = tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8")
    f.write(_OVERFLOW % {"NET": json.dumps(NET), "GID": GID})
    f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        assert r.returncode == 0, r.stderr
        got = json.loads([ln for ln in r.stdout.splitlines() if ln.strip()][-1])
    finally:
        Path(f.name).unlink(missing_ok=True)
    assert got["matched"], ("goods_ids 목록 밖(수집 상한 초과)이라고 내 응답을 버렸다", got)


def test_scope_search_is_bounded_on_large_responses():
    """스코프 탐색은 조상마다 서브트리를 훑는다 — 큰 응답에서 추출 예산(900ms)을 먹지 않아야 한다."""
    _jsdom_or_skip()   # node 존재 확인만 재사용
    f = tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8")
    f.write(_PERF % {"NET": json.dumps(NET), "GID": GID})
    f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        assert r.returncode == 0, r.stderr
        got = json.loads([ln for ln in r.stdout.splitlines() if ln.strip()][-1])
    finally:
        Path(f.name).unlink(missing_ok=True)
    assert got["scoped"] and got["reason"] == "narrowed", ("큰 응답에서 축소가 안 걸렸다", got)
    assert not got["hasReco"], ("축소했는데 추천 블록이 남아 있다", got)
    assert got["ms"] < 300, ("스코프 탐색이 느리다 — 추출 타임아웃(900ms)을 밀어낸다", got)


# ── 6) 드로어 표기: 확장이 바꾼 키를 화면이 못 따라가면 판정이 사라진다 ──────

def _diag_item(diag: dict) -> dict:
    return {"id": "x", "title": "폴더블 차량용 테이블", "url": "https://www.temu.com/kr/x-g-%s.html" % GID,
            "image_url": "", "price": "12900", "currency": "KRW",
            "extra_json": json.dumps({"price": "12900", "currency": "KRW",
                                      "images": ["https://img.kwcdn.com/product/m1.jpg"],
                                      "tier1_diag": diag})}


def test_drawer_shows_actual_adopted_url(flask_client):
    """★확장 키는 `tier1_source`인데 드로어가 `source`만 읽어 **항상 'API 응답'**으로 보이던 회귀.

    어떤 응답을 채택했는지가 화면에서 사라지면, 오너는 콘솔 없이는 Tier1 판정을 확인할 수 없다.
    """
    from unittest.mock import patch

    url = "https://www.temu.com/api/oak/integration/render?scene=goods_detail"
    diag = {"used": True, "netBound": True, "tier1_source": url, "topScore": 3, "cause": "",
            "tier1_scope": {"scoped": True, "reason": "narrowed"}}
    with patch("src.seller_console.collect_history_store.get", return_value=_diag_item(diag)), \
         patch("src.seller_console.market_credentials.is_connected", return_value=True):
        html = flask_client.get("/seller/collect/preview/x").get_data(as_text=True)
    assert "Tier1 동작" in html, "Tier1 판정 줄 자체가 안 나온다"
    assert "oak/integration/render" in html, "채택 URL이 표시되지 않는다(키 이름 회귀)"
    assert "추천 상품 블록 배제" in html, "스코프 축소 표기가 없다 — 오염 배제 여부를 화면에서 못 본다"


def test_drawer_still_reads_legacy_source_key():
    """옛 저장분(키가 `source`)도 그대로 읽힌다 — 하위호환(기록 소실 금지)."""
    tpl = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = tpl.split("Tier1 동작", 1)[1][:400]
    assert "_t1.tier1_source" in seg and "_t1.source" in seg, \
        "신·구 키를 함께 읽지 않는다 — 한쪽 기록이 화면에서 사라진다"


def test_diag_bundle_carries_scope_and_gid_count():
    """진단 번들(tier1_diag)에 goods_ids_n·tier1_scope가 실린다 — 서버·드로어에서 확인 가능."""
    assert "goods_ids_n" in CS and "tier1_scope" in CS, \
        "tier1_diag에 매칭·스코프 판독 필드가 없다"
    seg = CS.split("function _kgpTier1Diag", 1)[1].split("function _kgpTier1Cause", 1)[0]
    assert "goods_ids_n" in seg and "tier1_scope" in seg, "진단 조립 단일 소스에 미부착"
    assert "diag.scope" in MAIN, "MAIN world 브릿지가 스코프를 넘기지 않는다"
    # 스코프는 추출기 실행 **뒤에** 서는 값 — 순서가 뒤집히면 항상 null이다.
    assert MAIN.index("var meta = _run();") < MAIN.index("diag.scope"), \
        "추출 전에 스코프를 읽는다 — 언제나 null이 실린다"
