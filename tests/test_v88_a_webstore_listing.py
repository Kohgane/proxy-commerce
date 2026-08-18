"""tests/test_v88_a_webstore_listing.py — v88-A: 크롬 웹스토어 게시 패키지 완비 계약.

오너 결정: 웹스토어 게시(Unlisted 시작). 이 계약은 게시 패키지가 완비됐고, 특히 **manifest에 선언된
모든 권한이 스토어 심사용 정당화 문안을 갖는지**(권한 추가 시 정당화 누락 드리프트 방지)를 못박는다.
게시·심사 제출 자체는 오너 클릭(코드 아님).
"""
from __future__ import annotations

import json
from pathlib import Path

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
LISTING = (EXT / "STORE_LISTING.md").read_text(encoding="utf-8")


def test_store_listing_exists_and_bilingual():
    assert LISTING.strip(), "STORE_LISTING.md 비어 있음"
    assert "상세 설명 — 한국어" in LISTING and "상세 설명 — English" in LISTING
    assert "Single purpose" in LISTING or "단일 목적" in LISTING


def test_every_declared_permission_has_justification():
    """manifest의 모든 permissions + host_permissions가 §2 정당화 표에 등장(누락 0)."""
    for perm in MANIFEST.get("permissions", []):
        assert f"`{perm}`" in LISTING, ("권한 정당화 누락", perm)
    # host_permissions(<all_urls>)도 정당화.
    for host in MANIFEST.get("host_permissions", []):
        assert host in LISTING, ("host 권한 정당화 누락", host)
    assert "host_permissions: <all_urls>" in LISTING
    assert "content_scripts: <all_urls>" in LISTING   # 콘텐츠 스크립트 광범위 매치도 별도 정당화


def test_privacy_and_visibility_and_artifact():
    # 개인정보 URL(콘솔 기존 페이지 재사용) + Unlisted 시작 + zip 아티팩트 경로.
    assert "/privacy" in LISTING
    assert "Unlisted" in LISTING
    assert "build_extension_zip.py" in LISTING


def test_owner_action_table_present():
    # 심사 제출은 오너 클릭 — 오너 액션 표에 등록비·명의·업로드·제출 단계.
    assert "오너 액션" in LISTING
    for kw in ["$5", "명의", "Unlisted", "Submit for review"]:
        assert kw in LISTING, ("오너 액션 항목 누락", kw)


def test_privacy_route_actually_served():
    # 재사용하는 개인정보 페이지가 실제 라우트로 존재(죽은 URL 금지).
    legal = Path("src/legal/views.py").read_text(encoding="utf-8")
    assert '"/privacy"' in legal or "'/privacy'" in legal
