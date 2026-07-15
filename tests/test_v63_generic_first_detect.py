"""tests/test_v63_generic_first_detect.py — v63 STEP1: 감지 역전(Generic-first, Adapter-augment).

요시다(제네릭 휴리스틱)는 건강, 테무·아마존(어댑터)은 셀렉터 사망 시 버튼 미표시.
근본 수리: 제네릭을 항상 실행하고 어댑터는 정밀 보강만 → 어댑터 실패/부분매치가 제네릭 커버리지를
절대 막지 않는다. 상품키(_kgpCardKey)로 같은 상품 병합(어댑터 우선). 팝업 디버그 패널로 실측 보고.
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
    assert MANIFEST["version"] == "1.5.88"


def test_source_contract_generic_first():
    # 병합·상품키·스냅샷 존재.
    assert "_kgpMergeCards" in CS and "_kgpCardKey" in CS and "_kgpLastDetect" in CS
    # kgpFindCards가 제네릭을 어댑터보다 먼저 호출(생성 순서 = 제네릭 우선).
    fc = re.search(r"function kgpFindCards\(\) \{.*?\n\}", CS, re.S).group(0)
    gi = fc.find("_kgpGenericCards()")
    ai = fc.find("_kgpAmazonCards()")
    assert gi != -1 and ai != -1 and gi < ai, "제네릭이 어댑터보다 먼저 실행되어야 함"
    assert "_kgpMergeCards(generic, adapter)" in fc
    # 어댑터 실패가 제네릭을 막지 않음: 병합은 generic 먼저 채우고 adapter로 덮어씀(신규 추가).
    assert "제네릭" in fc


def test_source_contract_anchor_fallback():
    # 제네릭에 카드 컨테이너 앵커 폴백(테무 SPA: 이미지가 <a>로 안 감싸임).
    gen = re.search(r"function _kgpGenericCards\(\) \{.*?\n\}", CS, re.S).group(0)
    assert "card.querySelectorAll(\"a[href]\")" in gen
    assert "goods" in gen and "product" in gen   # 카드 컨테이너 셀렉터에 goods/product


def test_source_contract_debug_panel():
    assert 'msg.action === "kgpDetectState"' in CS
    assert "kgpDetectState" in POPUP_JS and "detectBody" in POPUP_JS
    assert 'id="detectPanel"' in POPUP_HTML and "감지 진단" in POPUP_HTML


def _extract(fn_name):
    m = re.search(r"function " + fn_name + r"\([^)]*\) \{.*?\n\}", CS, re.S)
    assert m, fn_name + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_card_key_and_merge_node():
    harness = (
        _extract("_kgpCardKey") + "\n" + _extract("_kgpMergeCards") + "\n"
        # 상품키: 아마존 ASIN(ref 꼬리·쿼리 무시), 테무 goods, 그 외 정규화.
        "var out = {};\n"
        "out.asin = _kgpCardKey('https://www.amazon.com/dp/B08XYZ1234/ref=sr_1_3?keywords=x');\n"
        "out.goods = _kgpCardKey('https://www.temu.com/kr/thing-g-601099887766.html?_x_sessn=1');\n"
        "out.goodsQ = _kgpCardKey('https://www.temu.com/goods.html?goods_id=42&refer=y');\n"
        "out.plain = _kgpCardKey('https://yoshidakaban.com/products/abc-123/');\n"
        # 병합: 제네릭 [A(dp/ref), B] + 어댑터 [A(dp 정밀), C] → A는 어댑터판, B·C 유지(제네릭 미차단).
        "var generic = ["
        "  {url:'https://www.amazon.com/dp/B08XYZ1234/ref=sr_1', title:'gen-A', price:''},"
        "  {url:'https://www.amazon.com/dp/B0BBBBBBBB', title:'gen-B', price:'10'}"
        "];\n"
        "var adapter = ["
        "  {url:'https://www.amazon.com/dp/B08XYZ1234', title:'adap-A', price:'20', sponsored:true},"
        "  {url:'https://www.amazon.com/dp/B0CCCCCCCC', title:'adap-C', price:'30'}"
        "];\n"
        "var merged = _kgpMergeCards(generic, adapter);\n"
        "out.mergedCount = merged.length;\n"
        "out.titles = merged.map(function(c){return c.title;});\n"
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
    assert out["asin"] == "asin:B08XYZ1234", out
    assert out["goods"] == "goods:601099887766", out
    assert out["goodsQ"] == "goods:42", out
    assert out["plain"] == "https://yoshidakaban.com/products/abc-123", out
    # 병합: 3건(A 하나로 합침 + B + C) — 어댑터 부분매치가 제네릭 B를 막지 않음.
    assert out["mergedCount"] == 3, out
    assert "adap-A" in out["titles"]       # 같은 상품은 어댑터판(정밀) 채택
    assert "gen-A" not in out["titles"]    # 제네릭판은 덮어써짐
    assert "gen-B" in out["titles"]        # 제네릭만 잡은 상품 유지(핵심: 폴백 미차단)
    assert "adap-C" in out["titles"]       # 어댑터만 잡은 상품 추가
