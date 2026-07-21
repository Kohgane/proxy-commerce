"""tests/test_v71_currency_locale.py — v71 STEP1: 통화 로케일 추론(버그① 통화 빈 값).

증상: tier1 가격 11235는 채택됐는데 통화 필드가 비어 sanity 게이트가 needs_check로 가격을 누락 처리.
수리: 통화 사다리 tier1 → DOM 기호 → **어댑터 로케일 기본값**(temu/kr·ko→KRW, amazon.com→USD,
amazon.co.jp·라쿠텐·요시다→JPY) → 그래도 불명이면 통화 미확인 유지. 근거는 html lang·경로·도메인만(무근거 추정 0).
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
    assert MANIFEST["version"] == "1.5.113"


def test_source_contract():
    assert "function _localeCurrency()" in EX
    # 가격 있음 + 통화 빔 → 로케일 추론(3번째 사다리).
    assert "if (price && !currency) {" in EX
    assert "lc = _localeCurrency();" in EX
    assert "currency = lc; currencyLocale = true;" in EX
    # 로그에 (locale) 근거 표기.
    assert 'currencyLocale ? "(locale)" : ""' in EX


def _fn(name):
    m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{.*?\n  \}", EX, re.S)
    assert m, name + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_locale_currency_ladder_node():
    harness = _fn("_localeCurrency") + "\n" + r"""
function decide(host, path, lang){
  global.location = { hostname: host, pathname: path };
  global.document = { documentElement: { lang: lang } };
  return _localeCurrency();
}
var out = {
  temu_kr: decide("www.temu.com", "/kr/goods-1.html", "ko"),
  temu_ko_lang: decide("www.temu.com", "/goods-1.html", "ko-KR"),
  ali_ko: decide("ko.aliexpress.com", "/item/1.html", "ko"),
  amazon_com: decide("www.amazon.com", "/dp/X", "en-US"),
  amazon_jp: decide("www.amazon.co.jp", "/dp/X", "ja"),
  rakuten: decide("item.rakuten.co.jp", "/x/", "ja"),
  yoshida: decide("www.yoshidakaban.com", "/products/x", "ja"),
  yahoo_jp: decide("shopping.yahoo.co.jp", "/x", "ja"),
  taobao: decide("item.taobao.com", "/x", "zh-CN"),
  amazon_uk: decide("www.amazon.co.uk", "/dp/X", "en-GB"),
  amazon_de: decide("www.amazon.de", "/dp/X", "de"),
  unknown: decide("shop.random-store.com", "/p/1", "")
};
process.stdout.write(JSON.stringify(out) + "\n");
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["temu_kr"] == "KRW" and out["temu_ko_lang"] == "KRW"
    assert out["ali_ko"] == "KRW"
    assert out["amazon_com"] == "USD"
    assert out["amazon_jp"] == "JPY" and out["rakuten"] == "JPY" and out["yoshida"] == "JPY" and out["yahoo_jp"] == "JPY"
    assert out["taobao"] == "CNY"
    assert out["amazon_uk"] == "GBP" and out["amazon_de"] == "EUR"
    assert out["unknown"] == ""   # 근거 없으면 빈 통화(무근거 추정 0)
