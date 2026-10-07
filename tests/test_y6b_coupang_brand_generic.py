"""Y6-B(오너 결정 2026-10-05 · 적용 2026-10-07) — 쿠팡 brand 칸 GENERIC 규칙.

- 브랜드가 비었거나 / 중국어·비한글 원문이거나 / 쿠팡 브랜드 목록 매칭 실패 → brand="GENERIC".
- 쿠팡 등록 브랜드로 매칭되면 그 이름.
- productGroup·manufacture에 넣던 값은 그대로. 신규 업로드(등록 몸통)부터.
"""
from __future__ import annotations

import json

import pytest

from tests.test_payload_canon_p3 import _PRODUCT, _up


@pytest.fixture
def table(tmp_path, monkeypatch):
    """쿠팡 브랜드 목록 — 테스트용 파일(운영 기본 파일은 비어 있다)."""
    from src.uploaders import coupang_brand as B
    p = tmp_path / "brands.json"
    p.write_text(json.dumps({"brands": {"UGMONK": ["ugmonk", "Ugmonk Inc"], "토라스": ["TORRAS"], "小米": ["xiaomi"]}},
                            ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("COUPANG_BRAND_TABLE", str(p))
    B._table.cache_clear()
    yield B
    B._table.cache_clear()


@pytest.mark.parametrize("brand,want,why", [
    ("", "GENERIC", "브랜드 없음"),
    ("   ", "GENERIC", "브랜드 없음"),
    ("亮妆（家俱）", "GENERIC", "중국어·비한글 원문"),          # 픽스처 3호 브랜드
    ("格斯潘", "GENERIC", "중국어·비한글 원문"),
    ("ヤマザキ", "GENERIC", "중국어·비한글 원문"),
    ("Baronfig", "GENERIC", "쿠팡 브랜드 목록에 없음"),         # 볼트 10-06 실측과 같은 판정
    ("코고가네", "GENERIC", "쿠팡 브랜드 목록에 없음"),
])
def test_generic_cases_with_empty_default_table(brand, want, why, monkeypatch):
    from src.uploaders import coupang_brand as B
    monkeypatch.delenv("COUPANG_BRAND_TABLE", raising=False)
    B._table.cache_clear()
    assert B.table() == {}                                      # 이 레포 기본 목록은 비어 있다(정직)
    assert B.coupang_brand(brand) == (want, why)


def test_matched_brand_uses_coupang_name(table):
    assert table.coupang_brand("UGMONK") == ("UGMONK", "쿠팡 브랜드 목록 매칭")
    assert table.coupang_brand("ugmonk inc") == ("UGMONK", "쿠팡 브랜드 목록 매칭")       # 대소문자·공백 무시
    assert table.coupang_brand("TORRAS") == ("토라스", "쿠팡 브랜드 목록 매칭")
    assert table.coupang_brand("xiaomi") == ("GENERIC", "쿠팡 브랜드 목록에 없음")        # 쿠팡 표기가 한자인 줄은 안 씀
    assert table.coupang_brand("Baronfig")[0] == "GENERIC"


def test_payload_brand_generic_product_group_unchanged(monkeypatch):
    from src.uploaders import coupang_brand as B
    monkeypatch.delenv("COUPANG_BRAND_TABLE", raising=False)
    B._table.cache_clear()
    for brand in ("", "亮妆（家俱）", "TORRAS"):
        p = _up(monkeypatch)._build_product_payload(dict(_PRODUCT, brand=brand))
        assert p["brand"] == "GENERIC"
        assert p["productGroup"] == brand and p["manufacture"] == (brand or "상세페이지 참조")   # 넣던 값 그대로


def test_payload_brand_matched(table, monkeypatch):
    p = _up(monkeypatch)._build_product_payload(dict(_PRODUCT, brand="Ugmonk"))
    assert p["brand"] == "UGMONK" and p["productGroup"] == "Ugmonk"


def test_generic_is_not_flagged_as_foreign():
    from src.uploaders.coupang_uploader import CoupangUploader
    assert CoupangUploader.foreign_fields({"brand": "GENERIC", "sellerProductName": "중고풍 티테이블"}) == []


def test_default_table_file_is_valid_and_empty():
    import pathlib
    raw = json.loads(pathlib.Path("src/uploaders/coupang_brands.json").read_text(encoding="utf-8"))
    assert raw["brands"] == {} and "GENERIC" in raw["_doc"]
