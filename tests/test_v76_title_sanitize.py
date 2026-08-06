"""tests/test_v76_title_sanitize.py — v76 STEP1: 제목 새니타이저(전 마켓 공통).

사이트명 접두("Amazon.com: ", 【楽天市場】)·접미(" | 吉田カバン", " - AliExpress", "｜楽天市場") 제거 +
제네릭(구분자 뒤 세그먼트가 도메인 브랜드명과 일치 시 제거). 계약: 제목에 사이트명 0(상품명 본문 보존).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.138"


# ── source-contract: 새니타이저 함수 + 최종 제목에 적용 ──
def test_sanitize_source():
    assert "function _sanitizeTitle(t, url)" in EX
    assert "function _brandFromHost(url)" in EX
    assert "var _SITE_BRAND_RE" in EX
    assert "title = _sanitizeTitle(title, location.href)" in EX   # 최종 제목에 적용(전 마켓)


# ── node: 8종 오염 패턴 → 사이트명 0 (계약) ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_sanitize_patterns_node():
    def grab(name):
        i = EX.index("function " + name + "(")
        j = EX.index("\n  }\n", i) + 4
        return EX[i:j]
    re_line = re.search(r"var _SITE_BRAND_RE = [^\n]+", EX).group(0)
    src = re_line + "\n" + grab("_brandFromHost") + "\n" + grab("_sanitizeTitle") + "\n"
    cases = [
        ["Amazon.com: BENKS 3-in-1 Wireless Charger", "https://www.amazon.com/dp/B0", "BENKS 3-in-1 Wireless Charger"],
        ["PORTER TANKER ショルダーバッグ | 吉田カバン", "https://www.yoshidakaban.com/products/1", "PORTER TANKER ショルダーバッグ"],
        ["수제 소가죽 크로스백 | 요시다", "https://www.yoshidakaban.com/products/2", "수제 소가죽 크로스백"],
        ["【楽天市場】折りたたみ椅子 アウトドア", "https://item.rakuten.co.jp/shop/x", "折りたたみ椅子 アウトドア"],
        ["ミニブレンダー - AliExpress", "https://www.aliexpress.com/item/1.html", "ミニブレンダー"],
        ["접이식 트렁크 정리함", "https://www.temu.com/g-1.html", "접이식 트렁크 정리함"],
        ["Cool Gadget | someshop", "https://www.someshop.com/p/1", "Cool Gadget"],
        ["折りたたみ椅子｜楽天市場", "https://item.rakuten.co.jp/shop/y", "折りたたみ椅子"],
    ]
    harness = (
        src +
        "var C = " + json.dumps(cases, ensure_ascii=False) + ";\n"
        "var out = C.map(function(c){ return _sanitizeTitle(c[0], c[1]); });\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    site_re = re.compile(r"(amazon|aliexpress|楽天市場|吉田カバン|요시다|rakuten|someshop)", re.I)
    for (inp, url, exp), got in zip(cases, out):
        assert got == exp, ("정규화 결과 불일치", inp, got, exp)
        assert not site_re.search(got), ("사이트명 잔존", inp, got)


# ── 실페이지 하네스: 전 픽스처 제목에 사이트명 0 계약(회귀 방지) ──
def test_all_fixtures_have_title_excludes():
    fixdir = Path("fixtures/realpages")
    checked = 0
    for exp in fixdir.glob("*.expected.json"):
        spec = json.loads(exp.read_text(encoding="utf-8"))
        if "title_contains" in spec:
            # 제목 계약이 있는 픽스처는 사이트명 배제 목록도 있어야(정직 회귀 가드).
            assert "title_excludes" in spec, ("title_excludes 누락", exp.name)
            assert spec["title_excludes"], exp.name
            checked += 1
    assert checked >= 4   # amazon-dp·temu·ali·yoshida-detail 최소
