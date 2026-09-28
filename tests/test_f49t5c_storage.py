"""F49-T 5부-c — 확장 저장 한도·자가진단 소음(오너 캡처 2026-09-28 14:38, detail.tmall.com 보강 탭 콘솔).

캡처: `Unchecked runtime.lastError: Resource::kQuotaBytesPerItem quota exceeded` ×2 ·
      `[고가수집기] 자가진단: 아직 상품별 JSON 응답 없음…`(kgp-main.js:42) · `contentscript.js:14088 MaxListeners/ObjectMultiplex`.

잰 것(코드):
  ① `kQuotaBytesPerItem`(8KB)은 **storage.sync 전용** 한도다. 우리 sync 사용 = 옵션 화면의 서버 주소·토큰 두 값뿐.
     큐는 서비스 워커 메모리 + 서버 대기열(5부), 진단·규칙 캐시·설정은 전부 storage.local → 그 경고는 **우리 쓰기가 아니다**.
     (같은 시각 백필은 정상 13·대기 21로 진행 중 — 오너 14:43 실측)
  ② 5부 「워커 재시작 시 큐 소실」과 같은 원인이 아니다 — 큐는 storage에 없었다(메모리).
  ③ 그래도 우리 쓰기 실패가 「Unchecked」로 흘러가지 않게 `lastError`를 잡아 진단(`storage_err`)에 싣는다.
  ④ 자가진단 문구는 응답 가로채기(kgp-net)가 주입되는 **테무에서만**. 그 밖에선 침묵.
  ⑤ `contentscript.js`·ObjectMultiplex는 우리 파일·코드에 없다(지갑류 확장 라이브러리).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
JS = {p.name: p.read_text(encoding="utf-8") for p in EXT.glob("*.js")}
node = pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")


def _run_node(src: str) -> dict:
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


FAKE_CHROME = r"""
const store = { sync: {}, local: {} };
let failLocal = false;
function mk(area) {
  return {
    set(obj, cb) {
      let err = null;
      if (area === "sync") for (const k in obj) if (JSON.stringify({[k]: obj[k]}).length > 8192) err = { message: "Resource::kQuotaBytesPerItem quota exceeded" };
      if (area === "local" && failLocal) err = { message: "QUOTA_BYTES quota exceeded" };
      if (!err) Object.assign(store[area], obj);
      if (cb) { chrome.runtime.lastError = err; cb(); chrome.runtime.lastError = null; return; }
      return err ? Promise.reject(new Error(err.message)) : Promise.resolve();
    },
  };
}
globalThis.chrome = { runtime: { lastError: null }, storage: { sync: mk("sync"), local: mk("local") } };
"""


def _fn(src: str, name: str) -> str:
    m = re.search(r"(?:async )?function " + name + r"\(.*?\n\}", src, re.S)
    assert m, name
    return m.group(0)


def test_sync_holds_only_server_url_and_token():
    uses = [(n, ln.strip()) for n, s in JS.items() for ln in s.splitlines() if "storage.sync" in ln]
    assert {n for n, _ in uses} <= {"background.js", "options.js"}, uses
    for n, ln in uses:
        if ".set(" in ln:
            assert n == "options.js" and "chrome.storage.sync.set(settings" in ln, ln
        else:
            assert '"serverUrl", "token"' in ln, ln
    # 옵션 화면이 sync에 넣는 값은 서버 주소·토큰 둘뿐이다.
    body = JS["options.js"]
    calls = re.findall(r"writeSettings\((\{[^}]*\})", body)
    assert calls and all(set(re.findall(r"(\w+)\s*:", c)) <= {"serverUrl", "token"} for c in calls), calls


def test_no_direct_unchecked_writes_left():
    # content_script·popup·background의 쓰기는 래퍼를 지난다(래퍼 본문 한 곳씩만 직접 호출).
    assert JS["content_script.js"].count("chrome.storage.local.set(") == 1
    assert JS["popup.js"].count("chrome.storage.local.set(") == 1
    assert JS["background.js"].count("chrome.storage.local.set(") == 1
    assert JS["content_script.js"].count("kgpStoreLocal(") >= 3 and JS["popup.js"].count("kgpPopupSet(") >= 5
    assert JS["background.js"].count("kgpLocalSet(") >= 3


@node
def test_big_payload_goes_to_local_not_sync_and_failures_are_recorded():
    cs = JS["content_script.js"]
    const = re.search(r"const KGP_STORAGE_ERR = \{[^;]*\};", cs).group(0)
    src = FAKE_CHROME + const + "\n" + _fn(cs, "kgpStoreLocal") + r"""
const big = { kgp_rules: { rules: "x".repeat(20000) } };
kgpStoreLocal(big);
const ok = { local: JSON.stringify(store.local).length, sync: Object.keys(store.sync).length, err: KGP_STORAGE_ERR.count };
failLocal = true;
kgpStoreLocal({ kgp_translate: true });
console.log(JSON.stringify({ ok, after: KGP_STORAGE_ERR }));
"""
    out = _run_node(src)
    assert out["ok"]["local"] > 20000 and out["ok"]["sync"] == 0 and out["ok"]["err"] == 0
    assert out["after"]["count"] == 1 and out["after"]["last"]["keys"] == "kgp_translate"
    assert "quota" in out["after"]["last"]["msg"]


@node
def test_background_write_failure_is_not_swallowed():
    bg = JS["background.js"]
    const = re.search(r"const KgpStorageErr = \{[^;]*\};", bg).group(0)
    src = FAKE_CHROME + const + "\n" + _fn(bg, "kgpLocalSet") + r"""
(async () => {
  const a = await kgpLocalSet({ kgp_rules: { rules: "y".repeat(30000) } });
  failLocal = true;
  const b = await kgpLocalSet({ kgp_update: { latest: "9" } });
  console.log(JSON.stringify({ a, b, n: KgpStorageErr.count, keys: KgpStorageErr.last.keys, sync: Object.keys(store.sync).length }));
})();
"""
    out = _run_node(src)
    assert out == {"a": True, "b": False, "n": 1, "keys": "kgp_update", "sync": 0}


def test_page_diag_carries_storage_errors_and_server_keeps_them():
    cs = JS["content_script.js"]
    assert "if (KGP_STORAGE_ERR.count) out.storage_err = { count: KGP_STORAGE_ERR.count, last: KGP_STORAGE_ERR.last };" in cs
    from src.collectors.collect_status import clean_page_diag
    d = clean_page_diag({"storage_err": {"count": "2", "last": {"keys": "kgp_rules", "msg": "quota", "at": "t", "evil": 1}}})
    assert d["storage_err"] == {"count": 2, "last": {"keys": "kgp_rules", "msg": "quota", "at": "t"}}
    assert "storage_err" not in clean_page_diag({"lazy": {"total": 1}})


@node
@pytest.mark.parametrize("with_net,expect", [(False, 0), (True, 1)])
def test_self_diagnosis_is_silent_where_nothing_is_intercepted(with_net, expect):
    src = r"""
const logs = []; let handler = null;
globalThis.console = { log: (...a) => logs.push(a.join(" ")), table: () => logs.push("table"), warn: () => {} };
globalThis.window = { addEventListener: (t, h) => { if (t === "message") handler = h; }, postMessage() {} };
globalThis.document = { documentElement: { setAttribute() {} } };
""" + ("window.__kgpDiagRows = () => [];\n" if with_net else "") + JS["kgp-main.js"] + r"""
handler({ source: window, data: { __kgpDiagReq: 1 } });
console.log = null;
process.stdout.write(JSON.stringify({ n: logs.filter(l => l.indexOf("자가진단") >= 0).length }) + "\n");
"""
    out = _run_node(src)
    assert out["n"] == expect


def test_contentscript_js_and_objectmultiplex_are_not_ours():
    assert "contentscript.js" not in JS                      # 우리 파일은 content_script.js(밑줄)
    assert not [n for n, s in JS.items() if "ObjectMultiplex" in s or "MaxListeners" in s]
    m = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert all("contentscript.js" not in cs["js"] for cs in m["content_scripts"])
