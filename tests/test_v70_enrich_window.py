"""tests/test_v70_enrich_window.py — v70 STEP6: 테무 보강 소형 창 판정 회수(견고화).

브리프: 보강 소형 창(활성 창)이 실기기에서 안 뜨면 그 지점 수리가 STEP의 전부.
수리: 소형 창 생성 실패(정책·API 부재) 시 조용히 죽지 않고 백그라운드 탭으로 폴백(보강 계속) +
창은 떴는데 tabs 미포함 시 창 탭 id 조회. 테무 성공 기준(가격+갤러리≥3) 미달이면 정직 실패(POST 안 함).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.142"


def test_source_contract():
    # 소형 창 미가용/실패 → 백그라운드 탭 폴백(조용한 실패 금지).
    assert "chrome.windows && chrome.windows.create" in BG
    assert "소형 창 실패 → 백그라운드 탭 폴백" in BG
    assert "const tab = await chrome.tabs.create({ url: item.url, active: false });" in BG
    # 창은 떴는데 tabs 미포함 시 창 탭 id 조회.
    assert "chrome.tabs.query({ windowId: win.id })" in BG
    # 테무 성공 기준 미달이면 정직 실패(보강 완료 처리 안 함).
    assert "if (!verdict.ok) throw new Error(verdict.reason);" in BG
    # 창 정리(finally).
    assert "chrome.windows.remove(win.id)" in BG


def _fn(name):
    m = re.search(r"async function " + re.escape(name) + r"\([^)]*\) \{.*?\n\}", BG, re.S)
    if not m:
        m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{.*?\n\}", BG, re.S)
    assert m, name + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_enrich_window_fallback_and_gate_node():
    deps = _fn("_kgpEnrichVerdict") + "\n" + _fn("_kgpEnrichOne")
    harness = deps + "\n" + r"""
var calls = {};
function reset(){ calls = { winCreate:0, winRemove:0, tabCreate:0, tabCreateActive:null, tabRemove:0, fetch:0 }; }
var WIN_THROWS = false, META = {};
global.chrome = {
  windows: {
    create: async function(o){ calls.winCreate++; if (WIN_THROWS) throw new Error("policy"); return { id:1, tabs:[{id:11}] }; },
    remove: async function(id){ calls.winRemove++; }
  },
  tabs: {
    create: async function(o){ calls.tabCreate++; calls.tabCreateActive = o.active; return { id:22 }; },
    query: async function(){ return [{ id:11 }]; },
    remove: async function(){ calls.tabRemove++; }
  }
};
global.KgpEnrich = { current: null };
function _kgpBroadcastEnrich(){}
async function _kgpWaitTabComplete(){}
async function _kgpSendTab(){ return META; }
global.fetch = async function(){ calls.fetch++; return { ok:true, json: async function(){ return { ok:true }; } }; };
global.console = { warn: function(){}, log: function(){}, error: function(){} };
var S = { enrichMode:"window", serverUrl:"http://x", token:"t" };

(async function(){
  var out = {};
  // A: 소형 창 성공(비테무) → 창 사용, POST, 창 정리.
  reset(); WIN_THROWS = false; META = { price:"29.99", images:["a","b","c"], options:[] };
  await _kgpEnrichOne({ url:"https://www.amazon.com/dp/X", item_id:"1" }, S);
  out.A = JSON.parse(JSON.stringify(calls));
  // B: 소형 창 실패 → 백그라운드 탭 폴백(active:false), POST, 탭 정리.
  reset(); WIN_THROWS = true; META = { price:"29.99", images:["a","b","c"] };
  await _kgpEnrichOne({ url:"https://www.amazon.com/dp/X", item_id:"1" }, S);
  out.B = JSON.parse(JSON.stringify(calls));
  // C: 테무 게이트 미달(갤러리 2) → 정직 실패(POST 안 함), 창 정리.
  reset(); WIN_THROWS = false; META = { price:"", images:["a","b"] };
  var threw = false;
  try { await _kgpEnrichOne({ url:"https://www.temu.com/x-g-1.html", item_id:"1" }, S); } catch(e){ threw = true; }
  out.C = JSON.parse(JSON.stringify(calls)); out.C.threw = threw;
  process.stdout.write(JSON.stringify(out) + "\n");
})();
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    # A: 창 성공 → 창 사용·POST·창 정리, 탭 폴백 없음.
    assert out["A"] == {"winCreate": 1, "winRemove": 1, "tabCreate": 0, "tabCreateActive": None, "tabRemove": 0, "fetch": 1}, out["A"]
    # B: 창 실패 → 백그라운드 탭 폴백(active:false)·POST·탭 정리, 창 remove 없음.
    assert out["B"]["winCreate"] == 1 and out["B"]["tabCreate"] == 1, out["B"]
    assert out["B"]["tabCreateActive"] is False, out["B"]
    assert out["B"]["fetch"] == 1 and out["B"]["tabRemove"] == 1 and out["B"]["winRemove"] == 0, out["B"]
    # C: 테무 게이트 미달 → 정직 실패(POST 0), 창 정리.
    assert out["C"]["threw"] is True and out["C"]["fetch"] == 0, out["C"]
    assert out["C"]["winCreate"] == 1 and out["C"]["winRemove"] == 1, out["C"]
