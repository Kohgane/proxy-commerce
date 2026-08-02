"""tests/test_v86_e_net_scope.py — v86-E: kgp-net.js 주입 스코프 한정.

■ 오너 실기기 오류함 실측(확정)
MAIN 월드 `kgp-net.js`가 `<all_urls>`로 걸려 **로컬 file:// HTML에까지** 주입됐다. 그러면 페이지
자신의 fetch 실패가 래퍼의 `_fetch.apply` 프레임을 지나면서 **귀속만 우리 스크립트로 잡혀**
확장 오류함에 쌓인다. 스코프 과대.

■ 판정: 래퍼는 무해하다 — 고칠 건 스코프다
후처리 체인은 `p.then(...).catch()`로 닫혀 있고(내부 `r.clone().text()`도 `.catch()`),
XHR은 `addEventListener("load")`라 promise 자체가 없다. 그리고 **원 promise를 그대로 반환**해
페이지의 에러 처리를 가리지도 않는다 → 우리가 만드는 unhandled rejection은 0이다.
즉 누락 catch를 메우는 수리는 없고, `matches`를 설계 범위(테무)로 되돌리는 것이 실제 수리다.

■ 왜 테무만인가
파일 헤더의 확정 사실 그대로 — Tier1 캡처는 "테무 KR 상품 페이지엔 초기상태 전역·og 없음"을 전제로
API 응답을 가로채는 **테무 전용 설계**다. 다른 소싱처가 필요해지면 도메인 추가가 정공이다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
NET = (EXT / "kgp-net.js").read_text(encoding="utf-8")


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.136"


def _net_entry():
    hits = [cs for cs in MANIFEST["content_scripts"] if "kgp-net.js" in cs["js"]]
    assert len(hits) == 1, ("kgp-net.js 주입 항목이 하나가 아니다", hits)
    return hits[0]


# ── manifest 스코프 ──────────────────────────────────────────────────────────

def test_net_scope_is_temu_only():
    """★ kgp-net.js matches에 <all_urls>·file 스킴이 없어야 한다(오너 지정)."""
    entry = _net_entry()
    pats = entry["matches"]
    assert pats == ["*://*.temu.com/*"], ("스코프가 테무 전용이 아니다", pats)
    for p in pats:
        assert p != "<all_urls>", "전 URL 주입으로 되돌아갔다"
        assert not p.startswith("file:"), ("file 스킴 주입", p)
        # `*://`는 http/https만 매치한다 — file://은 스킴 불일치로 원천 배제.
        assert p.startswith("*://") or p.startswith("http"), ("스킴이 열려 있다", p)
    assert entry.get("world") == "MAIN", "Tier1 캡처는 MAIN 월드여야 한다(설계 불변)"


def test_other_entries_untouched():
    """반-공허: 나머지 두 항목은 소싱처 전반에 필요하므로 <all_urls> 유지가 맞다."""
    others = [cs for cs in MANIFEST["content_scripts"] if "kgp-net.js" not in cs["js"]]
    assert len(others) == 2, others
    for cs in others:
        assert cs["matches"] == ["<all_urls>"], ("무관한 항목의 스코프를 건드렸다", cs)


def test_scope_decision_is_documented():
    """왜 테무만인지 소스에 남아 있어야 한다 — 다음 사람이 <all_urls>로 되돌리지 않도록."""
    head = NET.split("*/")[0]
    assert "v86-E" in head and "temu.com" in head
    assert "<all_urls>로 되돌리지 말" in head, "되돌림 방지 경고가 없다"


# ── 래퍼 무해성(소스 계약) ────────────────────────────────────────────────────

def test_wrapper_creates_no_unhandled_rejection():
    """후처리 체인이 닫혀 있고 원 promise를 그대로 반환한다."""
    seg = NET.split("// ── fetch 래핑 ──")[1].split("// ── XMLHttpRequest 래핑 ──")[0]
    assert "return p;" in seg, "원 promise를 반환하지 않는다(페이지 에러 처리를 가린다)"
    # p.then(...) 뒤에 .catch가 붙어 있어야 우리 파생 promise가 미처리로 남지 않는다.
    assert re.search(r"p\.then\(function \(r\) \{.*?\}\)\.catch\(", seg, re.S), \
        "후처리 체인에 catch가 없다 — 우리가 unhandled rejection을 만든다"
    # 본문 읽기도 닫혀 있어야 한다. 콜백 본문에 `;`가 들어가므로 `[^;]*?` 류로는 못 넘는다 —
    #   `.text().then(` 이후에 `.catch(`가 오는지로 본다(현행 코드는 한 줄 체인).
    body = next((ln for ln in seg.splitlines() if ".clone().text().then(" in ln), "")
    assert body, "본문 읽기 체인 자체가 없다"
    assert ".catch(" in body.split(".text().then(", 1)[1], \
        ("본문 읽기 체인에 catch가 없다", body.strip())


# ── 실브라우저: 테무 외 도메인에는 안 붙는다 ─────────────────────────────────

def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


def _matches(pattern: str, url: str) -> bool:
    """Chrome match pattern 판정(이 계약에 필요한 범위: scheme + host + path)."""
    if pattern == "<all_urls>":
        return True          # 나머지 두 항목은 전 URL 대상이 맞다(이 계약의 관심사가 아니다)
    m = re.match(r"^(\*|https?|file)://(\*\.)?([^/]*)(/.*)$", pattern)
    assert m, pattern
    scheme, sub, host, path = m.groups()
    u = re.match(r"^([a-z]+)://([^/]*)(/.*)?$", url)
    if not u:
        return False
    us, uh, up = u.group(1), u.group(2), u.group(3) or "/"
    if scheme == "*":
        if us not in ("http", "https"):
            return False           # `*://`는 file/chrome 스킴을 포함하지 않는다
    elif us != scheme:
        return False
    if host and host != "*":
        if sub:
            if uh != host and not uh.endswith("." + host):
                return False
        elif uh != host:
            return False
    return re.match("^" + re.escape(path).replace(r"\*", ".*") + "$", up) is not None


@pytest.mark.parametrize("url,expect", [
    ("https://www.temu.com/kr/goods.html?g=1", True),
    ("https://temu.com/kr/x", True),
    ("file:///C:/Users/x/page.html", False),          # ★ 오너 실측 경로
    ("https://www.amazon.com/s?k=x", False),
    ("https://item.rakuten.co.jp/shop/abc/", False),
    ("chrome://extensions/", False),
])
def test_pattern_admits_only_temu(url, expect):
    """패턴 판정 — file://·타 소싱처·chrome:// 전부 배제."""
    pat = _net_entry()["matches"][0]
    assert _matches(pat, url) is expect, (pat, url)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_no_net_binding_on_non_temu_page():
    """★ 테무 외 도메인 픽스처에서 __kgpNetBound 미존재(오너 지정).

    manifest 스코프대로 **주입 대상 스크립트만** 올린 뒤 전역을 확인한다 —
    스코프가 <all_urls>로 되돌아가면 kgp-net.js가 끼어들어 이 단언이 깨진다.
    """
    from playwright.sync_api import sync_playwright

    url = "https://www.amazon.com/s?k=x"
    injected = [j for cs in MANIFEST["content_scripts"] if any(_matches(p, url) for p in cs["matches"])
                for j in cs["js"]]
    assert "kgp-net.js" not in injected, ("아마존에 net 래퍼가 주입된다", injected)

    stub = """window.chrome={runtime:{id:'x',lastError:null,getManifest:()=>({version:'0'}),
      getURL:p=>p,sendMessage:(m,cb)=>{cb&&setTimeout(()=>cb({ok:false}),0);},onMessage:{addListener(){}}},
      storage:{local:{get:(k,cb)=>cb&&cb({}),set:()=>{}},sync:{get:(k,cb)=>cb&&cb({})},
      onChanged:{addListener(){}}}};"""
    code = ";\n".join((EXT / j).read_text(encoding="utf-8") for j in dict.fromkeys(injected))
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        page = b.new_context().new_page()
        page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body="<html><body>x</body></html>")
                   if r.request.url.split("#")[0] == url else r.abort())
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate(stub)
        page.evaluate(code)
        page.wait_for_timeout(300)
        bound = page.evaluate("() => !!window.__kgpNetBound")
        wrapped = page.evaluate("() => String(window.fetch).indexOf('_fetch') >= 0")
        b.close()
    assert bound is False, "테무가 아닌데 net 래퍼가 바인딩됐다"
    assert wrapped is False, "테무가 아닌데 window.fetch가 래핑됐다"
