"""tests/test_v42_e2_always_on.py — v42 E-2: 퍼센티식 상시 수집 버튼.

요구: 설치 후 지원 도메인(Temu·아마존·야후·요시다 등) 진입 시 인증과 무관하게 버튼 상시 표시.
미인증은 클릭 시에만 안내(E-1). SPA(pushState) 갱신.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_matches_all_urls():
    cs = MANIFEST["content_scripts"][0]
    assert "<all_urls>" in cs["matches"]


def test_fab_injection_has_no_auth_gate():
    """버튼은 인증 상태와 무관하게 표시(토큰 검사는 클릭 때만) — injectCollectButton에 토큰/auth 검사 없음."""
    i = CS.index("function injectCollectButton(")
    j = CS.index("_kgpMount(btn)", i)   # v45 P5: body.appendChild → _kgpMount(<html> 직속)
    body = CS[i:j]
    for bad in ("token", "Bearer", "getSettings", "authRequired", "401"):
        assert bad not in body, f"injectCollectButton에 인증 게이트({bad}) 있으면 안 됨"


def test_spa_hooks_present():
    assert "pushState" in CS and "replaceState" in CS and "popstate" in CS


def test_owner_named_domains_in_defaults():
    for dom in ("temu", "amazon", "yahoo", "yoshida"):
        assert f'id: "{dom}"' in CS


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_host_allowed_for_named_markets():
    """kgpHostAllowed가 Temu·아마존·야후·요시다 호스트를 지정 소싱처로 인정(버튼 상시)."""
    i = CS.index("const KGP_DEFAULT_SOURCES")
    j = CS.index("let KGP_SOURCES")
    block = CS[i:j]
    # kgpHostAllowed 본문 발췌
    hi = CS.index("function kgpHostAllowed(")
    hj = CS.index("\n}\n", hi) + 2
    fn = CS[hi:hj]
    script = block + "\nlet KGP_SOURCES=null;\n" + fn + r"""
    function chk(host){
      global.location = { hostname: host };
      return kgpHostAllowed();
    }
    const hosts = ['www.temu.com','www.amazon.co.jp','shopping.yahoo.co.jp','www.yoshidakaban.com','example.com'];
    console.log(JSON.stringify(hosts.map(chk)));
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    allowed = json.loads(res.stdout.strip())
    assert allowed == [True, True, True, True, False]   # 지정 4곳 허용, 무관 사이트 미허용
