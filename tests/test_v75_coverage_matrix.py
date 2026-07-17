"""tests/test_v75_coverage_matrix.py — v75 STEP1: 디폴트 마켓 커버리지 매트릭스(전수·정직).

전 디폴트 마켓의 9항목(목록·호버·상세·제목·가격+통화·갤러리·옵션·상세·리뷰) 지원 수준을 명문화.
근거는 실페이지 하네스 픽스처의 실제 어서션뿐(추측 기입 금지). 픽스처 없으면 '미검증' + 오너 스냅샷 요청.
가드: (1)claim한 fixture·필드가 실제 expected.json에 있는지 강제 → '진단 없는 지원' 차단, (2)매트릭스 문서가
레지스트리에서 파생돼 드리프트 0, (3)가이드 페이지 배지 렌더.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

from src.collectors.sourcing_registry import (  # noqa: E402
    DEFAULT_SOURCING_SITES, coverage_matrix_rows, registry_rows, snapshot_needed,
)

FIX = Path("fixtures/realpages")

# 커버리지 필드 → expected.json 어서션 키(있어야 그 필드 '검증됨' 주장 가능).
_FIELD_TO_SPEC = {
    "title": "title_contains",
    "price": "price",
    "currency": "currency",
    "gallery": "images_min",
    "options": "options",
    "description": "description_contains",   # 비어있지 않아야 검증으로 인정
}


def test_coverage_claims_are_fixture_backed():
    """level=full/partial로 claim한 필드는 반드시 해당 fixture의 expected.json이 실제로 어서션해야 한다."""
    for s in DEFAULT_SOURCING_SITES:
        cov = s.get("coverage") or {}
        level = cov.get("level", "unverified")
        if level == "unverified":
            assert cov.get("needs_snapshot") is True, s["id"]
            assert "fields" not in cov, ("미검증인데 필드 claim(가짜 지원)!", s["id"])
            continue
        fx = cov.get("fixture")
        assert fx, ("검증 레벨인데 fixture 없음", s["id"])
        expected = FIX / (fx + ".expected.json")
        assert expected.exists(), ("claim한 fixture expected.json 없음", s["id"], fx)
        spec = json.loads(expected.read_text(encoding="utf-8"))
        for f in (cov.get("fields") or []):
            key = _FIELD_TO_SPEC.get(f)
            if key is None:
                continue
            assert key in spec, ("필드 claim이 fixture에 근거 없음(추측 기입)", s["id"], f, key)
            if f == "description":
                assert (spec.get(key) or "").strip(), ("description 검증 주장인데 빈 어서션", s["id"])


def test_matrix_doc_derived_from_registry():
    """docs/coverage_matrix.md가 레지스트리에서 파생(수기 드리프트 0) — 재생성 결과와 동일."""
    from scripts.gen_coverage_matrix import render
    doc = Path("docs/coverage_matrix.md")
    assert doc.exists()
    assert doc.read_text(encoding="utf-8") == render(), "coverage_matrix.md가 레지스트리와 불일치 — python scripts/gen_coverage_matrix.py 재실행"


def test_matrix_has_all_default_markets():
    rows = coverage_matrix_rows()
    ids = {r["id"] for r in rows}
    assert ids == {s["id"] for s in DEFAULT_SOURCING_SITES}
    # 버튼 3열은 전 마켓 보장(제네릭).
    for r in rows:
        assert r["list_btn"] == "✓" and r["hover"] == "✓" and r["detail_btn"] == "✓", r


def test_verified_markets_present():
    """현재 하네스 검증 완료 마켓(아마존·테무=완전, 알리=부분)이 매트릭스에 반영."""
    by_id = {r["id"]: r for r in coverage_matrix_rows()}
    assert by_id["amazon"]["level"] == "full" and by_id["amazon"]["price"] == "✓"
    assert by_id["temu"]["level"] == "full" and by_id["temu"]["gallery"] == "✓"
    assert by_id["aliexpress"]["level"] == "partial" and by_id["aliexpress"]["options"] == "✓"
    # 미검증 마켓은 3핵심이 '픽스처 필요'.
    assert by_id["rakuten"]["title"] == "픽스처 필요" and by_id["rakuten"]["price"] == "픽스처 필요"


def test_snapshot_request_list():
    needed = {m["id"] for m in snapshot_needed()}
    # 픽스처 미보유 마켓 전부 요청 목록에(라쿠텐·야후·아마존JP류 포함).
    assert "rakuten" in needed and "yahoo" in needed and "taobao" in needed
    # 검증 완료 마켓은 요청 목록에서 제외.
    assert "amazon" not in needed and "temu" not in needed and "aliexpress" not in needed


def test_guide_page_renders_badges(flask_client):
    with flask_client.session_transaction() as sess:
        sess["user_id"] = "u_guide"
    r = flask_client.get("/seller/guide/sources")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "추출 지원" in html                      # 새 컬럼 헤더
    assert "완전 지원" in html and "부분 지원" in html and "미검증" in html   # 배지 3종
    assert "스냅샷 필요 마켓" in html               # 오너 스냅샷 요청 섹션
