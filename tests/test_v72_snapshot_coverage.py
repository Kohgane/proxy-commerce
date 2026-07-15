"""tests/test_v72_snapshot_coverage.py — v72 STEP5: 스냅샷 하네스 정기 판정(5필드 커버리지 계약).

v70 STEP5 규약 지속 — 오너 제공 테무 스냅샷 + 아마존 픽스처로 [price·currency·images·options·desc]를
스냅샷 CI로 상시 판정. 이 계약 테스트가 두 대표 픽스처의 5필드 커버리지를 강제(미래 변경이 필드를 조용히
빠뜨리지 못하게). 실제 추출 검증은 test_v70_realpage_harness(Playwright 실 크로미움)가 수행.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIX_DIR = Path("fixtures/realpages")

# 5필드 대표 픽스처(아마존 상세 + 테무 상세) — 각각 [가격·통화·이미지·옵션·상세] 계약을 모두 담아야 함.
FIVE_FIELD_FIXTURES = ["synthetic-amazon-dp", "synthetic-temu-detail"]


@pytest.mark.parametrize("name", FIVE_FIELD_FIXTURES)
def test_snapshot_fixture_covers_five_fields(name):
    spec = json.loads((FIX_DIR / (name + ".expected.json")).read_text(encoding="utf-8"))
    html = (FIX_DIR / (name + ".html"))
    assert html.exists(), name + ".html 없음"
    # [price·currency·images·options·desc] 5필드 계약 모두 존재(정기 판정 커버리지).
    assert spec.get("price"), (name, "price 계약 누락")
    assert spec.get("currency"), (name, "currency 계약 누락")
    assert spec.get("images_min") is not None, (name, "images 계약 누락")
    assert spec.get("options") and len(spec["options"]) >= 1, (name, "options 계약 누락")
    assert spec.get("description_contains"), (name, "desc 계약 누락")
    # url(호스트로 추출 분기 결정) 필수.
    assert spec.get("url", "").startswith("http"), (name, "url 누락")


def test_temu_and_amazon_hosts_present():
    # 테무·아마존 호스트가 픽스처 URL에 반영(추출 분기·로케일 근거).
    amazon = json.loads((FIX_DIR / "synthetic-amazon-dp.expected.json").read_text(encoding="utf-8"))
    temu = json.loads((FIX_DIR / "synthetic-temu-detail.expected.json").read_text(encoding="utf-8"))
    assert "amazon." in amazon["url"]
    assert "temu.com" in temu["url"]
    # 테무 통화 로케일(KRW) + 아마존 USD — v71/v72 수리 반영.
    assert temu["currency"] == "KRW" and amazon["currency"] == "USD"


def test_harness_gate_documented_in_claude_md():
    # 추출 로직 변경 시 하네스 통과 필수 규약이 CLAUDE.md에 상존(v70 STEP5 지속).
    txt = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "실페이지 하네스 통과 필수" in txt
    assert "test_v70_realpage_harness" in txt
