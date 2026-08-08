"""tests/test_v86_i_single_store.py — v86-I: 추출은 됐는데 저장이 빈 갈래를 스토어 단일화로 덮는다.

■ 오너 채점 확정(재조사 금지)
같은 분 테무 상세에서
  · 진단(1.5.138): price=44034 KRW · gallery 12 · options 2축 · reviews 8 · rating 5 — 전부 field_sources=tier1
  · 서버 레코드: title만 생존(1/5) · price=0 · currency=USD · gallery 0 · options 미수집
탈락 집합이 **정확히 tier1 비동기 필드**였다. 갈래는 A(클릭 시점 tier1 미착지) 또는
B(payload 빌더가 진단과 다른 스토어 독출) — 둘 다 "클릭 시점에 같은 스토어를 다시 읽는다"로 덮인다.

■ 이 파일이 지키는 것
1) 단일 진입점 — 수집 payload도 진단 export도 `kgpAcquireMeta` 하나만 통과한다(별도 스냅샷 금지).
2) 재독출 — tier1 미착지면 상한 내 1회 재독출. 그 사이 도착한 tier1이 payload에 실린다.
3) 정직 강등 — 끝내 미착지면 조용한 빈 필드 대신 tier1_pending + mode:"simple".
4) 통화 무가공 — 빈 통화에 USD를 주입하지 않는다. skus[].currency 공백만 상위 통화로 채운다.
5) 읽기 전용 계측 — payload_echo / tier1 카운터 / bar_collapsed·bar_auto.

■ 인위회귀
재독출을 무력화(KGP_TIER1_TRIES=1)하면 **tier1 필드가 payload에서 탈락**해야 한다. 그게 실패하면
위 그린은 수리가 아니라 하네스가 원래 쉬웠다는 뜻이다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
BG = (EXT / "background.js").read_text(encoding="utf-8")

_REQUIRE_BROWSER = os.getenv("KGP_REQUIRE_BROWSER", "") == "1"


def _node_or_fail():
    if shutil.which("node"):
        return
    if _REQUIRE_BROWSER:
        pytest.fail("KGP_REQUIRE_BROWSER=1인데 node가 없다 — 스토어 계약이 실행되지 않는다")
    pytest.skip("node 미설치")


def _store_slice() -> str:
    """단일 스토어 블록만 떼어 낸다 — chrome API 없이 실행 가능한 순수 구간."""
    i = CS.index("// ── v86-I: 추출-저장 단일 권위 스토어")
    j = CS.index("function handleFabClick(btn, opts) {")
    src = CS[i:j]
    assert "function kgpAcquireMeta" in src, "단일 진입점을 못 찾았다"
    return src


_HARNESS = """
"use strict";
const SLICE = %(SLICE)s;
const PLAN = %(PLAN)s;          // 매 독출이 돌려줄 meta(순서대로)
const TRIES_OVERRIDE = %(TRIES)s;

let reads = 0;
function kgpExtractMerged(cb) {
  const m = PLAN[Math.min(reads, PLAN.length - 1)];
  reads++;
  setTimeout(() => cb(JSON.parse(JSON.stringify(m))), 0);
}
function kgpPageType() { return %(PT)s; }

let body = SLICE;
if (TRIES_OVERRIDE !== null) {
  // 인위회귀: 재독출을 죽인다(최초 1회만 읽음).
  body = body.replace("var KGP_TIER1_TRIES = 2;", "var KGP_TIER1_TRIES = " + TRIES_OVERRIDE + ";");
}
const api = new Function("kgpExtractMerged", "kgpPageType",
  body + "\\n;return { kgpAcquireMeta: kgpAcquireMeta, echo: _kgpPayloadEcho, store: function () { return _kgpMetaStore; } };")(
  kgpExtractMerged, kgpPageType);

api.kgpAcquireMeta(function (meta) {
  console.log("RESULT " + JSON.stringify({
    reads: reads,
    price: meta.price || "", currency: meta.currency || "",
    images_n: (meta.images || []).length, options_n: (meta.options || []).length,
    field_sources: meta.field_sources || {},
    tier1_pending: !!meta.tier1_pending, mode: meta.mode || "",
    skus: meta.skus || [],
    echo: api.echo(meta),
    store_tries: api.store().tries,
  }));
});
"""

# 1차 독출: tier1 미착지(DOM 폴백만). 2차 독출: tier1 착지(진단이 본 그 값).
_NO_TIER1 = {"title": "샘플", "price": "", "currency": "", "images": [], "options": [],
             "field_sources": {"title": "tier2", "price": "none", "images": "none", "options": "none"}}
_TIER1 = {"title": "샘플", "price": "44034", "currency": "KRW", "currency_source": "tier1",
          "images": ["https://img.kwcdn.com/product/a%d.jpg" % i for i in range(12)],
          "options": [{"name": "색상", "values": ["블랙"]}, {"name": "사이즈", "values": ["L"]}],
          "reviews": [{"text": "좋아요"}] * 8, "rating": "5",
          "skus": [{"spec": "블랙/L", "price": "44034", "currency": ""}],
          "field_sources": {"title": "tier1", "price": "tier1", "images": "tier1",
                            "options": "tier1", "reviews": "tier1"}}


def _run(plan, tries=None, page_type="single") -> dict:
    _node_or_fail()
    script = _HARNESS % {
        "SLICE": json.dumps(_store_slice()), "PLAN": json.dumps(plan),
        "TRIES": "null" if tries is None else str(tries), "PT": json.dumps(page_type),
    }
    f = tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8")
    f.write(script)
    f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        assert r.returncode == 0, r.stderr[-1500:]
        for line in r.stdout.splitlines():
            if line.startswith("RESULT "):
                return json.loads(line[len("RESULT "):])
        raise AssertionError("RESULT 없음:\n" + r.stdout[-1500:])
    finally:
        Path(f.name).unlink(missing_ok=True)


# ── 1) 클릭 시점 재독출 — 늦게 온 tier1이 payload에 실린다 ────────────────────

def test_late_tier1_is_picked_up_by_reread():
    """★핵심 — 클릭 순간엔 tier1이 없었지만 재독출에서 도착하면 payload에 실린다."""
    got = _run([_NO_TIER1, _TIER1])
    assert got["reads"] == 2, ("재독출이 일어나지 않았다", got["reads"])
    assert got["price"] == "44034", ("늦게 온 tier1 가격이 payload에 없다", got)
    assert got["images_n"] == 12 and got["options_n"] == 2, ("tier1 배열 필드 탈락", got)
    assert got["field_sources"].get("price") == "tier1"
    assert not got["tier1_pending"], ("착지했는데 pending으로 표시됐다", got)


def test_disabling_reread_reproduces_the_field_loss():
    """★인위회귀 — 재독출을 죽이면 **정확히 오너가 본 탈락**(price 0·gallery 0·options 0)이 재현된다."""
    got = _run([_NO_TIER1, _TIER1], tries=1)
    assert got["reads"] == 1, ("재독출을 안 죽였다", got["reads"])
    assert got["price"] == "" and got["images_n"] == 0 and got["options_n"] == 0, \
        ("재독출을 죽였는데도 값이 실렸다 — 이 계약이 지키는 게 없다", got)
    assert got["tier1_pending"] and got["mode"] == "simple", \
        ("탈락했는데 정직 강등 표시가 없다 — 조용한 빈 필드 전송", got)


def test_first_read_hit_does_not_wait():
    """이미 착지해 있으면 재독출로 사용자를 세워두지 않는다(상한은 지연이지 비용이 아니다)."""
    got = _run([_TIER1])
    assert got["reads"] == 1, ("착지했는데 또 읽었다", got)
    assert got["price"] == "44034" and not got["tier1_pending"]


def test_list_page_does_not_wait_for_tier1():
    """목록에선 tier1이 원래 안 온다 — 대기 0(수집 체감 지연을 만들지 않는다)."""
    got = _run([_NO_TIER1, _TIER1], page_type="list")
    assert got["reads"] == 1, ("목록에서도 재독출로 지연을 만들었다", got)
    assert got["tier1_pending"] and got["mode"] == "simple", ("목록 payload가 정직 강등되지 않았다", got)


# ── 2) 끝내 미착지 — 조용한 빈 필드 대신 정직 강등 ──────────────────────────

def test_never_landing_is_downgraded_not_silent():
    got = _run([_NO_TIER1, _NO_TIER1])
    assert got["reads"] == 2, ("상한까지 재시도하지 않았다", got)
    assert got["tier1_pending"] is True and got["mode"] == "simple"
    assert got["echo"]["tier1_pending"] is True, ("echo에 pending이 안 실렸다", got["echo"])


# ── 3) 통화 무가공 운반 ────────────────────────────────────────────────────

def test_currency_is_carried_raw_never_defaulted():
    """빈 통화에 USD를 주입하지 않는다 — 임의 통화는 원화 상품을 달러로 둔갑시킨다."""
    got = _run([_NO_TIER1, _NO_TIER1])
    assert got["currency"] == "", ("빈 통화에 기본값이 주입됐다", got["currency"])
    assert "USD" not in json.dumps(got["echo"]), ("echo에 USD가 날조됐다", got["echo"])


def test_sku_currency_filled_from_parent():
    """잔결함 칩 — 상위가 KRW인데 skus[0].currency가 공백이면 상위 통화로 채운다."""
    got = _run([_TIER1])
    assert got["skus"], ("sku가 사라졌다", got)
    assert got["skus"][0]["currency"] == "KRW", ("SKU 통화 공백이 그대로다", got["skus"])


def test_no_usd_default_in_extension_sources():
    """소스계약 — 확장 어디에도 빈 통화 → USD 기본값 주입이 없다."""
    assert 'getMeta("product:price:currency") || "USD"' not in BG, \
        "background.js가 여전히 USD 기본값을 주입한다"
    for name, src in (("content_script.js", CS), ("background.js", BG)):
        assert 'currency || "USD"' not in src and "currency, 'USD'" not in src, \
            f"{name}에 통화 기본값 주입이 남아 있다"


# ── 4) 단일 스토어 — 수집과 진단이 같은 진입점을 쓴다 ────────────────────────

def test_collect_and_diag_share_one_entry_point():
    """★별도 스냅샷·중복 직렬화 경로 금지 — 두 경로 모두 kgpAcquireMeta만 통과한다."""
    assert CS.count("function kgpAcquireMeta") == 1, "단일 진입점이 여럿이다"
    # 경계는 **줄머리 선언**으로 잡는다 — 그냥 "function "으로 자르면 본문의
    #   `typeof x === "function"` 에서 끊겨 계약이 헛돈다(실제로 그렇게 헛돌았다).
    fab = CS.split("function handleFabClick", 1)[1].split("\nfunction ", 1)[0]
    assert "kgpAcquireMeta(function (meta)" in fab, "수집 클릭이 단일 스토어를 안 쓴다"
    assert "kgpExtractMerged(function (meta)" not in fab, "수집이 스토어를 우회해 직접 추출한다"
    diag = CS.split('msg.action === "kgpDiagBundle"', 1)[1].split("return true;", 1)[0]
    assert "kgpAcquireMeta(function (_authMeta)" in diag, "진단 export가 단일 스토어를 안 쓴다"
    assert "window.kgpExtractProduct(" not in diag, "진단이 별도 추출 경로를 유지한다"


def test_reread_bound_is_explicit():
    """대기는 **상한이 명시**돼야 한다 — 무한 대기는 사용자를 세워두는 결함이다."""
    assert "var KGP_TIER1_WAIT_MS = " in CS and "var KGP_TIER1_TRIES = " in CS
    seg = CS.split("var KGP_TIER1_TRIES = ", 1)[1][:6]
    assert int(seg.split(";")[0]) <= 3, "재독출 상한이 과도하다"


# ── 5) 읽기 전용 계측 ──────────────────────────────────────────────────────

def test_diag_carries_payload_echo():
    """진단에 마지막 전송 payload 요약 — '추출은 됐는데 전송이 빔'을 진단만으로 가른다."""
    assert "payload_echo:" in CS, "진단 응답에 payload_echo가 없다"
    assert "_kgpMetaStore.echo = _kgpPayloadEcho(meta)" in CS, "전송 시점에 echo를 안 남긴다"
    seg = CS.split("function _kgpPayloadEcho", 1)[1].split("\n}", 1)[0]
    for k in ("has_title", "has_price", "currency", "images_n", "options_n", "reviews_n", "tier1_pending"):
        assert k in seg, f"echo에 {k} 누락"


def test_diag_carries_tier1_counters_and_bar_state():
    """계측 사각 2건 동봉(읽기 전용·로직 변경 0)."""
    assert "detection.tier1 = {" in CS, "tier1 카운터가 진단 본문에 없다"
    seg = CS.split("detection.tier1 = {", 1)[1][:400]
    for k in ("seen:", "hits:", "goods_ids_n:"):
        assert k in seg, f"tier1 계측에 {k} 누락"
    assert "_ui.bar_collapsed = !!_kgpClosed;" in CS, "접힘 상태 계측 누락"
    assert "_ui.bar_auto = kgpLSget(" in CS, "자동/수동 토글 계측 누락"


def test_echo_is_read_only():
    """echo는 **기록만** 한다 — 진단이 payload를 바꾸면 그 진단은 증거가 아니다."""
    seg = CS.split('msg.action === "kgpDiagBundle"', 1)[1].split("return true;", 1)[0]
    assert "_kgpMetaStore.echo =" not in seg, "진단 경로가 echo를 덮어쓴다"
