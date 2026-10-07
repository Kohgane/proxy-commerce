"""Y6-C C(오너 2026-10-07) — 「문제가 생겼어요」 일반 토스트가 원인을 숨겼다.

실측(19:0x KST, 플리츠 세트 · 마켓 등록 모달 · 「사전검증 →」 직후): 토스트 「문제가 생겼어요 — 잠시 후 다시 시도해 주세요.
계속되면 도움말을 확인해 주세요.」만. 데스크톱 드로어의 사전검증은 **동기 경로**(`async` 없이 POST — 202+job_id 아님)라
응답이 502 HTML이면 `resp.json()`이 던지고, 처리기는 개발 메시지로 보고 원문을 가렸다.
계약: HTTP 상태 + 서버 사유코드·메시지 첫 120자를 토스트에 같이 싣는다(「사전검증 시작 실패 — 502 …」). 숨기는 일반 문구 금지.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

JS = Path(__file__).parent.parent / "src" / "seller_console" / "static" / "seller.js"
TPL = Path(__file__).parent.parent / "src" / "seller_console" / "templates" / "collect_preview.html"
node = pytest.mark.skipif(not shutil.which("node"), reason="node 미설치")


def _run(js_body: str) -> list:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js_body)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)


def _fn() -> str:
    m = re.search(r"function kgpFriendlyError\(raw\) \{[\s\S]*?\n\}", JS.read_text(encoding="utf-8"))
    assert m
    return m.group(0)


@node
def test_status_and_reason_are_shown_never_generic_only():
    cases = [
        [{"status": 502, "error": "worker timeout"}, "사전검증 시작 실패"],
        [{"status": 502, "error": "<!doctype html><html><head><title>x</title></head><body><h1>502 Bad Gateway</h1></body></html>"}, "사전검증 시작 실패"],
        [{"ok": False, "status": 500, "error_code": "prevalidate_error", "error": "사전검증 중 오류 — KeyError: 'skus'"}, ""],
        [[], ""],
        ["이미 수집한 상품입니다", ""],
    ]
    got = _run(_fn() + "\nconsole.log(JSON.stringify(%s.map(c => kgpFriendlyError(c[0], c[1]))));" % json.dumps(cases, ensure_ascii=False))
    assert got[0] == "사전검증 시작 실패 — 502 worker timeout"
    assert got[1].startswith("사전검증 시작 실패 — 문제가 생겼어요 — 502") and "502 Bad Gateway" in got[1] and "<" not in got[1]
    assert "500" in got[2] and "prevalidate_error" in got[2] and "KeyError: 'skus'" in got[2]
    assert got[3] == "문제가 생겼어요 — 사유 원문 없음(서버가 상태·본문을 주지 않았어요)"
    assert got[4] == "이미 수집한 상품입니다"
    for g in got:
        assert g != "문제가 생겼어요 — 잠시 후 다시 시도해 주세요. 계속되면 도움말을 확인해 주세요."


@node
def test_fetch_watcher_carries_status_when_json_parse_throws():
    """502 HTML → 호출부의 resp.json()이 SyntaxError로 죽어도 토스트가 상태·본문 첫 줄을 싣는다."""
    js = JS.read_text(encoding="utf-8")
    watcher = js[js.index("/** Y6-C C1: 실패한 응답을 적어 둔다"):]
    watcher = watcher[: watcher.index("})();") + 5]
    harness = ("var window = {fetch: function () { return Promise.resolve({ok: false, status: 502, "
               "clone: function () { return {text: function () { return Promise.resolve('<html><body>502 Bad Gateway — worker timeout</body></html>'); }}; }, "
               "json: function () { return Promise.reject(new SyntaxError(\"Unexpected token '<'\")); }}); }};\n"
               + _fn() + "\n" + watcher + "\n"
               "window.fetch('/seller/collect/prevalidate').then(function (r) { return r.json(); }).catch(function (e) {"
               "  setTimeout(function () { console.log(JSON.stringify([kgpFriendlyError(e, '사전검증 시작 실패')])); }, 20); });")
    got = _run(harness)[0]
    assert got.startswith("사전검증 시작 실패 — ") and "502" in got and "worker timeout" in got


def test_desktop_prevalidate_reads_text_first_and_labels_stage():
    t = TPL.read_text(encoding="utf-8")
    seg = t[t.index("async function runPrevalidate()"):t.index("function renderActionLink")]
    assert "await resp.text()" in seg and "await resp.json()" not in seg
    assert seg.count("'사전검증 시작 실패'") == 2 and "status: resp.status" in seg


def test_desktop_prevalidate_is_sync_path_fact():
    """C2 사실 기록: 데스크톱 드로어는 `async` 없이 POST — 202+job_id 경로가 아니다(운영 DB prevalidate_job 0건과 일치)."""
    t = TPL.read_text(encoding="utf-8")
    seg = t[t.index("async function runPrevalidate()"):t.index("function renderActionLink")]
    assert "async: true" not in seg and "'/seller/collect/prevalidate'" in seg


def test_server_exception_carries_type_and_message(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_pv_sync", lambda *a, **k: (_ for _ in ()).throw(KeyError("skus")))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    r = c.post("/seller/collect/prevalidate", json={"product": {"title": "x"}, "markets": ["shopify"]})
    d = r.get_json()
    assert r.status_code == 500 and d["error_code"] == "prevalidate_error"
    assert d["error"] == "사전검증 중 오류 — KeyError: 'skus'"


def test_no_hardcoded_generic_toasts_left():
    root = Path(__file__).parent.parent / "src" / "seller_console"
    bad = []
    for p in list(root.rglob("*.html")) + list(root.rglob("*.js")):
        t = p.read_text(encoding="utf-8")
        for m in re.finditer(r"pcToast\('([^']*(문제가 생겼|오류가 발생했어요)[^']*)'", t):
            bad.append(f"{p.name}: {m.group(1)}")
    assert bad == []
