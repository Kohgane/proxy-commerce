"""SEC-1 — 진단·스냅샷 파일에 로그인 쿠키가 실렸다(2026-09-27 실측, 티몰 617129397971).

페이지 DOM의 `<img src="https://pass.tmall.com/add?…cookie1=…&cookie2=…&_tb_token_=…">`와 page_diag.errors의
리소스 주소가 **쿼리스트링 그대로** 파일에 들어갔고, 그 파일이 레포에 커밋됐다. 내비바에는 계정 닉네임·회원번호도 찍혔다.

이 파일이 못박는 것:
  ① 레포의 진단·스냅샷 픽스처에 가려지지 않은 비밀이 0개(새로 올라온 파일도 여기서 걸린다)
  ② page_diag에 싣는 주소는 경로까지만(상품 id 계열만 남김) — 실브라우저에서 실패한 리소스로 확인
  ③ 파일로 나가는 텍스트(스냅샷·진단 번들)는 저장 직전 비밀 값을 `***`로 — 확장이 실제로 호출한다
  ④ 서버 `clean_page_diag`도 같은 규칙(옛 확장 1.5.156 이하가 보낸 값)
  ⑤ 확장(kgp-scrub.js)과 서버(secret_scrub.py)는 같은 키 목록·같은 결과
테스트 입력의 비밀 값은 전부 지어낸 가짜다.
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
from pathlib import Path

import pytest

from src.collectors.secret_scrub import (SECRET_KEYS, find_secrets, scrub_line, scrub_text,
                                         scrub_url)

EXT = Path("extensions/chrome-collector")
FAKE_NICK = "tb000011112222"
PASS_URL = ("https://pass.tmall.com/add?lid=" + FAKE_NICK + "&_l_g_=Ug%3D%3D&lgc=" + FAKE_NICK
            + "&cookie1=FAKEc1FAKEc1&cookie2=fakefakefake0000&sg=123&_tb_token_=faketok9&unb=4242424242&hng=KR")
SAMPLE = ('<img src="' + PASS_URL.replace("&", "&amp;") + '">'
          '<p class="site-nav-login-info-nick">' + FAKE_NICK + '</p>'
          '<script>var u={"userNumId":98765432101,"nick":"' + FAKE_NICK + '"};</script>'
          '<a href="https://detail.tmall.com/item.htm?id=617129397971&spm=a1">상품</a>')
LEAKS = ("FAKEc1FAKEc1", "fakefakefake0000", "faketok9", "4242424242", FAKE_NICK, "98765432101")


# ① 레포 픽스처 — 가려지지 않은 비밀 0
def test_no_committed_fixture_carries_a_login_secret():
    files = []
    for g in ("fixtures/realpages/**/*.html", "fixtures/realpages/**/*.json",
              "tests/fixtures/**/*.html", "tests/fixtures/**/*.json"):
        files += glob.glob(g, recursive=True)
    assert files
    dirty = {f: find_secrets(Path(f).read_text(encoding="utf-8", errors="replace")) for f in files}
    dirty = {f: k for f, k in dirty.items() if k}
    assert not dirty, ("비밀이 남은 픽스처 — python scripts/scrub_diag_secrets.py 로 지운 뒤 커밋", dirty)


def test_scrub_masks_cookies_tokens_and_the_account_everywhere():
    out = scrub_text(SAMPLE)
    for v in LEAKS:
        assert v not in out, v
    assert "cookie2=***" in out and "_tb_token_=***" in out and "unb=***" in out
    assert "hng=KR" in out and "Ug%3D%3D" not in out            # 비밀 아닌 값은 그대로
    assert "item.htm?id=617129397971&spm=a1" in out             # 상품 링크는 건드리지 않는다
    assert find_secrets(out) == [] and find_secrets(SAMPLE)


def test_scrub_url_keeps_the_path_and_the_product_id_only():
    assert scrub_url(PASS_URL) == "https://pass.tmall.com/add"
    assert scrub_url("https://detail.tmall.com/item.htm?id=617129397971&spm=x#tab") == \
        "https://detail.tmall.com/item.htm?id=617129397971"
    line = scrub_line("resource: <img> " + PASS_URL + " failed")
    assert line == "resource: <img> https://pass.tmall.com/add failed"


# ④ 서버 clean_page_diag
def test_server_page_diag_keeps_paths_only():
    from src.collectors.collect_status import clean_page_diag
    d = clean_page_diag({"url": "https://detail.tmall.com/item.htm?id=617129397971&cookie2=abcdef12",
                         "nav": {"requested": PASS_URL},
                         "errors": ["resource: <img> " + PASS_URL, "script: x @ " + PASS_URL + ":1:2"],
                         "ice_error": "JSON 실패 — ?cookie2=zzzzzzzz"})
    blob = json.dumps(d, ensure_ascii=False)
    for v in LEAKS + ("abcdef12", "zzzzzzzz"):
        assert v not in blob, v
    assert d["url"] == "https://detail.tmall.com/item.htm?id=617129397971"
    assert d["nav"]["requested"] == "https://pass.tmall.com/add"
    assert d["errors"][0] == "resource: <img> https://pass.tmall.com/add"


# ⑤ 확장 ↔ 서버 같은 규칙
def test_extension_and_server_share_keys_and_results():
    js = (EXT / "kgp-scrub.js").read_text(encoding="utf-8")
    keys = json.loads("[" + re.search(r"KGP_SECRET_KEYS = \[(.*?)\];", js, re.S).group(1) + "]")
    assert tuple(keys) == SECRET_KEYS
    node = ("const S=require('./extensions/chrome-collector/kgp-scrub.js');"
            "const a=JSON.parse(process.argv[1]);"
            "process.stdout.write(JSON.stringify([S.kgpScrubText(a[0]),S.kgpScrubUrl(a[1]),S.kgpScrubLine(a[2])]));")
    args = [SAMPLE, PASS_URL, "resource: <img> " + PASS_URL]
    got = json.loads(subprocess.run(["node", "-e", node, json.dumps(args)], capture_output=True,
                                    text=True, check=True).stdout)
    assert got == [scrub_text(args[0]), scrub_url(args[1]), scrub_line(args[2])]


# ③ 확장이 실제로 부르는가(배선)
def test_extension_wires_the_scrubber_into_every_export():
    man = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    iso = next(cs for cs in man["content_scripts"] if "content_script.js" in cs["js"])
    assert iso["js"].index("kgp-scrub.js") < iso["js"].index("content_script.js")
    assert '<script src="kgp-scrub.js"></script>' in (EXT / "popup.html").read_text(encoding="utf-8")
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert cs.count('html = _kgpSafeHtml("<!doctype html>\\n" + document.documentElement.outerHTML)') == 2
    assert "_KGP_PAGE_ERRORS.slice(0, 5).map(_kgpSafeLine)" in cs
    assert "url: _kgpSafeUrl(location.href)" in cs and "requested: _kgpSafeUrl(nav.name" in cs
    pop = (EXT / "popup.js").read_text(encoding="utf-8")
    assert "kgpScrubText(res.html + embed)" in pop and "kgpScrubText(res.html)" in pop


def _chrome():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return {"executable_path": hits[0]} if hits else {}


def _diag_js() -> str:
    src = (EXT / "content_script.js").read_text(encoding="utf-8")
    a = src.index("function _kgpDetectWall()")
    b = src.index("\n}\n", a) + 3
    c = src.index("const _KGP_PAGE_ERRORS = [];")
    d = src.index("function extractProductMeta()", c)
    return src[a:b] + "\n" + src[c:d]


# ② 실브라우저 — 실패한 pass.tmall 리소스가 page_diag.errors에 경로까지만
def test_real_browser_page_diag_and_snapshot_carry_no_cookie():
    pw = pytest.importorskip("playwright.sync_api")
    page = ("<html><head><title>随行盾</title></head><body>"
            + SAMPLE + '<img src="' + PASS_URL.replace("&", "&amp;") + '&late=1"></body></html>')
    with pw.sync_playwright() as p:
        br = p.chromium.launch(**_chrome())
        pg = br.new_page()
        pg.route("https://pass.tmall.com/**", lambda r: r.fulfill(status=404, body=""))
        pg.route("https://detail.tmall.com/**",
                 lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=page))
        # 캡처 리스너는 페이지 스크립트보다 먼저 — 확장처럼 문서 시작 시 주입
        src = (EXT / "kgp-scrub.js").read_text(encoding="utf-8") + "\n" + _diag_js()
        pg.add_init_script(script="(0, eval)(" + json.dumps(src) + ");")
        pg.goto("https://detail.tmall.com/item.htm?id=617129397971&spm=a1")
        pg.wait_for_timeout(300)
        d = pg.evaluate("() => kgpPageDiag()")
        snap = pg.evaluate("() => kgpScrubText('<!doctype html>\\n' + document.documentElement.outerHTML)")
        br.close()
    blob = json.dumps(d, ensure_ascii=False)
    assert any("pass.tmall.com/add" in e for e in d["errors"]), d["errors"]
    for v in LEAKS:
        assert v not in blob and v not in snap, v
    assert all("?" not in e for e in d["errors"] if "pass.tmall.com" in e)
    assert d["url"] == "https://detail.tmall.com/item.htm?id=617129397971"
    assert find_secrets(snap) == []


# SEC-1-c — 목록·홈 마크업의 닉네임(오너 1.5.158 world.taobao 진단: 5곳 미마스킹)
LIST_NICK = "tb000099998888"
LIST_PAGE = ('<div class="site-nav-bd"><a class="site-nav-login-info-nick " href="//i.taobao.com/">' + LIST_NICK
             + '</a><p class="site-nav-user-nick">' + LIST_NICK + '</p>'
             + '<img src="https://wwc.alicdn.com/avatar/getAvatar.do?userNick=' + LIST_NICK + '&width=40&height=40">'
             + '<span class="nick-count">12</span></div>'
             + '<script>var t="' + LIST_NICK + '";</script>')


def test_list_page_nickname_is_masked_everywhere():
    """상세 JSON(`"nick":`)이 없는 목록 페이지 — 내비바 요소 텍스트·`userNick=`에서 값을 모아 문서 전체에서 가린다."""
    assert find_secrets(LIST_PAGE)
    out = scrub_text(LIST_PAGE)
    assert LIST_NICK not in out and out.count("***") == 4 and find_secrets(out) == []
    assert '<span class="nick-count">12</span>' in out                       # 짧은 값은 계정이 아니다


def test_list_page_nickname_same_in_extension():
    node = ("const S=require('./extensions/chrome-collector/kgp-scrub.js');"
            "process.stdout.write(S.kgpScrubText(process.argv[1]));")
    got = subprocess.run(["node", "-e", node, LIST_PAGE], capture_output=True, text=True, check=True).stdout
    assert got == scrub_text(LIST_PAGE)
