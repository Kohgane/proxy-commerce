"""tests/test_extension_amazon_products_v25.py — v25 P0: 아마존 '전체 수집' 실제 상품만.

전체선택 시 Amazon Music·광고(스폰서)·미디어 카드까지 잡히던 문제 →
아마존 어댑터가 유효 ASIN(10자) + 비-스폰서 + 가격/이미지/제목을 모두 갖춘 카드만 상품으로.
(JS 런타임은 브라우저 전용 → 소스 계약을 정적으로 핀 + ASIN 정규식은 node로 실동작 검증.)
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_amazon_requires_valid_asin():
    # 유효 ASIN(10자) 필수로 비-상품 위젯(뮤직/앱/프로모) 제외 — v25 핵심.
    assert "function _kgpAmazonSponsored" in CS
    assert "/^[A-Z0-9]{10}$/.test(asin)" in CS
    # v45 P3: 스폰서 라벨 셀렉터는 유지(태깅용) — 스폰서 라벨 판별 자체는 계속 존재.
    assert "s-sponsored-label-text" in CS
    assert "sp-sponsored-result" in CS


def test_v45_p3_sponsored_products_included_not_excluded():
    """v45 P3(최신 우선): 스폰서 상품도 수집 대상(제외 아님) — 유효 ASIN이면 소싱 가능.
    _kgpAmazonSponsored는 '제외'가 아니라 카드에 sponsored 플래그로 태깅만 한다."""
    # 셀렉터 확장: data-asin 카드 전부(레이아웃 변형·스폰서 커버)
    assert 'div[data-asin]:not([data-asin=""])' in CS
    # 스폰서를 return(제외)하지 않고 태깅 — 'if (_kgpAmazonSponsored(el)) return' 패턴이 없어야 함.
    assert "if (_kgpAmazonSponsored(el)) return" not in CS
    assert "sponsored: sponsored" in CS   # 카드 객체에 태깅


def test_scanned_vs_product_count_surfaced():
    # 정직한 '전체 N개 중 상품 M개' 표기
    assert "_kgpScannedCount" in CS
    assert "전체 ${_kgpScannedCount}개 중 상품 ${_kgpCards.length}개" in CS


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_asin_regex_distinguishes_products():
    """ASIN 정규식이 실제 상품(B0…10자)만 통과시키고 뮤직/광고/빈값은 거른다."""
    script = r"""
    const re = /^[A-Z0-9]{10}$/;
    const cases = {
      "B08N5WRWNW": true,    // 정상 상품 ASIN
      "B0CHX1W1XY": true,
      "": false,             // ASIN 없음(프로모 위젯)
      "amazon-music": false, // 미디어 위젯
      "AD": false,           // 광고 슬롯
      "TOOLONGASIN12": false
    };
    let ok = true;
    for (const [k, exp] of Object.entries(cases)) {
      if (re.test(k) !== exp) { console.log("FAIL", k); ok = false; }
    }
    console.log(ok ? "PASS" : "FAIL");
    """
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("PASS"), out.stdout


def test_manifest_version_bumped():
    import json
    mf = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
    parts = [int(x) for x in mf["version"].split(".")]
    assert parts >= [1, 5, 12], mf["version"]
