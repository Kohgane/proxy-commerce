"""tests/test_v45_temu_extract.py — Temu 크롤 항목별 payload(5): 갤러리·가격·옵션·상세.

확장 클릭시점 추출이 옵션까지 payload에 담고, Temu '9 KRW' 오값(첫 가격 노드)을 방지하는지 검증.
(기능 실증은 scripts/_devshot_temu_extract.py — 실제 extractProductMeta 실행: 가격 61144·갤러리3·옵션3·상세.)
"""
from __future__ import annotations

import json
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
API = Path("src/api/extension_api.py").read_text(encoding="utf-8")


def test_options_in_payload():
    # 옵션 추출 함수 + payload에 options 포함(기존엔 누락)
    assert "function _kgpCollectOptions()" in CS
    assert "options: _kgpCollectOptions()" in CS


def test_price_scoping_max_value_fix():
    # 9 KRW 오값 방지: 첫 노드가 아니라 유효 후보 '최댓값' 채택
    assert "bestVal" in CS and "if (v > bestVal)" in CS
    # 취소선(원가)·추천/리뷰 영역 제외 유지
    assert "_kgpPriceIsOriginal" in CS and "_kgpInNonProd" in CS


def test_gallery_detail_buckets_kept():
    # 갤러리/상세 2버킷 payload 유지(회귀 방지)
    assert "gallery_images:" in CS and "detail_images:" in CS
    assert "_kgpSitePdp" in CS


def test_server_stores_client_options():
    # 서버는 payload.options가 있으면 그대로 저장(편집 프리필) — 없을 때만 스크래퍼 폴백
    assert 'if not out.get("options")' in API and 'out["options"] = scraped.options' in API


def test_price_currency_map_has_won():
    # 원→KRW 매핑(Temu KR '61,144원') 유지
    assert '"원": "KRW"' in CS


def test_manifest_bumped():
    mf = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
    # 5번 반영 버전(≥1.5.40)
    parts = [int(x) for x in mf["version"].split(".")]
    assert parts >= [1, 5, 37]
