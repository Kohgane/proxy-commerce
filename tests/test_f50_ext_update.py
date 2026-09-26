"""F50 — 확장 갱신, 재설치 최소화 (오너 2026-09-26).

| # | 계약 |
|---|---|
| 1 | 서버 최신 버전 > 설치 버전 → 팝업 배너 「새 버전 x — 다운로드」 + 툴바 배지 NEW. 같으면 **안 보인다** |
| 2 | 사이트 규칙은 데이터(JSON) — 서버가 버전·해시와 함께 서빙. 확장은 해시가 맞을 때만 캐시 |
| 2' | 규칙을 **못 받아도** 번들(kgp-rules.js)로 정상 동작 · 받으면 재설치 없이 그 값으로 바뀐다 |
| 2" | page_diag에 「규칙 버전」(version·hash·source) |
| 3 | zip 이름에 버전(kgp-ext-<ver>.zip) · 설치 안내 3줄 |
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
BG = (EXT / "background.js").read_text(encoding="utf-8")
VER = MANIFEST["version"]


def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


needs_browser = pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


# ── 서버 ─────────────────────────────────────────────────────────────────────

def test_latest_endpoint_reads_the_same_manifest(client):
    d = client.get("/api/v1/collect/extension/latest").get_json()
    assert d["ok"] and d["version"] == VER
    assert d["zip_name"] == f"kgp-ext-{VER}.zip" and d["download_page"] == "/seller/extension"


def test_rules_endpoint_serves_version_and_hash_of_the_rules(client):
    from src.collectors.ext_rules import rules_hash
    d = client.get("/api/v1/collect/rules").get_json()
    assert d["ok"] and d["version"] and d["rules"]["list_cards"]["taobao"]["anchor"]
    assert d["hash"] == rules_hash(d["rules"])


def test_bundle_matches_the_server_rules():
    """번들 = 서버를 못 받을 때의 기본값. 서버 JSON을 고치면 `scripts/build_ext_rules_bundle.py`를 돌린다."""
    from src.collectors.ext_rules import load
    js = (EXT / "kgp-rules.js").read_text(encoding="utf-8")
    line = next(ln for ln in js.splitlines() if ln.strip().startswith("var BUNDLED = "))
    bundled = json.loads(line.split("=", 1)[1].split(";   //")[0].strip())
    assert bundled == load(), "번들이 서버 규칙과 다르다 — build_ext_rules_bundle.py를 돌려라"


def test_zip_name_carries_the_version(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/extension/download")
    assert f'filename="kgp-ext-{VER}.zip"' in r.headers.get("Content-Disposition", "")
    import io
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert "kgp-rules.js" in names and "manifest.json" in names


def test_install_page_has_three_line_guide(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/extension").get_data(as_text=True)
    guide = html.split('data-role="ext-update-guide"')[1].split("</ol>")[0]
    assert f"kgp-ext-{VER}.zip" in guide
    assert guide.count("<li>") == 3
    assert "덮어쓰기" in guide and "새로고침" in guide and "삭제 후" in guide


# ── 확장 background: 해시 확인·배지 ────────────────────────────────────────────

def _node():
    n = shutil.which("node")
    if not n:
        pytest.skip("node 미설치")
    return n


def _bg_fns():
    a = BG.index("function kgpCmpVer(")
    b = BG.index("try {\n  chrome.runtime.onStartup")
    return BG[a:b]


def _run_bg(latest: str, rules_payload: dict):
    js = """
const store = {}; const badge = {text: null};
globalThis.chrome = {
  runtime: { getManifest: () => ({version: %(cur)s}) },
  storage: { local: { set: async (o) => Object.assign(store, o) } },
  action: { setBadgeText: async (o) => { badge.text = o.text; }, setBadgeBackgroundColor: async () => {},
            setTitle: async (o) => { badge.title = o.title; } },
};
async function getSettings() { return { serverUrl: "https://srv" }; }
globalThis.fetch = async (u) => ({ ok: true, json: async () => u.endsWith("/extension/latest")
  ? { ok: true, version: %(latest)s, download_page: "/seller/extension", zip_name: "z" } : %(rules)s });
%(fns)s
kgpRefreshRemote("test").then((st) => console.log(JSON.stringify({ st, store, badge })));
""" % {"cur": json.dumps(VER), "latest": json.dumps(latest), "rules": json.dumps(rules_payload), "fns": _bg_fns()}
    out = subprocess.run([_node(), "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _good_rules():
    from src.collectors.ext_rules import load
    return {"ok": True, **load()}


def test_newer_server_version_sets_the_badge_and_caches_verified_rules():
    got = _run_bg("99.0.0", _good_rules())
    assert got["st"]["newer"] is True and got["badge"]["text"] == "NEW"
    assert got["store"]["kgp_update"]["latest"] == "99.0.0"
    assert got["store"]["kgp_rules"]["hash"] == _good_rules()["hash"]      # JS 정규화 해시 = 파이썬 해시


def test_same_version_shows_nothing():
    got = _run_bg(VER, _good_rules())
    assert got["st"]["newer"] is False and got["badge"]["text"] == ""
    assert got["store"]["kgp_update"]["newer"] is False


def test_tampered_rules_are_not_cached():
    bad = _good_rules()
    bad["rules"] = json.loads(json.dumps(bad["rules"]))
    bad["rules"]["list_cards"]["taobao"]["anchor"] = "a.evil"
    got = _run_bg(VER, bad)
    assert "kgp_rules" not in got["store"] and got["st"]["rules"] == "hash-mismatch"


# ── 팝업 배너 ─────────────────────────────────────────────────────────────────

def _popup(upd):
    from playwright.sync_api import sync_playwright
    stub = """() => { window.chrome = {
      runtime: { id: 'x', getManifest: () => ({version: %s}), sendMessage: (m, cb) => cb && setTimeout(() => cb({}), 0),
                 onMessage: { addListener() {} }, getURL: (p) => p },
      storage: { local: { get: (k, cb) => cb && setTimeout(() => cb(k === 'kgp_update' ? { kgp_update: %s } : {}), 0), set: () => {} },
                 sync: { get: (k, cb) => cb && setTimeout(() => cb({}), 0) }, onChanged: { addListener() {} } },
      tabs: { query: (q, cb) => cb && setTimeout(() => cb([{ url: 'https://example.com/', id: 1 }]), 0),
              sendMessage: (t, m, cb) => cb && setTimeout(() => cb(null), 0), create: () => {} },
    }; }""" % (json.dumps(VER), json.dumps(upd))
    html = (EXT / "popup.html").read_text(encoding="utf-8").replace('<script src="popup.js"></script>', "")
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        pg = b.new_page()
        pg.set_content(html)
        pg.evaluate(stub)
        try:
            pg.add_script_tag(content=(EXT / "popup.js").read_text(encoding="utf-8"))
        except Exception:
            pass
        pg.wait_for_timeout(200)
        got = pg.evaluate("""() => { const el = document.getElementById('updBanner');
            return { shown: getComputedStyle(el).display !== 'none', text: el.textContent,
                     href: (el.querySelector('a') || {}).href || '' }; }""")
        b.close()
    return got


@needs_browser
def test_popup_banner_when_newer():
    got = _popup({"current": VER, "latest": "9.9.9", "newer": True, "download_page": "https://srv/seller/extension"})
    assert got["shown"] and "새 버전 9.9.9 — 다운로드" in got["text"]
    assert "덮어쓰고" in got["text"] and "새로고침" in got["text"]
    assert got["href"] == "https://srv/seller/extension"


@needs_browser
@pytest.mark.parametrize("upd", [
    {"current": VER, "latest": VER, "newer": False},
    {"current": "0.0.1", "latest": "9.9.9", "newer": True},     # 옛 설치 때 기록 — 지금 버전과 달라 무효
    None,
])
def test_popup_banner_hidden_otherwise(upd):
    assert _popup(upd)["shown"] is False


# ── content script: 번들 폴백 · 원격 규칙 반영 · 진단 표기 ─────────────────────────

def _isolated(drop_rules=False):
    return ";\n".join((EXT / j).read_text(encoding="utf-8") for cs in MANIFEST["content_scripts"]
                      if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"]
                      if not (drop_rules and j == "kgp-rules.js"))


def _taobao(storage: dict, drop_rules=False, cls="item-link"):
    from playwright.sync_api import sync_playwright
    from tests.test_f49t3_taobao_list_cards import _synthetic_page
    body = _synthetic_page().replace('class="item-link tb-pick-content-item item-appear"', f'class="{cls}"')
    stub = """() => { window.chrome = {
      runtime: { id: 'x', lastError: null, getManifest: () => (%s), getURL: (p) => p,
                 sendMessage: (m, cb) => cb && setTimeout(() => cb({ok: false}), 0), onMessage: { addListener() {} } },
      storage: { local: { get: (k, cb) => cb && cb(%s), set: () => {} }, sync: { get: (k, cb) => cb && cb({}) },
                 onChanged: { addListener() {} } } }; }""" % (json.dumps(MANIFEST), json.dumps(storage))
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
        pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
                 if r.request.resource_type == "document" else r.abort())
        pg.goto("https://world.taobao.com/", wait_until="domcontentloaded")
        pg.evaluate(stub)
        pg.evaluate(_isolated(drop_rules))
        pg.wait_for_timeout(1500)
        got = pg.evaluate("""() => ({ n: kgpFindCards().length, adapter: _kgpTaobaoListCards().length, rules: kgpPageDiag().rules,
            label: (document.querySelector('.kgp-card-quick') || {})._kgpLbl ? document.querySelector('.kgp-card-quick')._kgpLbl.textContent : null })""")
        b.close()
    return got


@needs_browser
def test_without_remote_rules_the_bundle_works():
    got = _taobao({})
    assert got["n"] == 30 and got["adapter"] == 30
    assert got["rules"]["source"] == "bundled" and got["rules"]["version"]


@needs_browser
def test_without_the_rules_file_code_defaults_still_work():
    got = _taobao({}, drop_rules=True)
    assert got["n"] == 30 and got["adapter"] == 30 and got["rules"]["source"] == "none"


@needs_browser
def test_remote_rules_change_detection_without_reinstall():
    """사이트가 카드 클래스를 바꿨다(가정) — 번들 셀렉터로는 0, 서버 규칙만 고치면 다시 30."""
    from src.collectors.ext_rules import load, rules_hash
    rules = json.loads(json.dumps(load()["rules"]))
    rules["list_cards"]["taobao"]["anchor"] = "a.feed-card-v2"
    rules["tiles"]["label"]["taobao"] = "고가수집"
    cache = {"kgp_rules": {"version": "2099-01-01.1", "hash": rules_hash(rules), "rules": rules}}
    before = _taobao({}, cls="feed-card-v2")
    after = _taobao(cache, cls="feed-card-v2")
    assert before["adapter"] == 0, "번들 셀렉터가 바뀐 카드를 잡았다(가정이 성립 안 함)"
    assert after["adapter"] == 30 and after["label"] == "고가수집"
    assert after["rules"] == {"version": "2099-01-01.1", "hash": rules_hash(rules)[:12], "source": "remote"}


def test_page_diag_rules_survive_server_cleaning():
    from src.collectors.collect_status import clean_page_diag
    got = clean_page_diag({"rules": {"version": "2026-09-26.1", "hash": "abc", "source": "remote", "x": 1}})
    assert got["rules"] == {"version": "2026-09-26.1", "hash": "abc", "source": "remote"}
