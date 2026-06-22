"""tests/test_extension_sourcing_v10.py — v10 확장 가드.

지정 소싱처에서만 노출 + 실제 제품만 감지 + 소싱처 관리 UI를 정적으로 검증한다.
(JS 런타임은 브라우저 전용이라 소스 구조/계약을 핀으로 고정한다.)
"""
from __future__ import annotations

import json
from pathlib import Path

EXT = Path("extensions/chrome-collector")


def _read(name: str) -> str:
    return (EXT / name).read_text(encoding="utf-8")


def test_content_script_has_sourcing_gate():
    cs = _read("content_script.js")
    # 허용목록 게이팅 함수 + 렌더 경로에서 호출
    assert "function kgpHostAllowed" in cs
    assert "function kgpTeardown" in cs
    assert "if (!kgpHostAllowed())" in cs
    # 설정 로드 + 런타임 즉시 반영
    assert "kgp_sources" in cs
    assert "chrome.storage.onChanged" in cs


def test_default_sources_present():
    cs = _read("content_script.js")
    for host in ["taobao", "tmall", "1688", "temu", "amazon", "aliexpress"]:
        assert host in cs, f"기본 소싱처 {host} 누락"


def test_real_product_detection_adapters():
    cs = _read("content_script.js")
    # 아마존 어댑터(실제 제품 카드 컨테이너) + 엄격 폴백 + 추천/푸터 제외
    assert 's-search-result' in cs
    assert "_kgpAmazonCards" in cs
    assert "_kgpGenericCards" in cs
    assert "_kgpInBadRegion" in cs
    # 제외 키워드(추천/푸터/캐러셀/광고/본 적 있음)
    for kw in ["footer", "recommend", "carousel", "viewed"]:
        assert kw in cs


def test_options_has_source_management():
    html = _read("options.html")
    js = _read("options.js")
    assert "소싱처 관리" in html
    assert "addHostBtn" in html and "customHost" in html
    assert "kgp_sources" in js
    assert "chrome.storage.local" in js


def test_popup_shows_source_indicator():
    html = _read("popup.html")
    js = _read("popup.js")
    assert "srcBadge" in html
    assert "소싱처 관리" in html
    assert "updateSourceBadge" in js


def test_manifest_version_bumped():
    manifest = json.loads(_read("manifest.json"))
    parts = [int(x) for x in manifest["version"].split(".")]
    assert parts >= [1, 5, 0], f"manifest 버전이 1.5.0+ 이어야 함: {manifest['version']}"
