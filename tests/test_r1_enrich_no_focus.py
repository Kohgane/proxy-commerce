"""R1(오너 2026-10-01 「컴터에 자꾸 고가브릿지 수집 창이 계속 뜬다」) — 보강은 화면에 창을 띄우지 않고 포커스를 뺏지 않는다.

## 실측(코드 + 운영 읽기 전용)
- 기본 모드 `window` → 보강 1건마다 `chrome.windows.create({type:"popup",480×640,focused:false})` — **보이는 창**.
  (`tab-activate` 모드는 `active:true`로 탭 포커스까지 뺏었다.)
- 트리거: `alarms` 5분 + **콘솔 탭이 로드될 때마다** 대기 목록 폴링 → 큐(동시 1탭) → 항목 사이 2~3초.
- 운영 대기(`enrich_state=pending`) **21건 전부 시도 0회**(09-30 이후 갱신 없음). 확장은 실패를 **3번째**에서야
  서버에 적었는데 MV3 워커가 그 전에 내려가면 기록이 안 남아, 같은 21건을 5분마다 다시 열었다 = 「계속 뜬다」.

## 계약
  1 소스: 보이는 창(popup)·`active:true`·`focused:true`·`windows.update`·`tabs.update(active)` 0 · 기본 = 최소화 창
  2 node: 최소화 창으로 열고 **추출 직후·서버 저장 전에 닫는다** · 창 실패면 `active:false` 탭 · 옛 설정값도 최소화
  3 node: 실패마다 서버에 기록(시도 수는 서버가 셈) — 서버가 `blocked`라 하면 재시도 안 함 · 1시간 멈춤이면 큐가 손 뗌
  4 실브라우저(확장 로드): 작업 탭을 연 채 보강 2건 → **포커스 변경 0 · 탭 활성 변경 0 · 보이는 창 0**,
     작업 탭이 끝까지 활성 · 보강 탭은 다 닫힘 · 보강 저장 2건
  5 팝업: 「보강 잠시 멈춤(1시간)」 토글 + 진행 수
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

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
PH = Path("extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
PJ = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
EXT_JS = [Path(p).read_text(encoding="utf-8") for p in glob.glob("extensions/chrome-collector/*.js")]


def test_source_never_shows_or_focuses():
    allsrc = "\n".join(EXT_JS)
    assert 'type: "popup"' not in allsrc                                  # 보이는 소형 창 0
    assert not re.search(r"focused:\s*true", allsrc)
    assert not re.search(r"tabs\.create\(\{[^}]*active:\s*(true|\(mode)", allsrc)
    assert "chrome.windows.update(" not in allsrc
    assert not re.search(r"tabs\.update\([^)]*active", allsrc)
    assert 'chrome.windows.create({ url: url, state: "minimized", focused: false })' in BG
    assert 'kgp_enrich_mode || "background"' in BG


def _fn(name):
    m = re.search(r"(?:async )?function " + re.escape(name) + r"\([^)]*\) \{.*?\n\}", BG, re.S)
    assert m, name
    return m.group(0)


def _grab(sig, end="\n}"):
    i = BG.index(sig)
    return BG[i:BG.index(end, i) + len(end)]


def _node(js):
    f = tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8")
    f.write(js); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_open_minimized_and_close_before_save_node():
    deps = "\n".join(_fn(n) for n in ("_kgpEnrichVerdict", "_kgpEnrichBody", "_kgpEnrichModeOf",
                                      "_kgpOpenHidden", "_kgpCloseHidden", "_kgpEnrichOne"))
    out = _node(deps + r"""
var log = [], WIN_THROWS = false;
global.chrome = {
  windows: { create: async function(o){ log.push("win:" + JSON.stringify(o)); if (WIN_THROWS) throw new Error("x"); return { id: 1, tabs: [{ id: 11 }] }; },
             remove: async function(){ log.push("winRemove"); } },
  tabs: { create: async function(o){ log.push("tab:" + JSON.stringify(o)); return { id: 22 }; },
          query: async function(){ return [{ id: 11 }]; }, remove: async function(){ log.push("tabRemove"); } } };
global.KgpEnrich = { current: "" };
function _kgpBroadcastEnrich(){}
async function _kgpWaitTabComplete(){}
async function _kgpSendTab(){ log.push("extract"); return { price: "9.9", images: ["a"] }; }
global.fetch = async function(u){ log.push("save"); return { ok: true, json: async function(){ return { ok: true }; } }; };
global.console = { warn(){}, log(){}, error(){} };
(async function(){
  var out = {};
  for (const mode of ["window", "tab-activate", "minimized", undefined]) {
    log = []; await _kgpEnrichOne({ url: "https://www.amazon.com/dp/X", item_id: "1" }, { enrichMode: mode, serverUrl: "h", token: "t" });
    out[String(mode)] = log.slice();
  }
  log = []; await _kgpEnrichOne({ url: "https://www.amazon.com/dp/X", item_id: "1" }, { enrichMode: "background", serverUrl: "h", token: "t" });
  out.background = log.slice();
  log = []; WIN_THROWS = true; await _kgpEnrichOne({ url: "https://www.amazon.com/dp/X", item_id: "1" }, { enrichMode: "minimized", serverUrl: "h", token: "t" });
  log = log.filter(x => !x.startsWith("win:"));
  out.fallback = log.slice();
  process.stdout.write(JSON.stringify(out) + "\n");
})();
""")
    win = 'win:{"url":"https://www.amazon.com/dp/X","state":"minimized","focused":false}'
    tab = 'tab:{"url":"https://www.amazon.com/dp/X","active":false}'
    for mode in ("window", "tab-activate", "undefined"):                      # 기본·옛 값 = 백그라운드 탭
        assert out[mode] == [tab, "extract", "tabRemove", "save"], (mode, out[mode])   # 닫고 나서 저장
    assert out["background"] == [tab, "extract", "tabRemove", "save"]
    assert out["minimized"] == [win, "extract", "winRemove", "save"]         # 고른 사람만 최소화 창
    assert out["fallback"] == [tab, "extract", "tabRemove", "save"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_every_failure_is_reported_and_server_decides_retry_node():
    kgp = _grab("const KgpEnrich = {", "};")
    out = _node(kgp + "\n" + _fn("_kgpEnrichSnapshot") + "\n" + _fn("_kgpBroadcastEnrich") + "\n"
                + _fn("_kgpEnrichLoop") + "\n" + r"""
var chrome = { runtime: { sendMessage(){} } };
var KGP_ENRICH_MAX_RETRIES = 3;
async function getSettings(){ return {}; }
function _kgpSleep(){ return Promise.resolve(); }
function _kgpEnrichDelayMs(){ return 0; }
var PAUSED = 0, opens = 0, reports = [];
async function _kgpPausedUntil(){ return PAUSED; }
async function _kgpEnrichOne(){ opens++; throw new Error("상세 추출 실패(빈 응답)"); }
var att = 0;
async function _kgpReportBlocked(item, reason){ att++; reports.push(reason); return { attempts: att, state: att >= 3 ? "blocked" : "pending" }; }
(async function(){
  KgpEnrich.queue.push({ item_id: "a", url: "u" }); KgpEnrich.total = 1;
  await _kgpEnrichLoop();
  var r1 = { opens, reports: reports.length, failed: KgpEnrich.failed, running: KgpEnrich.running };
  // 1시간 멈춤 — 큐가 있어도 열지 않는다
  opens = 0; PAUSED = Date.now() + 3600000; KgpEnrich.queue.push({ item_id: "b", url: "u" });
  await _kgpEnrichLoop();
  process.stdout.write(JSON.stringify({ r1, pausedOpens: opens, left: KgpEnrich.queue.length }) + "\n");
})();
""")
    assert out["r1"] == {"opens": 3, "reports": 3, "failed": 1, "running": False}, out   # 실패마다 기록 · 서버 상한에서 끝
    assert out["pausedOpens"] == 0 and out["left"] == 1                                  # 멈춤 = 창 0, 큐는 남김


def test_popup_pause_toggle_and_progress():
    assert 'id="enrichPause1h"' in PH and "보강 잠시 멈춤(1시간)" in PH and 'data-role="enrich-progress"' in PH
    assert "kgp_enrich_pause_until" in PJ and "60 * 60 * 1000" in PJ
    assert '"진행 " + snap.done + "/" + snap.total' in PJ
    assert 'value="window"' not in PH and 'value="tab-activate"' not in PH
    assert "_kgpPausedUntil()" in BG and "KGP_ENRICH_POLL_GAP_MS" in BG


# ── 실브라우저(확장 로드): 포커스 변경 0 ─────────────────────────────────────
def _pw_exe():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return hits[0] if hits else None


def _browser_ready():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if _pw_exe():
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


_PDP = ('<!doctype html><html><head><meta charset=utf-8><title>R1 상품</title>'
        '<meta property="og:title" content="R1 상품">'
        '<meta property="product:price:amount" content="19.99"><meta property="product:price:currency" content="USD">'
        '</head><body><h1 id="productTitle">R1 상품</h1><span class="a-price"><span class="a-offscreen">$19.99</span></span>'
        '</body></html>')


def _serve(saved):
    """작업 탭·상품 상세·서버 API를 한 로컬 서버로. (Playwright route는 **확장이 연 탭**엔 안 걸린다 — 실측.)"""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body, ctype="text/html; charset=utf-8"):
            b = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path.startswith("/work"):
                self._send("<!doctype html><title>작업 중</title><textarea>오너가 쓰는 중</textarea>")
            elif self.path.startswith("/dp/"):
                self._send(_PDP)
            else:
                self._send('{"ok":true,"items":[]}', "application/json")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path.endswith("/api/v1/collect/enrich"):
                saved.append(body.get("item_id"))
            self._send('{"ok":true,"state":"blocked"}', "application/json")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _run_enrich(mode):
    """확장을 실로드하고, 작업 탭을 연 채로 보강 2건을 돌린 뒤 이벤트를 잰다."""
    from playwright.sync_api import sync_playwright

    ext = os.path.abspath("extensions/chrome-collector")
    saved = []
    srv, base = _serve(saved)
    work_url, items = base + "/work", [base + "/dp/B0R1TEST01", base + "/dp/B0R1TEST02"]
    try:
        with sync_playwright() as pw:
            kw = {"headless": True,
                  "args": [f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--headless=new"]}
            if _pw_exe():
                kw["executable_path"] = _pw_exe()
            ctx = pw.chromium.launch_persistent_context(tempfile.mkdtemp(), **kw)
            try:
                work = ctx.pages[0] if ctx.pages else ctx.new_page()
                sw = None
                for _ in range(40):
                    if ctx.service_workers:
                        sw = ctx.service_workers[0]
                        break
                    work.wait_for_timeout(200)
                if sw is None:
                    return None
                sw.evaluate("(a) => chrome.storage.local.set({token:'QA-R1', serverUrl:a[0], kgp_enrich_mode:a[1]})",
                            [base, mode])
                work.goto(work_url)
                work.bring_to_front()
                for extra in list(ctx.pages):
                    if extra != work:
                        extra.close()
                before = sw.evaluate("""async () => {
                    globalThis.__r1 = { focus: [], activated: [], created: [] };
                    chrome.windows.onFocusChanged.addListener(id => __r1.focus.push(id));
                    chrome.tabs.onActivated.addListener(i => __r1.activated.push(i.tabId));
                    chrome.windows.onCreated.addListener(w => __r1.created.push({ state: w.state, focused: w.focused }));
                    const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
                    return { activeUrl: t && t.url, tabs: (await chrome.tabs.query({})).length };
                }""")
                sw.evaluate("(urls) => handleEnrichStart(urls.map((u, i) => ({ item_id: 'r1-' + i, url: u })), null)", items)
                for _ in range(150):                                       # 최대 ~75초
                    if not sw.evaluate("() => KgpEnrich.running"):
                        break
                    work.wait_for_timeout(500)
                after = sw.evaluate("""async () => {
                    const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
                    return { r1: __r1, activeUrl: t && t.url, tabs: (await chrome.tabs.query({})).length,
                             wins: (await chrome.windows.getAll()).map(w => w.state), snap: _kgpEnrichSnapshot() };
                }""")
            finally:
                ctx.close()
    finally:
        srv.shutdown()
    return {"work": work_url, "before": before, "after": after, "saved": saved}


def _need_browser():
    if not _browser_ready():
        if os.environ.get("KGP_REQUIRE_BROWSER") == "1":
            pytest.fail("KGP_REQUIRE_BROWSER=1 인데 playwright/chromium 없음")
        pytest.skip("playwright/chromium 미설치 — 실브라우저 계약 skip(정직)")


def test_real_browser_enrich_changes_no_focus():
    """기본(설정 없음 = 백그라운드 탭): 포커스 변경 0 · 탭 활성 변경 0 · 창 0 · 작업 탭 그대로 · 보강 탭 다 닫힘."""
    _need_browser()
    got = _run_enrich(None)
    if got is None:
        if os.environ.get("KGP_REQUIRE_BROWSER") == "1":
            pytest.fail("확장 서비스워커 미기동")
        pytest.skip("확장 서비스워커 미기동 — 하네스 한계(정직 skip)")
    before, after = got["before"], got["after"]
    assert before["activeUrl"] == got["work"], before
    r1 = after["r1"]
    assert r1["focus"] == [], f"포커스 변경 {len(r1['focus'])}회"
    assert r1["activated"] == [], f"탭 활성 변경 {r1['activated']}"
    assert r1["created"] == [], f"창 {len(r1['created'])}개가 열렸다"
    assert after["activeUrl"] == got["work"]                               # 작업 탭이 끝까지 활성
    assert after["tabs"] == before["tabs"] and after["wins"] == ["normal"], after   # 보강 탭 다 닫힘
    assert after["snap"]["done"] == 2 and after["snap"]["ok"] == 2 and after["snap"]["running"] is False, after["snap"]
    assert sorted(got["saved"]) == ["r1-0", "r1-1"], got["saved"]          # 보강 저장 2건(읽기는 됐다)


def test_real_browser_minimized_window_is_measured_honestly():
    """최소화 창(선택)은 화면엔 안 뜨지만 만들 때 작업 창 포커스가 잠깐 바뀐다 — 그래서 기본이 아니다(실측 고정)."""
    _need_browser()
    got = _run_enrich("minimized")
    if got is None:
        pytest.skip("확장 서비스워커 미기동 — 하네스 한계(정직 skip)")
    r1 = got["after"]["r1"]
    assert r1["created"] and all(w["state"] == "minimized" and not w["focused"] for w in r1["created"]), r1["created"]
    assert got["after"]["activeUrl"] == got["work"]                        # 작업 탭은 그대로 활성
    # 실측: 새 창마다 그 창의 탭 활성 이벤트도 난다(작업 창 탭은 아님)
    assert got["after"]["wins"] == ["normal"]                              # 다 닫힘
    assert len(r1["focus"]) > 0                                            # 포커스 이동이 있다(정직 — 팝업 문구 근거)
