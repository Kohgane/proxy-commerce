"""tests/test_v86_g_tier1_diag.py — v86-G: 테무 Tier1 캡처 실전 규명 계측.

■ 오너 실측(재조사 금지)
테무 상품페이지 merged 0(url 제외 62 필드 공백), **tier1 흔적 무**.

■ 규명 결과(코드 근거 — 추측 아님)
1. `kgpExtractMerged`가 `merged.tier1_diag`를 **성공 응답 경로에서만** 세웠다. 900ms 타임아웃 폴백은
   콘솔 경고만 남기고 `cb(isolated)`로 빠져 payload에 tier1 흔적이 **아예 안 실린다**.
   → 오너가 본 '흔적 무'는 "MAIN world 미응답"과 "진단 미부착"을 구분할 수 없는 상태였다.
2. `kgp-net.js`의 `stash()`는 **채점 0점 응답을 버린다**(`score<=0` → return). 그래서 종전 진단의
   `captured:0`은 "래퍼가 트래픽을 못 봤다(월드/타이밍)"와 "봤지만 전부 0점(시그니처 채점)"을
   **구분하지 못했다** — 캡처 0의 원인 갈래를 고를 근거 자체가 없었다.

■ 이 파일이 지키는 계약
- 두 경로 모두 tier1_diag를 싣는다(타임아웃 폴백 포함).
- 진단에 tier1_hits(채점 통과 수)·tier1_seen/dropped(채점 이전 트래픽)·top(최고점 후보 요약)이 실린다.
- 캡처 0의 원인 문구가 **관측값으로** 갈린다(주입 타이밍 / 형식 / 채점).
- 계수는 node로 실제 실행해 확인한다(소스 문자열 단언만으로는 동작을 보증 못 한다).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
NET = EXT / "kgp-net.js"
MAIN = EXT / "kgp-main.js"
CS = EXT / "content_script.js"


def _node_or_skip():
    if not shutil.which("node"):
        pytest.skip("node 미설치 — 실행 계약 검증 불가")


def _run_node(script: str) -> dict:
    """node로 스크립트를 돌리고 마지막 줄 JSON을 파싱한다(한글 출력 인코딩 문제 회피)."""
    f = tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8")
    f.write(script)
    f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=30)
        assert r.returncode == 0, r.stderr
        last = [ln for ln in r.stdout.splitlines() if ln.strip()][-1]
        return json.loads(last)
    finally:
        Path(f.name).unlink(missing_ok=True)


# ── kgp-net.js 계수: 트래픽을 봤는가 vs 채점에서 떨어졌는가 ────────────────────

_NET_HARNESS = """
// 최소 브라우저 셰이프 — kgp-net.js는 window/fetch/XMLHttpRequest만 만진다.
const listeners = [];
globalThis.window = globalThis;
globalThis.location = { href: "https://www.temu.com/kr/x-g-601234567890.html" };
globalThis.XMLHttpRequest = function () {};
globalThis.XMLHttpRequest.prototype = { open() {}, send() {} };
globalThis.fetch = async () => ({ headers: { get: () => "application/json" }, url: "", clone: () => ({ text: async () => "" }) });

%(NET)s

// stash는 IIFE 안 비공개 → 래퍼가 실제로 밟는 절차(p.then(r => r.clone().text()) → stash)를
// 그대로 재현해 태운다. fetch 래퍼 자체를 다시 호출하면 원본 응답을 케이스별로 바꿀 수 없다.
async function push(body, url) {
  const r = {
    url,
    headers: { get: (k) => (k.toLowerCase() === "content-type" ? "application/json" : "") },
    clone: () => ({ text: async () => body }),
  };
  // 래퍼 내부 로직과 동일한 절차를 직접 태운다.
  const ct = r.headers.get("content-type");
  if (/json/i.test(ct)) await r.clone().text().then((t) => globalThis.__kgpStashProbe(t, r.url));
}

console.log(JSON.stringify(%(BODY)s));
"""


def _net_script(body_expr: str) -> str:
    """kgp-net.js 본문에서 stash를 테스트가 부를 수 있게 노출한 사본으로 하네스를 만든다."""
    src = NET.read_text(encoding="utf-8")
    # stash는 IIFE 안 비공개 — 테스트 전용 훅으로 노출(원본 로직은 손대지 않는다).
    hooked = src.replace(
        "  // ── fetch 래핑 ──",
        "  globalThis.__kgpStashProbe = stash;\n  // ── fetch 래핑 ──",
        1,
    )
    assert "__kgpStashProbe" in hooked, "stash 노출 지점(fetch 래핑 주석)을 못 찾았다"
    return _NET_HARNESS % {"NET": hooked, "BODY": body_expr}


_PRODUCTISH = json.dumps({
    "goods": {"goodsId": "601234567890", "price": 12900,
              "gallery": ["https://img.temu.com/a.jpg", "https://img.temu.com/b.jpg"],
              "skuList": [{"specKey": "color", "specValue": "red"}]},
})
_NOISE = json.dumps({"tracking": {"sessionId": "abc", "ts": 1}})


def test_netstats_separates_no_traffic_from_zero_score():
    """★캡처 0의 두 원인을 계수로 가른다 — 트래픽 자체가 없었나, 봤지만 0점이었나."""
    _node_or_skip()
    body = """(async () => {
      await push(%(NOISE)s, "https://www.temu.com/api/track");
      await push(%(NOISE)s, "https://www.temu.com/api/log");
      await push(%(PROD)s, "https://www.temu.com/api/goods/detail");
      await push("<html>not json</html>", "https://www.temu.com/page");
      return { stats: window.__kgpNetStats, hits: (window.__kgpCaptured || []).length,
               top: window.__kgpTopCandidate() };
    })()""" % {"NOISE": json.dumps(_NOISE), "PROD": json.dumps(_PRODUCTISH)}
    got = _run_node(_net_script("await " + body))

    st = got["stats"]
    assert st["seen"] == 4, ("stash 호출 계수가 안 맞는다", got)
    assert st["jsonish"] == 3, ("JSON 파싱 성공 계수가 안 맞는다(HTML 1건은 제외)", got)
    assert st["dropped"] == 2, ("0점 폐기 계수 미기록 — '봤지만 0점'을 여전히 못 본다", got)
    assert st["kept"] == 1, ("채점 통과 계수가 안 맞는다", got)
    assert got["hits"] == 1, ("__kgpCaptured가 채점 통과분만 담는다는 전제가 깨졌다", got)
    # 버려진 응답의 URL 표본 = "트래픽은 있었다"의 물증.
    assert st["droppedUrls"], ("폐기 표본 URL 미기록 — 채점 갈래 확정 근거가 없다", got)


def test_top_candidate_summary_has_signature_breakdown():
    """최고점 후보 요약 — 점수만으론 수리 방향이 안 잡힌다(가격만 2점 vs 가격+옵션 3점)."""
    _node_or_skip()
    body = """(async () => {
      await push(%(PROD)s, "https://www.temu.com/api/goods/detail?goods_id=601234567890");
      return { top: window.__kgpTopCandidate() };
    })()""" % {"PROD": json.dumps(_PRODUCTISH)}
    got = _run_node(_net_script("await " + body))
    top = got["top"]
    assert top, ("최고점 후보 요약이 비었다", got)
    for k in ("url", "score", "price", "images", "sku", "reviews", "goods_id"):
        assert k in top, (f"후보 요약에 {k} 없음", top)
    assert top["price"] and top["images"] and top["sku"], ("시그니처 분해가 안 실린다", top)
    assert top["score"] >= 3, ("상품형 응답인데 점수가 낮다 — 채점 회귀", top)
    assert top["goods_id"] == "601234567890", ("goods_id 미기록", top)


# ── content_script.js: 두 경로 모두 진단을 싣는가 ─────────────────────────────

_CS_HARNESS = """
globalThis.window = globalThis;
globalThis.location = { href: "https://www.temu.com/kr/x-g-1.html", hostname: "www.temu.com" };
%(FNS)s
console.log(JSON.stringify(%(BODY)s));
"""


def _cs_fns() -> str:
    """content_script.js에서 진단 조립 두 함수만 떼어낸다(파일 전체는 DOM 의존이라 못 돌린다)."""
    src = CS.read_text(encoding="utf-8")
    a = src.index("function _kgpTier1Diag(")
    b = src.index("function kgpExtractMerged(")
    seg = src[a:b]
    assert "_kgpTier1Cause" in seg, "원인 판정 함수가 조립 함수와 떨어져 있다"
    return seg


@pytest.mark.parametrize("diag,expect", [
    ({"netBound": False}, "미주입"),
    ({"netBound": True, "netStats": {"seen": 0}}, "주입 타이밍"),
    ({"netBound": True, "netStats": {"seen": 5, "jsonish": 0}}, "JSON 아님"),
    ({"netBound": True, "netStats": {"seen": 5, "jsonish": 5}}, "0점"),
])
def test_capture_zero_cause_branches_are_observed_not_guessed(diag, expect):
    """★캡처 0의 원인 갈래가 **관측값**으로 갈린다 — 종전엔 전부 '매치 0건' 한 문장이었다."""
    _node_or_skip()
    got = _run_node(_CS_HARNESS % {
        "FNS": _cs_fns(),
        "BODY": "{cause: _kgpTier1Cause(%s)}" % json.dumps(diag),
    })
    assert expect in got["cause"], (f"원인 갈래가 안 갈린다: {got['cause']}", diag)


def test_diag_carries_hits_seen_dropped_and_top():
    """진단 필드 계약 — tier1_source·tier1_hits·top 요약이 실린다(오너 요구 필드)."""
    _node_or_skip()
    diag = {"netBound": True, "captured": 2, "topScore": 3,
            "netStats": {"seen": 9, "jsonish": 7, "dropped": 5, "droppedUrls": ["u1"]},
            "top": {"url": "https://x/api", "score": 3}}
    got = _run_node(_CS_HARNESS % {
        "FNS": _cs_fns(),
        "BODY": "_kgpTier1Diag(%s, 'https://x/api', true, '')" % json.dumps(diag),
    })
    assert got["tier1_source"] == "https://x/api"
    assert got["tier1_hits"] == 2, ("tier1_hits(채점 통과 수) 누락", got)
    assert got["tier1_seen"] == 9, ("tier1_seen(채점 이전 트래픽) 누락", got)
    assert got["tier1_dropped"] == 5, ("tier1_dropped 누락", got)
    assert got["top"] and got["top"]["score"] == 3, ("최고점 후보 요약 누락", got)
    assert got["used"] is True


def test_timeout_fallback_also_attaches_diag():
    """★근본 — MAIN world 미응답 경로도 tier1_diag를 싣는다.

    이게 없으면 payload에 tier1 흔적이 없는 것이 '미응답'인지 '진단 미부착'인지 영원히 못 가른다
    (오너 실기기의 '테무 tier1 흔적 무'가 정확히 그 상태였다).
    """
    src = CS.read_text(encoding="utf-8")
    tail = src.split("function kgpExtractMerged(", 1)[1].split("\nfunction handleFabClick", 1)[0]
    timeout_block = tail.split("setTimeout(", 1)[1]
    # ★주석이 아니라 **실제 대입**을 본다. 'tier1_diag'라는 낱말만 찾으면 설명 주석이 계약을 통과시킨다
    #   (이 파일의 인위회귀에서 실제로 그렇게 새는 것을 확인하고 좁힌 단언).
    assign = "isolated.tier1_diag = _kgpTier1Diag("
    assert assign in timeout_block, "타임아웃 폴백이 진단 없이 cb(isolated)로 빠진다"
    assert "cb(isolated)" in timeout_block, "폴백 경로 자체가 사라졌다"
    assert timeout_block.index(assign) < timeout_block.index("cb(isolated)"), \
        "진단을 붙이기 전에 콜백을 부른다 — payload에 안 실린다"


def test_diag_assembly_is_single_source():
    """성공/타임아웃 두 경로가 **같은 조립 함수**를 쓴다 — 두 벌이면 또 한쪽만 필드가 빠진다."""
    src = CS.read_text(encoding="utf-8")
    body = src.split("function kgpExtractMerged(", 1)[1].split("\nfunction handleFabClick", 1)[0]
    assert body.count("_kgpTier1Diag(") == 2, ("두 경로 중 하나가 조립 함수를 안 쓴다", body.count("_kgpTier1Diag("))
    # 인라인 객체 리터럴로 진단을 다시 짜는 회귀 감시.
    assert "tier1_diag = {" not in body, "진단을 인라인 리터럴로 다시 조립 중(단일 소스 위반)"


def test_main_world_forwards_netstats_and_top():
    """MAIN world가 netStats·top을 넘긴다 — 격리월드는 window.__kgp*를 직접 못 읽는다(월드 경계)."""
    m = MAIN.read_text(encoding="utf-8")
    assert "diag.netStats = window.__kgpNetStats" in m, "netStats 미전달 — 계수가 경계를 못 넘는다"
    assert "__kgpTopCandidate" in m, "최고점 후보 요약 미전달"
