"""tests/test_v87_w1_collect_hygiene.py — v87-W1 수집 목록 위생 계약.

비상품 판별기(오탐 0·고한계) + 유입 봉인(경고, 거부 아님) + 정리 후보 필터 뷰 + UI 계약 +
자동삭제 금지 + 인위회귀(판별기 무력화 → 194 미검출).

실상품 오탐 0 픽스처 = 오너 업로드 Temu 상품(g-601104878115983, 12730 KRW, 이미지 9)에서 파생한 행.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.seller_console.collect_hygiene import (
    classify_row,
    is_cleanup_candidate,
    summarize_candidates,
)
import src.seller_console.collect_hygiene as hyg

# ── 픽스처 ────────────────────────────────────────────────
REAL_TEMU = {  # 오너 업로드 실상품(오탐 절대 금지)
    "id": "r1",
    "url": "https://www.temu.com/kr/%ED%81%90%EB%B8%8C-g-601104878115983.html?_oak_mp_inf=x&search_key=speaker",
    "title": "큐브 매직큐브 RGB 조명 휴대용 무선 스피커",
    "price": "12730", "currency": "KRW",
    "image_url": "https://img.kwcdn.com/product/x.jpg",
    "extra_json": json.dumps({"images": ["a", "b", "c"], "options": [{"name": "색상"}]}),
}
REAL_PRODUCTS = [
    REAL_TEMU,
    {"id": "r2", "url": "https://www.amazon.com/dp/B0BWFF", "title": "Card Case", "price": "", "image_url": "", "extra_json": "{}"},
    {"id": "r3", "url": "https://item.rakuten.co.jp/shop/abc123/", "title": "가방", "price": "7480", "currency": "JPY", "image_url": "https://x/y.jpg", "extra_json": json.dumps({"images": ["a"]})},
    {"id": "r4", "url": "https://niche-shop.example/product/9981", "title": "니치 실상품", "price": "29000", "image_url": "https://x/z.jpg", "extra_json": json.dumps({"images": ["a"]})},
    {"id": "r5", "url": "https://www.aliexpress.com/item/1005006.html", "title": "케이블", "price": "", "image_url": "", "extra_json": "{}"},
]
NON_PRODUCTS = [
    {"id": "n1", "url": "https://www.icloud.com/mail/", "title": "QA-TEST- iCloud Mail", "price": "", "image_url": "", "extra_json": "{}"},
    {"id": "n2", "url": "https://chatgpt.com/c/abc-123", "title": "QA-TEST- ChatGPT", "price": "", "image_url": "", "extra_json": "{}"},
    {"id": "n3", "url": "https://mail.google.com/mail/u/0/#inbox", "title": "QA-TEST- 받은편지함", "price": "", "image_url": "", "extra_json": "{}"},
    {"id": "n4", "url": "https://www.google.com/search?q=speaker", "title": "QA-TEST- speaker 검색", "price": "", "image_url": "", "extra_json": "{}"},
    {"id": "n5", "url": "https://blog.naver.com/someone/12345", "title": "QA-TEST- 블로그", "price": "", "image_url": "", "extra_json": "{}"},
    {"id": "n6", "url": "https://docs.google.com/document/d/xyz/edit", "title": "QA-TEST- 문서", "price": "", "image_url": "", "extra_json": "{}"},
    {"id": "n7", "url": "https://github.com/owner/repo", "title": "QA-TEST- repo", "price": "", "image_url": "", "extra_json": "{}"},
]


# ── 판별기 계약 ──────────────────────────────────────────
def test_zero_false_positive_on_real_products():
    for row in REAL_PRODUCTS:
        assert not is_cleanup_candidate(row), f"실상품 오탐: {row['url']}"


def test_catches_known_non_products_with_reasons():
    for row in NON_PRODUCTS:
        c = classify_row(row)
        assert c["is_candidate"], f"비상품 미검출: {row['url']}"
        assert c["score"] >= 70 and c["reasons"], f"점수/사유 없음: {row['url']}"


def test_shopping_host_early_return_even_when_empty():
    # 쇼핑 도메인은 가격·이미지·옵션 전무여도 절대 후보 아님(거부보다 미검출).
    empty_amazon = {"url": "https://www.amazon.co.jp/dp/X", "title": "", "price": "", "image_url": "", "extra_json": "{}"}
    assert not is_cleanup_candidate(empty_amazon)


def test_summarize_three_numbers():
    rep = summarize_candidates(REAL_PRODUCTS + NON_PRODUCTS)
    assert rep["total"] == len(REAL_PRODUCTS) + len(NON_PRODUCTS)
    assert rep["candidates"] == len(NON_PRODUCTS)          # 잡은 수
    assert rep["kept"] == len(REAL_PRODUCTS)               # 유지(실상품)
    assert len(rep["samples"]) == len(NON_PRODUCTS)


def test_artificial_regression_194(monkeypatch):
    """인위회귀: 194 비상품(+ 실상품 20) → 전량 검출·오탐 0(green).
    판별기 무력화(한계 ∞) → 0 검출(red 신호)."""
    non = [{"id": f"n{i}", "url": f"https://www.icloud.com/mail/#m{i}", "title": f"QA-TEST- mail {i}",
            "price": "", "image_url": "", "extra_json": "{}"} for i in range(194)]
    real = [dict(REAL_TEMU, id=f"r{i}") for i in range(20)]
    rep = summarize_candidates(non + real)
    assert rep["total"] == 214
    assert rep["candidates"] == 194          # 잡은 수 = 194
    assert rep["kept"] == 20                 # 실상품 오탐 0
    # 무력화 → 미검출(red를 실증).
    monkeypatch.setattr(hyg, "_CANDIDATE_THRESHOLD", 10 ** 9)
    rep2 = summarize_candidates(non + real)
    assert rep2["candidates"] == 0, "판별기 무력화 시 후보가 잡히면 회귀 가드가 무의미"


def test_no_auto_delete_in_module():
    src = Path("src/seller_console/collect_hygiene.py").read_text(encoding="utf-8")
    # 판별기는 후보 제시만 — 저장소를 건드리는 부수효과가 전무해야 한다(자동 삭제/보관 금지).
    for bad in ("collect_history_store", "delete_ids", "DELETE FROM", "from src.db",
                ".delete(", ".update(", "run_ddl", "backup"):
        assert bad not in src, f"판별기에 데이터 변경 부수효과 의심: {bad}"


# ── 유입 봉인(경고, 거부 아님) ──────────────────────────
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _clear():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def test_intake_seal_warns_but_saves_non_product(client):
    _clear()
    r = client.post("/api/v1/collect/extension", json={
        "url": "https://www.icloud.com/mail/", "title": "iCloud Mail"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True                              # 저장 거부 아님(오탐으로 실상품 막지 않음)
    assert data.get("hygiene_warning") and data["hygiene_warning"]["is_candidate"]
    from src.seller_console import collect_history_store as ch
    row = ch.list_items(seller_ids={"u1"})[0]
    ex = json.loads(row.get("extra_json") or "{}")
    assert ex.get("hygiene", {}).get("is_candidate") is True   # 사유 기록


def test_intake_seal_real_product_no_warning(client):
    _clear()
    r = client.post("/api/v1/collect/extension", json={
        "url": "https://www.temu.com/kr/g-601104878115983.html", "title": "무선 스피커",
        "price": "12730", "currency": "KRW", "images": ["https://img.kwcdn.com/x.jpg"]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data.get("hygiene_warning") is None                 # 실상품 경고 0


# ── 정리 후보 필터 뷰 ────────────────────────────────────
def test_view_cleanup_filter_returns_only_candidates(client, monkeypatch):
    _clear()
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_seller_id", lambda: "u1")
    monkeypatch.setattr(views, "_seller_identities", lambda: {"u1"})
    from src.seller_console import collect_history_store as ch
    for row in REAL_PRODUCTS + NON_PRODUCTS:
        ch.append(source="extension", url=row["url"], title=row["title"],
                  image=row.get("image_url", ""), price=row.get("price", ""),
                  currency=row.get("currency", ""),
                  extra=json.loads(row.get("extra_json") or "{}"), seller_id="u1")
    r = client.get("/seller/collect/history?hygiene=cleanup&days=3650")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "정리 후보" in body and "삭제가 아니라 보관" in body
    # 후보(비상품) 제목은 뜨고, 실상품 제목(Temu 스피커)은 안 뜬다.
    assert "받은편지함" in body or "ChatGPT" in body
    assert "큐브 매직큐브 RGB" not in body


def test_archived_candidate_drops_from_cleanup(client, monkeypatch):
    """보관(archive)한 후보는 정리 후보 목록에서 빠진다(정리 완료 취급)."""
    _clear()
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_seller_id", lambda: "u1")
    monkeypatch.setattr(views, "_seller_identities", lambda: {"u1"})
    from src.seller_console import collect_history_store as ch
    ch.append(source="extension", url="https://www.icloud.com/mail/#a", title="iCloud A",
              seller_id="u1", status="ok")
    _id2 = ch.append(source="extension", url="https://www.icloud.com/mail/#b", title="iCloud B",
                     seller_id="u1", status="ok")
    if isinstance(_id2, tuple):
        _id2 = _id2[0]
    ch.update(_id2, seller_ids={"u1"}, status="archived")   # 하나 보관
    r = client.get("/seller/collect/history?hygiene=cleanup&days=3650")
    body = r.get_data(as_text=True)
    assert "iCloud A" in body            # 활성 후보는 보임
    assert "iCloud B" not in body        # 보관한 후보는 정리 후보에서 빠짐


# ── UI 계약 ──────────────────────────────────────────────
def test_template_ui_contract():
    tpl = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    rows = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert "hygiene=cleanup" in tpl and "정리 후보" in tpl
    assert "runBulkArchiveCandidates" in tpl              # 선택 보관(삭제 아님)
    assert "bulkDeleteAck" in tpl                         # 영구 삭제 2단 확인 체크
    assert "비상품 의심" in rows and "hygiene" in rows      # 후보 배지
