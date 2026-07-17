"""tests/test_v75_my_sources_diagnosis.py — v75 STEP2: My Sources 자가진단.

유저 등록 소싱처의 상품 페이지 1곳에서 테스트 추출 → [제목·가격·이미지·옵션·상세] 필드별 ○/× 를
카드에 저장·표시. 3핵심(제목·가격·이미지) 미달=수동 보완 필요(등록/수집 차단 아님). 제네릭 추출기는
ld+json Product → og/meta → DOM 순서로 작동(요시다 제네릭 계약 픽스처로 3핵심 검증).
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

import pytest

from src.seller_console import my_sources_store as store


# ── 순수 진단 로직: 필드별 ○/× + 3핵심 ──
def test_diag_from_scraped_full():
    d = store.diag_from_scraped({
        "title": "포터 탱커 숄더백", "price": "19800", "images": ["a.jpg", "b.jpg"],
        "options": [{"name": "색상", "values": ["블랙"]}], "description": "원목 상세…",
    })
    assert d["fields"] == {"title": True, "price": True, "image": True, "options": True, "description": True}
    assert d["core3_ok"] is True and d["missing_core"] == []
    assert set(d["supported"]) == {"title", "price", "image", "options", "description"}


def test_diag_from_scraped_core_shortfall():
    # 가격·이미지 없음 → 3핵심 미달(수동 보완 필요), 등록은 별개(차단 아님).
    d = store.diag_from_scraped({"title": "제목만 있음", "price": "", "images": []})
    assert d["core3_ok"] is False
    assert set(d["missing_core"]) == {"price", "image"}
    assert d["fields"]["title"] is True and d["fields"]["price"] is False


def test_diag_from_scraped_empty():
    d = store.diag_from_scraped({})
    assert d["core3_ok"] is False and set(d["missing_core"]) == {"title", "price", "image"}


# ── 저장/조회 round-trip ──
def test_save_and_get_diagnosis(monkeypatch):
    monkeypatch.setattr(store, "_SHEET_ID", None, raising=False)
    store._in_memory.clear()
    store.add_source("shop.example.com", skip_probe=True)
    diag = store.diag_from_scraped({"title": "T", "price": "100", "images": ["i.jpg"]})
    assert store.save_diagnosis("shop.example.com", diag) is True
    got = store.get_source("shop.example.com")
    assert got and got.get("diag_json")
    import json
    parsed = json.loads(got["diag_json"])
    assert parsed["core3_ok"] is True


def test_save_diagnosis_auto_registers(monkeypatch):
    # 진단만 하고 미등록이어도 자동 등록(차단 아님).
    monkeypatch.setattr(store, "_SHEET_ID", None, raising=False)
    store._in_memory.clear()
    diag = store.diag_from_scraped({"title": "T", "price": "1", "images": ["i.jpg"]})
    store.save_diagnosis("newshop.example.org", diag)
    assert store.get_source("newshop.example.org") is not None


# ── 제네릭 추출기 순서 감사(ld+json Product → og → DOM) — 요시다형 제네릭 계약 픽스처 ──
def test_generic_extractor_ldjson_first_3core():
    """어댑터 없는 사이트도 제네릭(ld+json Product)으로 3핵심(제목·가격·이미지)이 나온다."""
    from src.collectors.universal_scraper import UniversalScraper
    html = Path("fixtures/realpages/synthetic-generic-detail.html").read_text(encoding="utf-8")
    sp = UniversalScraper().parse_html(html, "https://www.yoshidakaban.com/products/porter-1")
    d = sp.to_dict()
    diag = store.diag_from_scraped(d)
    assert diag["fields"]["title"] and diag["fields"]["price"] and diag["fields"]["image"], (d, diag)
    assert diag["core3_ok"] is True   # 제네릭만으로 3핵심 충족(요시다 검증 사례)


def test_generic_extractor_source_order():
    # universal_scraper 우선순위 명문: JSON-LD 최우선 → OG → 휴리스틱.
    src = Path("src/collectors/universal_scraper.py").read_text(encoding="utf-8")
    assert "JSON-LD" in src or "json-ld" in src.lower()
    assert "og:title" in src or "Open Graph" in src


# ── 진단 라우트(확장 자가진단 결과 직접 반영 경로) ──
def test_diagnose_route_with_scraped(flask_client, monkeypatch):
    monkeypatch.setattr(store, "_SHEET_ID", None, raising=False)
    store._in_memory.clear()
    with flask_client.session_transaction() as s:
        s["user_id"] = "u_diag"
    r = flask_client.post("/seller/sourcing/my-sources/diagnose", json={
        "domain": "brandshop.example.com",
        "url": "https://brandshop.example.com/product/1",
        "scraped": {"title": "테스트 상품", "price": "5000", "images": ["x.jpg"], "options": [], "description": ""},
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    assert d["ok"] is True
    assert d["diag"]["fields"]["title"] is True and d["diag"]["fields"]["price"] is True
    assert d["diag"]["core3_ok"] is True
    # 저장돼 카드에 반영.
    assert store.get_source("brandshop.example.com") is not None


def test_diagnose_route_partial_not_blocking(flask_client, monkeypatch):
    monkeypatch.setattr(store, "_SHEET_ID", None, raising=False)
    store._in_memory.clear()
    with flask_client.session_transaction() as s:
        s["user_id"] = "u_diag"
    r = flask_client.post("/seller/sourcing/my-sources/diagnose", json={
        "domain": "weakshop.example.com",
        "scraped": {"title": "제목만", "price": "", "images": []},
    })
    d = r.get_json()
    assert d["ok"] is True and d["diag"]["core3_ok"] is False   # 미달이어도 ok(차단 아님) + 정직 표기
    assert set(d["diag"]["missing_core"]) == {"price", "image"}


# ── My Sources 페이지: 진단 UI 렌더 ──
def test_sourcing_page_renders_diag_ui(flask_client, monkeypatch):
    monkeypatch.setattr(store, "_SHEET_ID", None, raising=False)
    store._in_memory.clear()
    store.add_source("diagshop.example.com", skip_probe=True)
    store.save_diagnosis("diagshop.example.com", store.diag_from_scraped({"title": "T", "price": "", "images": []}))
    with flask_client.session_transaction() as s:
        s["user_id"] = "u_diag"
    r = flask_client.get("/seller/sourcing")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "registry-diag-btn" in html            # 진단 버튼
    assert "수동 보완 필요" in html                # 3핵심 미달 배지(등록 유지)
