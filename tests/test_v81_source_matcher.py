"""tests/test_v81_source_matcher.py — v81 STEP3: 소싱처 호스트 매칭 단일 진실원천 + 아마존 국가도메인.

버그: 팝업(popup.js)이 6개짜리 자체 소싱처 목록을 들고 있어 www.rakuten.co.jp에서 콘텐츠스크립트는
FAB 주입 / 팝업은 "지정 소싱처 아님" 모순 표시. 수리: kgp-sources.js(단일 레지스트리+매처)에 양쪽 위임.

계약(CI 게이트):
- 매처 단위: rakuten 서브도메인 전부 → rakuten, amazon 국가도메인(de/co.jp/co.uk/…) → amazon, 미등록 → null.
- drift-guard: 팝업이 자체 목록/매처를 안 쓰고 KGPSources에 위임(소스계약).
- content_script·popup·manifest 로드 정합.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
SOURCES_JS = (EXT / "kgp-sources.js").read_text(encoding="utf-8")
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
POPUP = (EXT / "popup.js").read_text(encoding="utf-8")
POPUP_HTML = (EXT / "popup.html").read_text(encoding="utf-8")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))


def _node(script: str) -> str:
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=".")
    assert r.returncode == 0, f"node 실패: {r.stderr[:800]}"
    return r.stdout.strip()


# ── 매처 단위(node 실행 — 실제 KGPSources.matchUrl) ──
def test_matcher_registry_contract():
    out = _node(
        "global.self=global;require('./extensions/chrome-collector/kgp-sources.js');"
        "const K=global.KGPSources;"
        "const C=["
        "['https://www.rakuten.co.jp/?l2-id=shop_header_logo','rakuten'],"
        "['https://item.rakuten.co.jp/shop/123/','rakuten'],"
        "['https://search.rakuten.co.jp/search/mall/roller/','rakuten'],"
        "['https://books.rakuten.co.jp/rb/12345/','rakuten'],"
        "['https://www.amazon.de/dp/B0AAA','amazon'],"
        "['https://www.amazon.co.jp/dp/B0AAA','amazon'],"
        "['https://www.amazon.co.uk/s?k=x','amazon'],"
        "['https://www.amazon.fr/dp/x','amazon'],"
        "['https://www.amazon.it/dp/x','amazon'],"
        "['https://www.amazon.es/dp/x','amazon'],"
        "['https://www.amazon.com/dp/X?ref=trk','amazon'],"
        "['https://www.taobao.com/item.htm?id=1','taobao'],"
        "['https://www.example.com/foo?utm=1',null],"
        "['https://shop.unregistered.io/','null']"
        "];"
        "let bad=[];for(const[u,e]of C){const m=K.matchUrl(u,{});const id=m?m.id:null;"
        "const exp=e==='null'?null:e;if(id!==exp)bad.push(u+'=>'+id);}"
        "console.log(JSON.stringify(bad));"
    )
    assert out == "[]", f"매처 불일치: {out}"


def test_matcher_ignores_query_and_defaults_toggle():
    out = _node(
        "global.self=global;require('./extensions/chrome-collector/kgp-sources.js');"
        "const K=global.KGPSources;"
        # 쿼리/트래킹 무시(hostname만)
        "const a=K.matchUrl('https://www.rakuten.co.jp/?l2-id=x&scid=trk',{});"
        # defaults에서 끄면 null
        "const b=K.matchUrl('https://www.amazon.de/dp/x',{defaults:{amazon:false}});"
        # custom 도메인 매칭
        "const c=K.matchUrl('https://sub.mysite.com/p',{custom:[{host:'mysite.com',on:true}]});"
        "console.log(JSON.stringify([a&&a.id,b,c&&c.custom]));"
    )
    assert json.loads(out) == ["rakuten", None, True]


def test_amazon_country_currency_locale():
    """아마존 국가도메인 로케일 통화(de→EUR, co.jp→JPY, co.uk→GBP) — kgp-extractor._localeCurrency 계약."""
    out = _node(
        "global.self=global;global.window=global;"
        "global.location={hostname:'',pathname:'/'};"
        "global.document={documentElement:{lang:''}};"
        "const src=require('fs').readFileSync('extensions/chrome-collector/kgp-extractor.js','utf8');"
        # _localeCurrency 추출·실행(순수 함수 — host만 바꿔 평가)
        "const m=src.match(/function _localeCurrency\\([^)]*\\)[\\s\\S]*?\\n  \\}/);"
        "eval(m[0]);"
        "function cur(h){global.location.hostname=h;return _localeCurrency();}"
        "console.log(JSON.stringify({de:cur('www.amazon.de'),jp:cur('www.amazon.co.jp'),"
        "uk:cur('www.amazon.co.uk'),fr:cur('www.amazon.fr'),com:cur('www.amazon.com')}));"
    )
    assert json.loads(out) == {"de": "EUR", "jp": "JPY", "uk": "GBP", "fr": "EUR", "com": "USD"}


# ── drift-guard: 팝업/콘텐츠스크립트가 단일 소스에 위임 ──
def test_popup_delegates_to_kgpsources():
    # 팝업이 자체 6개 목록/매처를 안 쓴다.
    assert "DEFAULT_SOURCE_TESTS" not in POPUP, "팝업이 아직 자체 소싱처 목록을 든다(drift 재발)"
    assert "KGPSources.matchHost" in POPUP
    # 메시지 3분리: 미등록 / 수집버튼 표시 / 상품·목록 페이지 안내.
    assert "지정 소싱처가 아니에요" in POPUP
    assert "수집 버튼이 표시돼요" in POPUP
    assert "상품·목록 페이지에서 수집 버튼이 나와요" in POPUP
    # popup.html이 단일 소스 스크립트 로드.
    assert "kgp-sources.js" in POPUP_HTML and "kgp-detect.js" in POPUP_HTML


def test_content_script_derives_registry_from_kgpsources():
    assert "KGPSources.SOURCES" in CS, "콘텐츠스크립트가 KGPSources에서 파생하지 않음"
    assert "KGPSources.allowed" in CS
    # 레지스트리 전 소싱처 id가 단일 소스에 존재.
    ids = [s["id"] for s in _sources_registry()]
    for want in ["taobao", "tmall", "1688", "temu", "amazon", "aliexpress", "iherb",
                 "dhgate", "qoo10", "mercari", "rakuten", "yahoo", "yoshida"]:
        assert want in ids, f"단일 레지스트리에 {want} 누락"


def test_manifest_loads_sources_before_content_script():
    cs_entry = next(c for c in MANIFEST["content_scripts"] if "content_script.js" in c.get("js", []))
    js = cs_entry["js"]
    assert "kgp-sources.js" in js, "manifest content_scripts에 kgp-sources.js 미포함"
    assert js.index("kgp-sources.js") < js.index("content_script.js"), "kgp-sources는 content_script보다 먼저 로드돼야"
    assert MANIFEST["version"] == "1.5.147"


def _sources_registry():
    out = _node(
        "global.self=global;require('./extensions/chrome-collector/kgp-sources.js');"
        "console.log(JSON.stringify(global.KGPSources.SOURCES.map(s=>({id:s.id}))));"
    )
    return json.loads(out)
