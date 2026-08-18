"""tests/test_v86_k_tier1_adopted.py — v86-K: tier1_diag adopted 블록(읽기 전용 계측).

오너 실기기(테무 1.5.140): top 후보=추천 캐러셀 goods_detail_like(goods_id 605155487520667=필립스
멀티탭, goods_matched=false)가 최고점인데도 채택 안 됨 = 방어 실작동. 종전 진단은 top만 실어
'무엇이 채택됐나'를 못 봤다. adopted 블록으로 top≠adopted(방어 작동)를 진단만으로 판독.

금지 준수: 선택 로직·kgp-net.js 스코프 무변경. adopted는 extractor가 세팅한 전역 역판독(관찰만).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

NET = Path("extensions/chrome-collector/kgp-net.js").read_text(encoding="utf-8")
MAIN = Path("extensions/chrome-collector/kgp-main.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.149"


# ── source-contract: 읽기 전용 계측, 선택 로직 무변경 ──
def test_adopted_reader_is_readonly_instrumentation():
    assert "window.__kgpAdoptedCandidate = function ()" in NET
    # extractor 전역 역판독만(값 대입 0 — 선택 경로에 안 씀).
    body = NET.split("window.__kgpAdoptedCandidate = function ()")[1].split("window.__kgpDiagRows")[0]
    for g in ("__kgpTier1Url", "__kgpTier1Mismatch", "__kgpTier1Score", "__kgpNetBound", "__kgpCaptured"):
        assert g in body, f"{g} 역판독 누락"
    assert re.search(r"__kgpTier1Url\s*=", body) is None, "adopted 리더가 tier1 전역에 대입(선택 로직 변경 금지 위반)"
    # 채택/기각 enum(빈 문자열 금지) 6종 명시.
    for enum in ("adopted:id_match", "adopted:top_score", "rejected:id_mismatch",
                 "rejected:no_capture", "rejected:score", "rejected:not_injected"):
        assert enum in body, f"adopt_cause enum 누락: {enum}"
    # kgp-main 브릿지 + content_script 진단 노출.
    assert "diag.adopted = (typeof window.__kgpAdoptedCandidate" in MAIN
    assert "adopted: diag.adopted || null," in CS


# ── node 하네스: 채택/기각 판독(오너 실기기 시나리오 포함) ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_adopted_reads_match_and_defense_rejection():
    m = re.search(r"window\.__kgpAdoptedCandidate = function \(\) \{[\s\S]*?\n  \};", NET)
    assert m, "리더 추출 실패"
    harness = "global.window=global;\n" + m.group(0) + r"""
    function run(setup){ setup(); return window.__kgpAdoptedCandidate(); }
    var out = {};
    // ① id_match 채택
    out.match = run(function(){
      window.__kgpNetBound=true;
      window.__kgpCaptured=[{url:'u/mine?id=999',score:4,price:true,images:true,sku:true,reviews:true,goods_id:'999'}];
      window.__kgpPageGoodsId=function(){return '999';};
      window.__kgpTier1Url='u/mine?id=999'; window.__kgpTier1Score=4; window.__kgpTier1Mismatch=false;
    });
    // ② 오너 실기기: top=추천 캐러셀(고점)인데 id 불일치 → 기각(adopted=false)
    out.defense = run(function(){
      window.__kgpNetBound=true;
      window.__kgpCaptured=[{url:'u/reco?id=605155487520667',score:3,price:false,images:true,sku:false,reviews:false,goods_id:'605155487520667'}];
      window.__kgpPageGoodsId=function(){return '111';};
      window.__kgpTier1Url=''; window.__kgpTier1Score=0; window.__kgpTier1Mismatch=true;
    });
    // ③ 미주입
    out.noinject = run(function(){ window.__kgpNetBound=false; window.__kgpTier1Url=''; });
    console.log(JSON.stringify(out));
    """
    r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout.strip())
    # ① 채택 — id 일치, 기여 필드 전부.
    assert o["match"]["adopted"] is True and o["match"]["adopt_cause"] == "adopted:id_match"
    assert o["match"]["goods_matched"] is True and o["match"]["price"] and o["match"]["sku"]
    # ② 방어 — 고점 top인데 채택 안 됨(adopted=false), 사유 enum 명시(빈 문자열 아님).
    assert o["defense"]["adopted"] is False and o["defense"]["adopt_cause"] == "rejected:id_mismatch"
    assert o["defense"]["adopt_cause"] != ""
    # ③ 미주입 사유.
    assert o["noinject"]["adopt_cause"] == "rejected:not_injected"
