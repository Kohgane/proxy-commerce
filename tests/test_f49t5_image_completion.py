"""F49-T 5부 — 타오바오 전체 수집 시 이미지 1장만(오너 실측).

원인(코드로 확인한 두 겹 — 실데이터 분류는 `/seller/collect/image-audit`로 오너 계정에서 잰다):
  ① 목록 타일 수집 뒤 상세 보강은 확장 워커 **메모리 큐**로만 돌았다. 30장이면 10분을 넘겨 MV3 워커가
     내려가면 남은 항목은 그대로 썸네일 1장.
  ② 서버는 그 항목을 다시 집지 못했다 — `enrich_axes`가 「대기 + 이미지 ≥ 1」을 **완료**로 읽었고, 목록 타일은
     썸네일 1장을 이미 갖고 온다. 대기열(`/enrich/pending`)에서 영영 빠졌다.

이 파일이 못박는 것:
  ① 중국 소싱처 목록 타일 = 「초안 + 상세 보강 대기」, 썸네일 1장이어도 대기열에 남는다(다른 소싱처는 그대로)
  ② 보강 완료 기준 = 갤러리 ≥ 원본 갤러리 수(ICE) · 상세 이미지 ≥ 1 — 미달이면 「이미지 부족」 + 사유(목록·드로어)
  ③ 원인 실측 라우트 — A 목록 카드만 · B 막힘 · C 보강했는데 1장 · D 정상
  ④ 확장: 간격 2~3초 · 실패 항목과 사유 · 툴바 「보강 실패 N건 다시」 · 보강 본문에 원본 갤러리 수
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
TB = "https://item.taobao.com/item.htm?id=617129397971"
DIAG = Path("fixtures/realpages/diag/kgp-diagnostic-detail-tmall-com-item-htm-id-617129397971.html")


def _client(monkeypatch, seller):
    import src.api.extension_api as ext
    from src.order_webhook import app
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def _tile(c, url=TB, n=1):
    body = {"url": url, "title": "随行盾 手表架", "price": "29.9", "currency": "CNY", "mode": "simple",
            "images": [f"https://img.alicdn.com/list{i}.jpg" for i in range(n)], "translate": False}
    d = c.post("/api/v1/collect/extension", json=body).get_json()
    assert d["ok"], d
    return d["item_id"]


def _extra(iid, seller):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_id=seller)["extra_json"])


def _ice():
    t = DIAG.read_text(encoding="utf-8")
    e = json.loads(re.search(r'<script type="application/json" id="kgp-diagnostic">(.*?)</script>', t, re.S).group(1))["extracted"]
    return e


# ① 목록 타일 = 초안 + 보강 대기
def test_cn_list_tile_stays_pending_with_one_thumbnail(monkeypatch):
    from src.collectors.collect_status import enrich_axes
    seller = "u-5-pending"
    c = _client(monkeypatch, seller)
    iid = _tile(c)
    ex = _extra(iid, seller)
    assert ex["mode"] == "simple" and ex["enrich_state"] == "pending"
    assert enrich_axes(ex)["enrich_state"] == "pending"                 # 썸네일 1장 ≠ 보강 완료
    pend = c.get("/api/v1/collect/enrich/pending").get_json()
    assert any(p["item_id"] == iid for p in pend["items"])


def test_other_sources_are_unchanged(monkeypatch):
    seller = "u-5-amazon"
    c = _client(monkeypatch, seller)
    iid = _tile(c, url="https://www.amazon.com/dp/B0TEST5555")
    assert "enrich_state" not in _extra(iid, seller)


# ② 완료 기준
def test_enrich_with_ice_gallery_and_detail_passes(monkeypatch):
    from src.collectors.collect_status import enrich_axes
    seller = "u-5-ok"
    c = _client(monkeypatch, seller)
    iid = _tile(c)
    e = _ice()
    assert len(e["images"]) == 5            # 2026-09-28 재업로드: ICE 갤러리 5장
    r = c.post("/api/v1/collect/enrich", json={
        "item_id": iid, "gallery": e["images"], "detail_images": ["https://img.alicdn.com/d1.jpg"],
        "field_sources": e["field_sources"], "gallery_expected": 5, "price": e["price"], "currency": "CNY"}).get_json()
    assert r["ok"]
    ex = _extra(iid, seller)
    assert ex["image_check"]["ok"] is True and ex["image_check"]["gallery"] >= 5
    assert enrich_axes(ex)["enrich_state"] == "done"


def test_short_images_are_flagged_with_reason_in_list_and_drawer(monkeypatch):
    seller = "u-5-short"
    c = _client(monkeypatch, seller)
    iid = _tile(c)
    c.post("/api/v1/collect/enrich", json={"item_id": iid, "gallery": ["https://img.alicdn.com/g1.jpg"],
                                          "detail_images": [], "gallery_expected": 5,
                                          "field_sources": {"images": "ice_context"}})
    ex = _extra(iid, seller)
    ic = ex["image_check"]
    assert ic["ok"] is False and "갤러리 1/5장" in ic["reason"] and "상세 이미지 0장" in ic["reason"]
    lst = c.get("/seller/collect/history").get_data(as_text=True)
    assert 'data-role="image-short"' in lst and "이미지 부족 · 갤러리 1/5장" in lst
    drawer = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert 'data-role="image-short"' in drawer and "이미지 부족 — 갤러리 1/5장" in drawer


def test_unknown_source_gallery_count_is_not_invented(monkeypatch):
    seller = "u-5-unknown"
    c = _client(monkeypatch, seller)
    iid = _tile(c)
    c.post("/api/v1/collect/enrich", json={"item_id": iid, "gallery": ["https://img.alicdn.com/g1.jpg"],
                                          "detail_images": ["https://img.alicdn.com/d1.jpg"]})
    ic = _extra(iid, seller)["image_check"]
    assert ic["expected_known"] is False and ic["ok"] is True               # 원본 수를 모르면 부족이라 하지 않는다


# ③ 원인 실측 라우트
def test_image_audit_classifies_cases(monkeypatch):
    seller = "u-5-audit"
    c = _client(monkeypatch, seller)
    a = _tile(c, url="https://item.taobao.com/item.htm?id=500000000001")
    b = _tile(c, url="https://item.taobao.com/item.htm?id=500000000002")
    for _ in range(3):
        c.post("/api/v1/collect/enrich/blocked", json={"item_id": b, "reason": "로그인 벽"})
    cc = _tile(c, url="https://item.taobao.com/item.htm?id=500000000003")
    c.post("/api/v1/collect/enrich", json={"item_id": cc, "detail_images": ["https://img.alicdn.com/d.jpg"]})
    d = _tile(c, url="https://item.taobao.com/item.htm?id=500000000004", n=3)
    got = c.get("/seller/collect/image-audit?format=json").get_json()   # 5부-b: 기본은 화면, JSON은 명시
    ids = {k: {x["item_id"] for x in v} for k, v in got["samples"].items()}
    assert a in ids["A"] and b in ids["B"] and cc in ids["C"] and d in ids["D"], got
    assert set(got["summary"]) == {"A", "B", "C", "D"} and got["images_source"]


# ④ 확장
def test_extension_queue_interval_failures_and_retry():
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert "return 2000 + Math.floor(r * 1000);" in bg
    assert "failures: KgpEnrich.failures.slice(-30)" in bg and bg.count("KgpEnrich.failures.push(") == 2
    assert 'gallery_expected: (meta.field_sources && meta.field_sources.images === "ice_context")' in bg
    assert "function kgpRenderEnrichRetry(failures)" in cs and "보강 실패 ${failures.length}건 다시" in cs
    assert "kgpRenderEnrichRetry(s.failures || [])" in cs


def test_world_taobao_sample_five(monkeypatch):
    """실 스냅샷(오너 재업로드 2026-09-28)의 피드 카드 30장 중 5장 — 목록 수집 = 초안 + 상세 보강 대기."""
    hits = sorted(Path("fixtures/realpages/diag").glob("kgp-snapshot-world-taobao-com*.html"))
    assert hits, "world-taobao 스냅샷이 main에 있어야 한다(오너 업로드 52dda872)"
    pytest.importorskip("playwright.sync_api")
    from tests import _pw
    if not _pw.chromium_hits():
        pytest.skip("chromium 없음")
    from tests.test_f49t4_infinite_scroll import _open
    from playwright.sync_api import sync_playwright
    body = hits[0].read_text(encoding="utf-8", errors="ignore")
    with sync_playwright() as pw:
        b, page = _open(pw, "https://world.taobao.com/", body)
        page.wait_for_timeout(1200)
        cards = page.evaluate("() => (_kgpCards || []).map(c => ({url: c.url, title: c.title, image: c.image, price: c.price, currency: c.currency}))")
        b.close()
    assert len(cards) == 30 and all("item.htm?id=" in c["url"] for c in cards)
    seller = "u-5-wt"
    c = _client(monkeypatch, seller)
    picks = [cards[i] for i in (0, 7, 14, 21, 29)]
    ids = []
    for k in picks:
        d = c.post("/api/v1/collect/extension", json={**k, "images": [k["image"]] if k["image"] else [],
                                                      "mode": "simple", "translate": False}).get_json()
        assert d["ok"], d
        ids.append(d["item_id"])
    pend = {p["item_id"] for p in c.get("/api/v1/collect/enrich/pending").get_json()["items"]}
    for iid in ids:
        ex = _extra(iid, seller)
        assert ex["mode"] == "simple" and ex["enrich_state"] == "pending" and iid in pend
