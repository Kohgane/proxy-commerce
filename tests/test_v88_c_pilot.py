"""tests/test_v88_c_pilot.py — v88-C 파일럿 배선: 모집단 396 결정성 · 50 선정 · 하드 정지 · 검수표 · admin 트리거.

라이브 실행 없음(트리거까지만). 순수 로직·라우트 접근/게이트 검증. 난수 금지(재현성).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.pipeline import coupang_replicate as CR


# ── 합성 sourcing_map (결정성·대표선정 검증) ─────────────────────────────────────
def _sm():
    return {
        # sid=100: 두 ASIN 그룹 → 대표 1 (krw+usd 보유 우선)
        "AAA00000A1": {"name_ko": "가", "krw": 1000, "sources": [{"url": "https://x/a", "priority": 1}], "coupang_sid": 100},
        "BBB00000B1": {"name_ko": "나", "krw": 2000, "usd": 2, "sources": [{"url": "https://x/b", "ship_usd": 0, "priority": 1}], "coupang_sid": 100},
        # sid=50: 단일
        "CCC00000C1": {"name_ko": "다", "krw": 3000, "sources": [{"url": "https://s.myshopify.com/products/c", "priority": 1}], "coupang_sid": 50},
        # coupang_sid 없음 → 모집단 제외
        "DDD00000D1": {"name_ko": "라", "krw": 4000, "sources": [{"url": "https://x/d"}]},
    }


def test_population_636_to_396_shape_and_determinism():
    r1 = CR.build_pilot_population(_sm())
    r2 = CR.build_pilot_population(_sm())
    # coupang_sid truthy 3 → distinct sid 2 (sid=100 중복 1 제거).
    assert r1["reduction"] == {"truthy": 3, "distinct_sid": 2, "dropped_dup": 1}
    assert r1["count"] == 2
    # 결정성: 두 번 돌려 동일 sid 시퀀스(sid 오름차순).
    assert [p["sid"] for p in r1["population"]] == [p["sid"] for p in r2["population"]] == [50, 100]


def test_representative_priority_krw_usd_then_ship_then_asin():
    pop = {p["sid"]: p for p in CR.build_pilot_population(_sm())["population"]}
    # sid=100 대표 = BBB(krw+usd 보유) — AAA(krw만)보다 우선.
    assert pop[100]["asin"] == "BBB00000B1"
    assert "krw+usd" in pop[100]["reason"]


def test_select_pilot_deterministic_and_count():
    pop = [{"sid": i, "asin": f"A{i}"} for i in range(200)]
    a = CR.select_pilot(pop, n=50)
    b = CR.select_pilot(list(reversed(pop)), n=50)   # 입력 순서 무관(내부 sid 정렬)
    assert len(a) == 50 and [x["sid"] for x in a] == [x["sid"] for x in b]   # 재현성
    assert [x["sid"] for x in a] == sorted(x["sid"] for x in a)              # sid 오름차순 stride
    # 모집단 <= n 이면 전량.
    assert len(CR.select_pilot(pop[:30], n=50)) == 30


def test_register_gate_approved_and_guard_passes():
    # 오너 최종 승인("전부가라") → 해제. 안전은 카나리 게이트(register_pilot_rows batch_ok)로 이관.
    assert CR.PILOT_REGISTER_APPROVED is True
    CR.pilot_register_guard()          # 승인됐으므로 raise 안 함


class _FakeUploadResult:
    def __init__(self, ok, url=None, message=None):
        self.market = "woocommerce"; self.success = ok; self.external_url = url; self.message = message


class _FakeDispatch:
    def __init__(self, ok=True): self.ok = ok; self.calls = []
    def __call__(self, product_data, markets):
        self.calls.append(product_data)
        class _DR:
            results = [_FakeUploadResult(self.ok, url="https://shop/p/%s" % product_data.get("title_ko"),
                                         message=None if self.ok else "WC 인증 실패")]
        return _DR()


def _rows(n=3):
    return [{"sid": 100 + i, "asin": "A%d" % i, "title_ko": "상품%d" % i, "sale_krw": 10000 + i,
             "excluded": False} for i in range(n)]


def test_register_canary_registers_only_first_without_batch_ok():
    disp = _FakeDispatch(ok=True)
    out = CR.register_pilot_rows(_rows(3), dispatch_fn=disp, sleep_fn=lambda s: None)
    assert out["mode"] == "canary" and out["target"] == 1 and out["registered"] == 1
    assert len(disp.calls) == 1                     # 첫 1건(Ystudio)만 — 46건 금지
    assert disp.calls[0]["status"] == "draft"       # draft 등록
    assert out["results"][0]["url"].startswith("https://shop/p/")


def test_register_batch_ok_registers_all_and_reports_per_row():
    disp = _FakeDispatch(ok=True)
    out = CR.register_pilot_rows(_rows(3), dispatch_fn=disp, n=47, batch_ok=True, sleep_fn=lambda s: None)
    assert out["mode"] == "batch" and out["target"] == 3 and out["registered"] == 3
    assert all(r["registered"] and r["status"] == "draft" for r in out["results"])


def test_register_partial_failure_no_rollback_and_honest_reason():
    # 첫 성공·둘째 실패 → 성공분 유지(롤백 금지), 실패분 사유 표기(조용한 실패 금지).
    class _Mixed(_FakeDispatch):
        def __call__(self, product_data, markets):
            ok = product_data["title_ko"] != "상품1"
            class _DR:
                results = [_FakeUploadResult(ok, url=("u" if ok else None), message=(None if ok else "가격 0"))]
            return _DR()
    out = CR.register_pilot_rows(_rows(3), dispatch_fn=_Mixed(), n=3, batch_ok=True, sleep_fn=lambda s: None)
    assert out["registered"] == 2 and out["failed"] == 1
    fail = [r for r in out["results"] if not r["registered"]][0]
    assert fail["reason"] and fail["url"] is None      # 사유 존재·롤백 안 함(성공 2건 유지)


def test_sourcing_map_resolves_source_url_not_none(tmp_path):
    # 등록 사후 근원 수리: 엔트리에 top-level url 없고 sources[].url만 있어도 해석(이미지 0장 근원).
    p = tmp_path / "sm.json"
    p.write_text(json.dumps({"B0AAA": {"name_ko": "가", "krw": 1000,
                 "sources": [{"url": "https://amz/dp/B0AAA", "priority": 2},
                             {"url": "https://amz/dp/BEST", "priority": 1}], "coupang_sid": 7}}), encoding="utf-8")
    m = CR.load_sourcing_map(str(p))["map"]
    assert m["B0AAA"] == "https://amz/dp/BEST"       # 우선순위 1 소스
    assert CR._best_source_url({"sources": []}) == "" and CR._best_source_url({"url": "u"}) == "u"


def test_register_silent_failure_guard_and_stock():
    # 이미지 0장인데 등록 성공 → warning(백필 필요) 표기(조용한 성공 금지) + no_image 집계.
    disp = _FakeDispatch(ok=True)
    out = CR.register_pilot_rows(_rows(1), dispatch_fn=disp, sleep_fn=lambda s: None)  # enrich 없음 → 이미지 0
    assert out["no_image"] == 1
    assert out["results"][0]["registered"] is True and out["results"][0]["warning"] == "이미지 0장 — 백필 필요"
    # 재고: 무재고 모델 — manage_stock off + instock.
    assert disp.calls[0]["manage_stock"] is False and disp.calls[0]["stock_status"] == "instock"


def test_backfill_images_matches_by_meta_idempotent_and_honest():
    rows = [{"sid": 10, "asin": "A", "excluded": False}, {"sid": 11, "asin": "B", "excluded": False},
            {"sid": 12, "asin": "C", "excluded": False}]
    products = [
        {"id": 101, "meta_data": [{"key": "_kgp_pilot_sid", "value": "10"}], "images": []},          # 매칭·백필
        {"id": 102, "meta_data": [{"key": "_kgp_pilot_sid", "value": "11"}], "images": [{"src": "x"}]},  # 이미 이미지 → 스킵
        # sid 12 → WC에 없음(unmatched)
    ]
    updated = {}
    def _upd(pid, patch): updated[pid] = patch; return True
    def _enrich(r):
        return {"images": ["https://i/1.jpg", "https://i/2.jpg", "https://i/3.jpg"]} if r["sid"] == 10 else {"images": []}
    out = CR.backfill_images(rows, enrich_fn=_enrich, list_products_fn=lambda: products, update_fn=_upd,
                             image_cap=2, stock_patch={"manage_stock": False, "stock_status": "instock"},
                             sleep_fn=lambda s: None)
    assert out["updated"] == 1 and out["skipped"] == 1 and out["unmatched"] == 1
    assert len(updated[101]["images"]) == 2                 # 2장 캡
    assert updated[101]["manage_stock"] is False and updated[101]["stock_status"] == "instock"  # 재고 동승


def test_prepare_product_data_stock_and_status_override():
    from src.vendors import woocommerce_client as wc
    prod = wc.prepare_product_data(
        {"title_ko": "테스트", "status": "draft", "manage_stock": False, "stock_status": "instock",
         "product_type": "simple", "extra_meta": [{"key": "_kgp_pilot_sid", "value": "9"}]}, 10000)
    assert prod["status"] == "draft" and prod["manage_stock"] is False and prod["stock_status"] == "instock"
    assert prod["type"] == "simple"                         # 자사 결제형(external 아님)
    assert "stock_quantity" not in prod                     # 관리 off면 수량 제거
    assert any(m["key"] == "_kgp_pilot_sid" for m in prod["meta_data"])


def test_register_sets_product_type_simple():
    disp = _FakeDispatch(ok=True)
    CR.register_pilot_rows(_rows(1), dispatch_fn=disp, sleep_fn=lambda s: None)
    assert disp.calls[0]["product_type"] == "simple"        # external 아님


# ── 자동 마감(크론 피기백) — 백필→publish 청크·멱등·no_image draft 잔류 ───────────
class _FakeWC:
    """WC 상태 저장소 대역 — draft/publish 목록 + update_product(patch 병합·상태 전이)."""
    def __init__(self, products):
        self.products = {p["id"]: p for p in products}
        self.updates = []

    def list_products_by_status(self, status="draft"):
        return [dict(p) for p in self.products.values() if p.get("status", "draft") == status]

    def update_product(self, pid, patch):
        self.updates.append((pid, patch))
        p = self.products[pid]
        if "images" in patch:
            p["images"] = patch["images"]
        if "status" in patch:
            p["status"] = patch["status"]
        if "type" in patch:
            p["type"] = patch["type"]
        for m in (patch.get("meta_data") or []):
            p.setdefault("meta_data", []).append(m)
        return True


def _pilot_products(sids):
    return [{"id": 100 + s, "status": "draft", "images": [],
             "meta_data": [{"key": "_kgp_pilot_sid", "value": str(s)}]} for s in sids]


def test_pilot_finish_tick_backfills_chunk_then_publishes_when_done():
    rows = [{"sid": s, "asin": f"A{s}", "excluded": False} for s in (1, 2)]
    wc = _FakeWC(_pilot_products([1, 2]))
    enrich = lambda r: {"images": ["https://i/%s-1.jpg" % r["sid"], "https://i/%s-2.jpg" % r["sid"], "x3"]}
    # 틱1: chunk=1 → sid1만 백필. 아직 pending 남음 → publish 없음.
    t1 = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                              update_fn=wc.update_product, enrich_fn=enrich, chunk=1,
                              image_cap=2, sleep_fn=lambda s: None)
    assert t1["backfilled"] == 1 and t1["remaining_pending"] == 1 and t1["published_this_tick"] == 0
    assert t1["done"] is False
    # 백필 시 2장 캡 + type=simple.
    first = [u for u in wc.updates if "images" in u[1]][0]
    assert len(first[1]["images"]) == 2 and first[1]["type"] == "simple"
    # 틱2: chunk=5 → sid2 백필 + remaining 0 → 이미지 있는 draft 전부 publish.
    t2 = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                              update_fn=wc.update_product, enrich_fn=enrich, chunk=5,
                              image_cap=2, sleep_fn=lambda s: None)
    assert t2["backfilled"] == 1 and t2["remaining_pending"] == 0 and t2["done"] is True
    assert t2["published_this_tick"] == 2
    assert all(p["status"] == "publish" for p in wc.products.values())


def test_pilot_finish_tick_no_image_stays_draft_and_flagged():
    rows = [{"sid": 1, "asin": "A1", "excluded": False}]
    wc = _FakeWC(_pilot_products([1]))
    enrich = lambda r: {"images": []}                       # 수집 이미지 0장
    out = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                               update_fn=wc.update_product, enrich_fn=enrich, chunk=5,
                               image_cap=2, sleep_fn=lambda s: None)
    assert out["no_image"] == 1 and out["backfilled"] == 0
    # 이미지 0 → publish 금지(안 팔릴 상품 공개 방지), draft 잔류 + no_image 플래그.
    assert wc.products[101]["status"] == "draft"
    assert CR._pilot_has_flag(wc.products[101], CR._NO_IMAGE_META)
    # 다음 틱: 플래그된 행은 재시도 대상에서 제외(pending 0).
    out2 = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                                update_fn=wc.update_product, enrich_fn=enrich, chunk=5,
                                sleep_fn=lambda s: None)
    assert out2["pending_before"] == 0 and out2["published_this_tick"] == 0


def test_pilot_finish_tick_collect_failure_is_honest_not_silent():
    rows = [{"sid": 1, "asin": "A1", "excluded": False}]
    wc = _FakeWC(_pilot_products([1]))
    def _boom(r):
        raise RuntimeError("수집 타임아웃")
    out = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                               update_fn=wc.update_product, enrich_fn=_boom, chunk=5,
                               sleep_fn=lambda s: None)
    assert out["failed"] == 1 and out["backfilled"] == 0
    r = out["results"][0]
    assert r["action"] == "collect_fail" and "수집 실패" in r["reason"]   # 조용한 실패 금지
    assert wc.products[101]["status"] == "draft"            # 실패 → 여전히 draft
    assert out["stuck"] and out["stuck"][0]["sid"] == 1     # 멈춘 행이 사유와 함께 노출


def test_pilot_finish_tick_flag_write_failure_not_silent_stall():
    # 0장 종결 플래그 쓰기가 실패(falsy 반환)하면 조용히 no_image로 묻지 않고 flag_fail 사유 노출 +
    # 플래그 미기록이라 다음 틱에도 pending(무한 정체 아님, 정직).  ← pending 32 정체 근원 수리.
    rows = [{"sid": 1, "asin": "A1", "excluded": False}]
    class _FlagFailWC(_FakeWC):
        def update_product(self, pid, patch):
            if any(m.get("key") == "_kgp_no_image" for m in (patch.get("meta_data") or [])):
                return False                        # WC가 플래그 PUT을 반영 안 함(falsy)
            return super().update_product(pid, patch)
    wc = _FlagFailWC(_pilot_products([1]))
    enrich = lambda r: {"images": [], "account": "gogane", "source": "none", "reason": "쿠팡 404·소싱 0"}
    out = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                               update_fn=wc.update_product, enrich_fn=enrich, chunk=5, sleep_fn=lambda s: None)
    assert out["no_image"] == 0 and out["failed"] == 1
    r = out["results"][0]
    assert r["action"] == "flag_fail" and "플래그 쓰기 실패" in r["reason"]
    assert not CR._pilot_has_flag(wc.products[101], CR._NO_IMAGE_META)   # 종결 안 됨
    # 다음 틱: 여전히 pending(정체가 드러남 — 조용히 사라지지 않음).
    out2 = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                                update_fn=wc.update_product, enrich_fn=enrich, chunk=5, sleep_fn=lambda s: None)
    assert out2["pending_before"] == 1


def test_pilot_finish_tick_survives_wc_list_failure():
    # WC 목록 조회 실패 시 틱 전체가 조용히 죽지 않고 error 사유 반환.
    def _boom_list(status="draft"):
        raise RuntimeError("WC 502")
    out = CR.pilot_finish_tick([{"sid": 1, "asin": "A", "excluded": False}],
                               list_products_fn=_boom_list, update_fn=lambda *a: True,
                               enrich_fn=lambda r: {"images": []}, sleep_fn=lambda s: None)
    assert out["done"] is False and "draft 목록 조회 실패" in out["error"]


def test_pilot_accounting_excludes_hold_brand_bosmere():
    # 회계 정정: 보스미어(오탐·미등록)는 target/pending/unmatched에서 제외 + held로 별도 보고.
    rows = [
        {"sid": 1, "asin": "A1", "title_ko": "원목 식탁", "excluded": False},          # 정상
        {"sid": 2, "asin": "B0046A80ZC", "title_ko": "보스미어 Bosmere Yard Waste Tarp", "excluded": False},  # 보류
    ]
    products = [{"id": 101, "status": "publish", "images": [{"src": "x"}], "permalink": "https://s/p/1",
                 "meta_data": [{"key": "_kgp_pilot_sid", "value": "1"}]}]
    wc = _FakeWC(products)
    st = CR.pilot_status(rows, list_products_fn=wc.list_products_by_status)
    assert st["target"] == 1 and st["published"] == 1 and st["unmatched"] == 0   # 보스미어 회계 제외
    assert st["held"] == 1 and st["held_rows"][0]["asin"] == "B0046A80ZC"
    assert st["done"] is True
    # finish_tick도 보스미어를 pending으로 잡지 않음.
    wc2 = _FakeWC(_pilot_products([2]))
    out = CR.pilot_finish_tick(rows, list_products_fn=wc2.list_products_by_status,
                               update_fn=wc2.update_product, enrich_fn=lambda r: {"images": ["u"]},
                               chunk=5, sleep_fn=lambda s: None)
    assert out["pending_before"] == 0            # 보스미어는 pending 대상 아님


def test_pilot_status_buckets_mutually_exclusive():
    rows = [{"sid": s, "asin": f"A{s}", "title_ko": f"상품{s}", "excluded": False} for s in (1, 2, 3, 4)]
    products = [
        {"id": 101, "status": "publish", "images": [{"src": "x"}], "permalink": "https://shop/p/1",
         "meta_data": [{"key": "_kgp_pilot_sid", "value": "1"}]},         # published
        {"id": 102, "status": "draft", "images": [{"src": "y"}],
         "meta_data": [{"key": "_kgp_pilot_sid", "value": "2"}]},         # with_images (다음 완료틱 publish)
        {"id": 103, "status": "draft", "images": [],
         "meta_data": [{"key": "_kgp_pilot_sid", "value": "3"},
                       {"key": "_kgp_no_image", "value": "coupang"}]},    # no_image 종결(쿠팡까지 시도)·draft 잔류
        # sid 4 → WC에 없음(unmatched · 아직 미등록)
    ]
    wc = _FakeWC(products)
    st = CR.pilot_status(rows, list_products_fn=wc.list_products_by_status)
    assert (st["target"], st["published"], st["with_images_draft"], st["no_image_draft"],
            st["pending"], st["unmatched"], st["done"]) == (4, 1, 1, 1, 0, 1, True)
    # 미매칭 행을 sid·asin·이름으로 식별(추정 금지) + 게시물 URL 샘플.
    assert st["unmatched_rows"] == [{"sid": "4", "asin": "A4", "name": "상품4"}]
    assert st["published_samples"] == [{"sid": "1", "url": "https://shop/p/1"}]
    # 이미지 0·플래그 없는 draft는 pending(다음 백필 대상) — done False.
    products.append({"id": 105, "status": "draft", "images": [],
                     "meta_data": [{"key": "_kgp_pilot_sid", "value": "4"}]})
    wc2 = _FakeWC(products)
    st2 = CR.pilot_status(rows, list_products_fn=wc2.list_products_by_status)
    assert st2["pending"] == 1 and st2["unmatched"] == 0 and st2["done"] is False


# ── 이미지 소스 피벗: 쿠팡 seller-products 원본 우선 (v88-C) ───────────────────────
class _Resp:
    def __init__(self, status, body=None): self.status_code = status; self._b = body or {}
    def json(self): return self._b


def _cp_body(*urls):
    return {"data": {"items": [{"images": [{"imageOrder": i, "vendorPath": u} for i, u in enumerate(urls)]}]}}


def test_coupang_image_urls_extract_and_cdn_base(monkeypatch):
    monkeypatch.delenv("COUPANG_IMAGE_CDN_BASE", raising=False)
    data = {"items": [{"images": [{"cdnPath": "a/b/c.jpg"}, {"vendorPath": "https://x.com/d.png"},
                                  {"cdnPath": "/e/f.webp"}, {"note": "not-an-image"}]}]}
    urls = CR._coupang_image_urls(data)
    assert urls == ["https://image.coupangcdn.com/a/b/c.jpg", "https://x.com/d.png",
                    "https://image.coupangcdn.com/e/f.webp"]


def test_account_creds_prefix_and_base_fallback(monkeypatch):
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("COUPANG_GOGANE_ACCESS_KEY", "gak")
    monkeypatch.setenv("COUPANG_GOGANE_SECRET_KEY", "gsk")
    monkeypatch.setenv("COUPANG_GOGANE_VENDOR_ID", "A01381223")
    # 우주대행은 무접두 base(COUPANG_*)로 흡수(VENDOR_ID 일치).
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "bak")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "bsk")
    monkeypatch.setenv("COUPANG_VENDOR_ID", "A01504840")
    assert CR._account_creds("gogane") == ("gak", "gsk", "A01381223")
    assert CR._account_creds("woojoo") == ("bak", "bsk", "A01504840")   # base 폴백
    assert set(CR.ready_accounts()) == {"gogane", "woojoo"}


def test_fetch_coupang_images_account_routing_hint_and_order(monkeypatch):
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    for a, vid in (("GOGANE", "A01381223"), ("WOOJOO", "A01504840")):
        monkeypatch.setenv(f"COUPANG_{a}_ACCESS_KEY", f"{a}ak")
        monkeypatch.setenv(f"COUPANG_{a}_SECRET_KEY", f"{a}sk")
        monkeypatch.setenv(f"COUPANG_{a}_VENDOR_ID", vid)
    calls = []
    def _req(method, url, *, headers=None, market="", key=""):
        calls.append({"url": url, "key": key, "auth": headers["Authorization"]})
        # 고가네(A01381223) 소유 아님(404), 우주대행(A01504840) 소유(200).
        return _Resp(404) if key == "A01381223" else _Resp(200, _cp_body("https://c/1.jpg", "https://c/2.jpg"))
    now = __import__("datetime").datetime(2026, 8, 21, 0, 0, 0)
    # 힌트 없음 → ready 순차(고가네→우주대행), 404면 다음 계정.
    out = CR.fetch_coupang_images(555, request_fn=_req, now_fn=lambda: now)
    assert out["ok"] and out["account"] == "woojoo" and len(out["images"]) == 2
    assert [c["key"] for c in calls] == ["A01381223", "A01504840"]      # 순차·혼동 없음
    assert "access-key=WOOJOOak" in calls[-1]["auth"]                    # 맞는 키로 서명
    # 힌트 있으면 그 계정만 호출(재판별 0).
    calls.clear()
    out2 = CR.fetch_coupang_images(555, account_hint="woojoo", request_fn=_req, now_fn=lambda: now)
    assert out2["account"] == "woojoo" and [c["key"] for c in calls] == ["A01504840"]


def test_fetch_coupang_images_no_creds_and_zero_honest(monkeypatch):
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    out = CR.fetch_coupang_images(1, request_fn=lambda *a, **k: _Resp(200), now_fn=lambda: __import__("datetime").datetime(2026, 8, 21))
    assert out["ok"] is False and out["images"] == [] and "자격 없음" in out["reason"]


def test_coupang_first_enrich_prefers_coupang_then_sourcing():
    # 쿠팡 이미지 있으면 소싱 미호출(source=coupang).
    def _fetch_ok(sid, *, account_hint=None, request_fn=None):
        return {"ok": True, "images": ["https://c/a.jpg", "https://c/b.jpg", "https://c/c.jpg"], "account": "gogane"}
    called = {"n": 0}
    def _collect(url): called["n"] += 1; return {"images": ["https://s/x.jpg"]}
    en = CR.make_coupang_first_enrich_fn(_collect, image_cap=2, fetch_images_fn=_fetch_ok)
    r = en({"sid": 7, "asin": "A"})
    assert r["source"] == "coupang" and len(r["images"]) == 2 and r["account"] == "gogane"
    assert called["n"] == 0                              # 쿠팡 성공 → 소싱 폴백 안 함
    # 쿠팡 0장 → 소싱 폴백.
    def _fetch_zero(sid, *, account_hint=None, request_fn=None):
        return {"ok": False, "images": [], "account": None, "reason": "200·이미지 0"}
    en2 = CR.make_coupang_first_enrich_fn(_collect, image_cap=2, fetch_images_fn=_fetch_zero)
    # 소싱맵에 asin이 없으면 폴백도 0 → source=none + 사유.
    r2 = en2({"sid": 7, "asin": "NOPE_NOT_IN_MAP"})
    assert r2["source"] == "none" and r2["images"] == [] and "쿠팡" in r2["reason"]


def test_pilot_finish_tick_retries_old_gen_flag_and_caches_account():
    # 구세대 no_image 플래그("1")는 쿠팡 소스로 재시도 대상(오너 지시 3). 판별 계정 캐시.
    rows = [{"sid": 1, "asin": "A1", "excluded": False}]
    products = [{"id": 101, "status": "draft", "images": [],
                 "meta_data": [{"key": "_kgp_pilot_sid", "value": "1"},
                               {"key": "_kgp_no_image", "value": "1"}]}]  # 구세대 플래그
    wc = _FakeWC(products)
    def _enrich(row):
        assert row.get("coupang_account") is None       # 아직 캐시 없음
        return {"images": ["https://c/1.jpg", "https://c/2.jpg"], "account": "woojoo", "source": "coupang"}
    out = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                               update_fn=wc.update_product, enrich_fn=_enrich, chunk=5,
                               image_cap=2, sleep_fn=lambda s: None)
    assert out["backfilled"] == 1 and out["pending_before"] == 1        # "1" 플래그도 재시도됨
    p = wc.products[101]
    assert CR._pilot_img_count(p) == 2
    assert CR._pilot_account_hint(p) == "woojoo"                        # 판별 계정 캐시됨


def test_pilot_finish_tick_coupang_gen_flag_is_terminal():
    # 쿠팡·소싱 둘 다 0 → "coupang" 세대 플래그로 종결(다음 틱 재시도 제외).
    rows = [{"sid": 1, "asin": "A1", "excluded": False}]
    wc = _FakeWC(_pilot_products([1]))
    def _enrich(row):
        return {"images": [], "account": "gogane", "source": "none", "reason": "쿠팡 200·이미지 0 · 소싱 폴백도 0"}
    out = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                               update_fn=wc.update_product, enrich_fn=_enrich, chunk=5,
                               sleep_fn=lambda s: None)
    assert out["no_image"] == 1
    assert CR._pilot_flag_value(wc.products[101], "_kgp_no_image") == "coupang"   # 현 세대 종결
    # 다음 틱: "coupang" 플래그는 재시도 제외.
    out2 = CR.pilot_finish_tick(rows, list_products_fn=wc.list_products_by_status,
                                update_fn=wc.update_product, enrich_fn=_enrich, chunk=5,
                                sleep_fn=lambda s: None)
    assert out2["pending_before"] == 0


def test_register_flags_suspect_cjk_into_meta():
    disp = _FakeDispatch(ok=True)
    row = {"sid": 9, "asin": "Z", "title_ko": "세일러 万年筆", "sale_krw": 5000, "excluded": False,
           "title_truncated_suspect": True, "title_cjk_residual": True}
    CR.register_pilot_rows([row], dispatch_fn=disp, sleep_fn=lambda s: None)
    keys = {m["key"] for m in disp.calls[0]["pilot_meta"]}
    assert "_kgp_title_suspect" in keys and "_kgp_cjk_residual" in keys and "_kgp_pilot_sid" in keys


def test_review_row_blacklist_and_price_and_no_register():
    # 금지 카테고리 → excluded + 사유(조용한 탈락 금지).
    bad = CR.build_review_row({"sid": 1, "asin": "X", "name_ko": "샤넬 향수", "krw": 10000},
                              channel="woocommerce_multishop")
    assert bad["excluded"] is True and bad["forbidden"].startswith("forbidden-category")
    assert bad["registered"] is False
    # 정상 → 원가기준 가격(멀티샵 3%·마진 27.4%) 14,400.
    ok = CR.build_review_row({"sid": 2, "asin": "Y", "name_ko": "원목 식탁", "krw": 10000},
                             channel="woocommerce_multishop")
    assert ok["excluded"] is False and ok["sale_krw"] == 14400 and ok["registered"] is False
    # 주입 blacklist85 반영.
    inj = CR.build_review_row({"sid": 3, "asin": "Z", "name_ko": "특정금지품 XYZ", "krw": 5000},
                              channel="woocommerce_multishop", blacklist=["특정금지품"])
    assert inj["excluded"] is True and inj["forbidden"].startswith("blacklist")


# ── admin 트리거 라우트 (오너 세션 인증 · 등록 하드 정지) ─────────────────────────
def _admin_client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner"
        s["user_role"] = "admin"       # is_admin_session True
    return c


def test_pilot_route_requires_admin(monkeypatch):
    from src.order_webhook import app
    c = app.test_client()
    r = c.post("/admin/coupang-pilot")   # 세션 없음 → 로그인 리다이렉트(비-200)
    assert r.status_code in (301, 302, 403)


def test_pilot_route_returns_population_selection_and_gate(monkeypatch):
    c = _admin_client(monkeypatch)
    monkeypatch.delenv("COUPANG_BLACKLIST85", raising=False)
    # blacklist 미설정 → 가드가 400 → 전체 경로 검증 위해 명시적 우회.
    r = c.post("/admin/coupang-pilot?n=50&allow_no_blacklist=1")
    assert r.status_code == 200, r.status_code
    d = r.get_json()
    assert d["ok"] is True
    assert d["registered"] is False and "PILOT_REGISTER_APPROVED=True" in d["register_gate"]
    # 레포에 data/pilot_population.json(396) 존재 → 그 모집단 사용.
    if Path("data/pilot_population.json").is_file():
        assert d["population_count"] == 396 and d["selected"] == 50
    # 제외 테이블 키 존재(조용한 탈락 금지).
    assert "excluded_table" in d and "review_table" in d
    # 라이브 미충족(샌드박스) → 현행가 아님 표기.
    assert "현행가 아님" in d["price_basis"] or d["live"] is True


def test_pilot_route_blacklist_guard_blocks_on_zero(monkeypatch):
    # 조용한 실패 금지: blacklist 0건이면 표 산출 중단·400(빈 필터 전량 통과 금지).
    c = _admin_client(monkeypatch)
    monkeypatch.delenv("COUPANG_BLACKLIST85", raising=False)
    r = c.post("/admin/coupang-pilot?n=10")   # 우회 없음
    assert r.status_code == 400, r.status_code
    d = r.get_json()
    assert d["ok"] is False and d["blacklist85_loaded"] == 0
    assert "review_table" not in d           # 표를 만들지 않았다
    assert "COUPANG_BLACKLIST85" in d["how_to_load"]


def test_build_pilot_report_live_price_flips_basis_and_recalcs():
    # 계약(task 3): relay 주입 + price_fn(현행가) → price_basis="coupang live" + 마진 재계산.
    pop = [{"sid": 7, "asin": "A7", "name_ko": "원목 선반", "krw": 10000, "source": "amazon"}]
    access = {"ready": True, "missing": [], "relay_mode": "mkt.php(MARKET_API_RELAY_URL)",
              "coupang_accounts": {"우주대행": True}}
    relay = {"ready": True, "mode": "mkt.php(MARKET_API_RELAY_URL)"}
    # 현행가 재조회 stub: sourcing krw(10000)와 다른 현행가(20000) → 재계산 결과가 달라야 한다.
    live = CR.build_pilot_report(pop, n=1, access=access, relay=relay,
                                 price_fn=lambda sid: 20000, blacklist=["__none__"])
    assert live["live"] is True and live["live_price_used"] is True
    assert live["price_basis"].startswith("coupang live")
    sale_live = live["review_table"][0]["sale_krw"]
    # price_fn 없으면 sourcing krw 기준 → 다른 판매가 + basis 표기 달라짐.
    off = CR.build_pilot_report(pop, n=1, access=access, relay=relay,
                                price_fn=None, blacklist=["__none__"])
    assert off["live_price_used"] is False and "현행가 아님" in off["price_basis"]
    assert sale_live != off["review_table"][0]["sale_krw"], "현행가 재조회가 마진 재계산에 반영 안 됨"
