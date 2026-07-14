"""tests/test_v70_default_sites_parity.py — v70 STEP4: 디폴트 소싱처 전수 버튼 보장.

오너 최우선: 수집 버튼이 테무·아마존 외 디폴트 소싱처에서 전멸(요시다 등 회귀 의심).
근원: kgpIsDefaultSourcing이 드리프트한 정규식(KGP_DEFAULT_SRC_RE) 단독 → 요시다/아이허브/
DHgate/큐텐이 결정적 페이지 판정에서 누락. 수리: 레지스트리(KGP_DEFAULT_SOURCES) 단일 소스로 봉인 +
서버 레지스트리 상수/가이드 문서 명문화(가드가 id 일치 강제).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


# ── 레지스트리 파리티(서버 ↔ 확장) ──
def test_registry_parity_server_matches_extension():
    from src.collectors.sourcing_registry import registry_ids
    ext_ids = re.findall(r'\{\s*id:\s*"([a-z0-9]+)"', CS.split("const KGP_DEFAULT_SOURCES")[1].split("];")[0])
    assert ext_ids, "확장 KGP_DEFAULT_SOURCES id 추출 실패"
    assert registry_ids() == ext_ids, (registry_ids(), ext_ids)   # 순서·집합 일치(드리프트 0)


def test_default_sourcing_derives_from_registry():
    # 레지스트리 순회 백스톱(정규식 드리프트 무효화).
    assert "for (let i = 0; i < KGP_DEFAULT_SOURCES.length; i++) { if (KGP_DEFAULT_SOURCES[i].test(host)) return true; }" in CS
    # 정규식도 누락 도메인 보강(yoshida·iherb·dhgate·qoo10).
    for dom in ("yoshidakaban", "iherb", "dhgate", "qoo10"):
        assert dom in CS.split("const KGP_DEFAULT_SRC_RE")[1].split(";")[0]


def test_generic_fallback_not_gated_by_adapter():
    # v63 원칙 보존: 어댑터 실패해도 제네릭 감지가 병합되어 버튼 보장(폴백 차단 구조 0).
    assert "function _kgpMergeCards" in CS
    # kgpFindCards는 제네릭을 먼저 돌리고 어댑터는 보강.
    seg = CS.split("function kgpFindCards")[1].split("\n}")[0]
    assert "generic = _kgpGenericCards()" in seg
    assert "_kgpMergeCards(generic, adapter)" in seg


# ── 서버 가이드 라우트 ──
def test_guide_sources_route_renders(flask_client):
    from src.collectors.sourcing_registry import DEFAULT_SOURCING_SITES
    r = flask_client.get("/seller/guide/sources")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for s in DEFAULT_SOURCING_SITES:
        assert s["label"] in html   # 전 사이트 렌더
    assert "소싱처 관리" in html      # 미지원 사이트 직접 추가 정직 안내


# ── 버튼 보장 스모크(node): 레지스트리 전 사이트 × host 허용 + 결정적 판정 ──
REGISTRY_HOSTS = [
    ("taobao", "item.taobao.com"),
    ("tmall", "detail.tmall.com"),
    ("1688", "detail.1688.com"),
    ("temu", "www.temu.com"),
    ("amazon", "www.amazon.com"),
    ("amazon-jp", "www.amazon.co.jp"),
    ("aliexpress", "www.aliexpress.com"),
    ("iherb", "www.iherb.com"),
    ("dhgate", "www.dhgate.com"),
    ("qoo10", "www.qoo10.jp"),
    ("mercari", "www.mercari.com"),
    ("rakuten", "item.rakuten.co.jp"),
    ("yahoo", "shopping.yahoo.co.jp"),
    ("yoshida", "www.yoshidakaban.com"),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_all_registry_sites_allowed_and_deterministic_node():
    def const(name):
        m = re.search(r"const " + name + r" = (/.*?/i);", CS)
        assert m, name
        return m.group(1)

    def arr():
        m = re.search(r"const KGP_DEFAULT_SOURCES = (\[.*?\n\]);", CS, re.S)
        assert m, "KGP_DEFAULT_SOURCES"
        return m.group(1)

    def fn(name):
        m = re.search(r"function " + name + r"\([^)]*\) \{.*?\n\}", CS, re.S)
        assert m, name
        return m.group(0)

    hosts_js = ",".join('["%s","%s"]' % (i, h) for i, h in REGISTRY_HOSTS)
    harness = "\n".join([
        "const KGP_DEFAULT_SOURCES = " + arr() + ";",
        "const KGP_DEFAULT_SRC_RE = " + const("KGP_DEFAULT_SRC_RE") + ";",
        "const KGP_DETAIL_URL_RE = " + const("KGP_DETAIL_URL_RE") + ";",
        "let KGP_SOURCES = {};",
        "function kgpEntrySession(){ return false; }",
        fn("_kgpHostMatch"),
        fn("kgpHostAllowed"),
        fn("kgpIsDefaultSourcing"),
        r"""
const HOSTS = [""" + hosts_js + r"""];
let bad = [];
HOSTS.forEach(function(pair){
  const host = pair[1];
  global.location = { hostname: host, search: "" };
  const allowed = kgpHostAllowed();
  const isDflt = kgpIsDefaultSourcing();
  // 결정적 판정: 상세 URL → single, 목록/루트 → list (unknown 금지).
  const detail = "https://" + host + "/products/item123";
  const listu  = "https://" + host + "/";
  const dPt = isDflt ? (KGP_DETAIL_URL_RE.test(detail) ? "single" : "list") : "heuristic";
  const lPt = isDflt ? (KGP_DETAIL_URL_RE.test(listu) ? "single" : "list") : "heuristic";
  if (!allowed || !isDflt || dPt !== "single" || lPt !== "list") {
    bad.push({ site: pair[0], host: host, allowed: allowed, isDflt: isDflt, dPt: dPt, lPt: lPt });
  }
});
// 비레지스트리 사이트는 허용 안 됨(하드 게이트 아님 — heuristic).
global.location = { hostname: "shop.random-store.com", search: "" };
const nonAllowed = kgpHostAllowed();
process.stdout.write(JSON.stringify({ bad: bad, nonAllowed: nonAllowed }) + "\n");
""",
    ])
    r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=25)
    assert r.returncode == 0, r.stderr
    import json
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["bad"] == [], out["bad"]        # 전 레지스트리 사이트 host 허용 + 결정적 판정
    assert out["nonAllowed"] is False, out     # 비레지스트리는 허용 안 됨(정직 게이트)
