"""tests/test_v64_button_spec.py — v64 STEP3: 수집 버튼 스펙 확정.

원 과대·글자 과소 → 지름 절반(min-height 66→34)·아이콘 축소(21→14)·텍스트 위주 필.
앵커: 기본 중앙, 설정(kgp_hover_anchor)에서 좌하(bl 7시)/우하(br 5시). gogabridj 토큰(먹/금/청록).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
POPUP_JS = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
POPUP_HTML = Path("extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.146"


def test_button_shrunk_and_tokens():
    # v86 STEP2: 알약 모양(치수·색)은 Shadow DOM 스타일시트로 이전됐다. 호스트(kgpQuickBtnStyle)는
    #   위치·가시성만 담당한다 → 스펙 검증 대상은 _kgpQuickShadowCss. 값 자체는 v64 그대로여야 한다.
    style = re.search(r"function _kgpQuickShadowCss\(\) \{.*?\n\}", CS, re.S).group(0)
    assert "min-height:34px" in style        # 지름 절반(66→34)
    assert "66px" not in style               # 옛 큰 값 제거
    # gogabridj 토큰만(먹/금/청록) — 임의 색 없음.
    assert "#1a1714" in style and "#c9a24b" in style and "#119a8e" in style
    # 아이콘 축소(21→14).
    assert "width:14px;height:14px" in style
    # 호스트는 모양을 갖지 않는다(옛 all:initial 인라인 경로로 복귀 방지).
    host = re.search(r"function kgpQuickBtnStyle\(collected, mode\) \{.*?\n\}", CS, re.S).group(0)
    # v86 STEP4: 이 가드의 대상은 **코드**다 — 주석의 역사 설명(all:initial이 왜 유령이었는지)까지
    #   금지하면 재발 방지 지식을 코드에서 지우게 된다. 주석을 제거하고 판정한다.
    host_code = "\n".join(ln.split("//")[0] for ln in host.splitlines())
    assert "all:initial" not in host_code


def test_anchor_setting_wired():
    assert "KGP_HOVER_ANCHOR" in CS and "function kgpHoverAnchor()" in CS
    assert "kgp_hover_anchor" in CS
    # 팝업이 chrome.storage.local로 설정(사이트 무관 공유).
    assert "hoverAnchor" in POPUP_JS and "kgp_hover_anchor" in POPUP_JS
    assert 'id="hoverAnchor"' in POPUP_HTML
    for opt in ["center", "bl", "br"]:
        assert 'value="' + opt + '"' in POPUP_HTML


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_anchor_css_node():
    # KGP_TOUCH=false(데스크톱)일 때 앵커별 CSS: center=translate, bl=bottom+left, br=bottom+right.
    fn = re.search(r"function _kgpAnchorCss\(mode\) \{.*?\n\}", CS, re.S).group(0)
    harness = (
        "var KGP_TOUCH=false; var _a='center';\n"
        "function kgpLSget(){return _a;}\n"
        "function kgpHoverAnchor(){return _a;}\n"
        + fn + "\n"
        "var out={};\n"
        "_a='center'; out.center=_kgpAnchorCss().join('|');\n"
        "_a='bl'; out.bl=_kgpAnchorCss().join('|');\n"
        "_a='br'; out.br=_kgpAnchorCss().join('|');\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert "translate(-50%,-50%)" in out["center"]
    assert "bottom:10px" in out["bl"] and "left:10px" in out["bl"]
    assert "bottom:10px" in out["br"] and "right:10px" in out["br"]
