"""오너 11-26 11:58 「셰고가 다시 켜라」 — 판매중지 → 골라서 판매 재개. 계약.

목록은 읽기만(전송 0) · 줄마다 뺄 사유 · 켤 순서(① 팔림 · ② 조회수 API 없음 → 건너뜀 표시 · ③ 주제 · ④ 최신) · 빈자리만큼 ·
실행은 셰고가만 · 두 번 확인(건수 맞아야) · 50건씩 · 멈춤 · 실패는 네이버 원문 · 끝나면 상태별 수 다시 · 가격은 표시만.
"""
from __future__ import annotations

import json

import pytest

M = "https://shop-phinf.pstatic.net/"


class FakeUp:
    """네이버 커머스 API 흉내 — 판매중지 목록·상태별 수·채널 상품·상태 바꾸기."""

    def __init__(self, products, counts, fail=()):
        self.products, self.counts, self.fail, self.calls = products, counts, set(fail), []

    def _api_request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path == "/v1/products/search":
            page, size = data["page"], data["size"]
            chunk = self.products[(page - 1) * size: page * size]
            return {"totalElements": len(self.products), "contents": [
                {"originProductNo": p["origin"], "channelProducts": [{
                    "channelProductNo": p["ch"], "name": p["name"], "salePrice": p.get("price", 30000), "statusType": "SUSPENSION",
                    "regDate": p.get("reg", "2026-10-01T00:00:00"), "modifiedDate": p.get("mod", "2026-11-01T00:00:00"),
                    "representativeImage": {"url": p.get("img", M + p["ch"] + "_big.jpg")}, "stockQuantity": 5,
                    "wholeCategoryName": p.get("cat", "")}]} for p in chunk]}
        if path.startswith("/v2/products/channel-products/"):
            return {"originProduct": {"images": {"optionalImages": []}}}
        if path.endswith("/change-status"):
            no = path.split("/")[-2]
            if no in self.fail:
                return {"error": "HTTP 400 {\"code\":\"InvalidStatus\",\"message\":\"재고 수량이 0입니다\"}"}
            self.counts["SALE"] = self.counts.get("SALE", 0) + 1
            self.counts["SUSPENSION"] = self.counts.get("SUSPENSION", 0) - 1
            return {"ok": True}
        return {"error": "unknown"}

    def count_products(self, statuses):
        return sum(int(self.counts.get(s) or 0) for s in statuses)


def _size(url):
    return {"long_side": 300} if "_small" in str(url) else {"long_side": 1200}


@pytest.fixture
def state(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    return s


_MADE: list = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from src.seller_console import collect_history_store as S
    for sid, iid in _MADE:
        try:
            S.delete([iid], seller_id=sid)
        except Exception:
            pass
    _MADE.clear()


def _ours(ch, *, price="10", currency="USD", url="https://www.amazon.com/dp/B0X", **ex):
    from src.seller_console import collect_history_store as S
    e = {"price": price, "currency": currency, "uploaded": [{"market": "smartstore:chezgoga", "channel_product_no": ch, "product_id": "o" + ch}]}
    e.update(ex)
    iid = S.append(source="share", url=url, title="x", price=price, currency=currency, image="", seller_id="rl1", extra=e)
    _MADE.append(("rl1", iid))
    return iid


def _env(monkeypatch):
    monkeypatch.setenv("MARKET_COMMISSION_PCT_SMARTSTORE", "5.5")
    monkeypatch.setenv("IMPORT_MARGIN_PCT", "25")
    from src.services import smartstore_relist as SR
    monkeypatch.setattr(SR, "_rules", lambda: (["도검", "사시미칼"], ["supreme"]))
    monkeypatch.setattr(SR, "_sales_index", lambda ours: {"9001": {"ss": 3, "cp": 0}, "9002": {"ss": 0, "cp": 2}})
    return SR


def _products():
    return [
        {"ch": "9001", "origin": "o9001", "name": "옛날에 팔린 백팩", "price": 200000, "reg": "2026-01-01"},
        {"ch": "9002", "origin": "o9002", "name": "쿠팡에서 팔린 램프", "price": 200000, "reg": "2026-02-01"},
        {"ch": "9003", "origin": "o9003", "name": "기계식 키보드 텐키리스", "price": 200000, "reg": "2026-03-01"},
        {"ch": "9004", "origin": "o9004", "name": "주방 수납함", "price": 200000, "reg": "2026-09-01"},
        {"ch": "9005", "origin": "o9005", "name": "주방 선반", "price": 200000, "reg": "2026-10-01"},
        {"ch": "9006", "origin": "o9006", "name": "일본 사시미칼 장인", "price": 200000},
        {"ch": "9007", "origin": "o9007", "name": "도수 안경렌즈 1.67", "price": 200000},
        {"ch": "9008", "origin": "o9008", "name": "Supreme 백팩", "price": 200000},
        {"ch": "9009", "origin": "o9009", "name": "Snow Peak 티타늄 머그", "price": 200000},
        {"ch": "9010", "origin": "o9010", "name": "싸게 판 컵", "price": 12000},
        {"ch": "9011", "origin": "o9011", "name": "원가 모름 컵", "price": 200000},
        {"ch": "9012", "origin": "o9012", "name": "우리 기록 없는 상품", "price": 200000},
        {"ch": "9013", "origin": "o9013", "name": "흐린 사진 상품", "price": 200000, "img": M + "9013_small.jpg"},
        {"ch": "9014", "origin": "o9014", "name": "반려됐던 상품", "price": 200000},
        {"ch": "9015", "origin": "o9015", "name": "소싱처 품절 상품", "price": 200000},
    ]


def _seed():
    for ch in ("9001", "9002", "9003", "9004", "9005", "9006", "9007", "9008", "9009", "9010", "9013"):
        _ours(ch)
    _ours("9011", price="")
    _ours("9014", uploaded=[{"market": "smartstore:chezgoga", "channel_product_no": "9014"},
                            {"market": "coupang:gogane", "product_id": "55", "review": {"state": "rejected", "comment": "상표권 침해 신고"}}])
    _ours("9015", monitor={"in_stock": False, "summary": "품절"})


def test_build_reads_only_and_applies_every_rule(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    up = FakeUp(_products(), {"SALE": 400, "WAIT": 1, "OUTOFSTOCK": 2, "SUSPENSION": 15})
    p = SR.build("chezgoga", up=up, size_of=_size)
    assert not [c for c in up.calls if c[0] == "PUT"]                                   # 읽기만
    by = {x["channel_no"]: x for x in p["rows"]}
    assert by["9006"]["exclude"] == ["knife"] and by["9007"]["exclude"] == ["lens"] and by["9008"]["exclude"] == ["brand"]
    assert by["9009"]["action"] == "on"                                                  # 스노우피크 예외
    assert "margin_low" in by["9010"]["exclude"] and "cost_unknown" in by["9011"]["exclude"]
    assert "no_source" in by["9012"]["exclude"] and by["9012"]["our_reason"] == "기록 없음"
    assert "photos_small" in by["9013"]["exclude"]
    assert "ours_reject" in by["9014"]["exclude"] and "상표권" in by["9014"]["exclude_detail"][0]
    assert "src_soldout" in by["9015"]["exclude"]
    assert p["room"] == 597 and p["status_counts"]["SUSPENSION"] == 15 and "조회수" in p["views_note"]


def test_order_sold_first_then_theme_then_newest(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    p = SR.build("chezgoga", up=FakeUp(_products(), {"SALE": 400}), size_of=_size)
    on = [x["channel_no"] for x in p["rows"] if x["action"] == "on"]
    assert on[:2] == ["9001", "9002"]                                                    # ① 스스 3 > 쿠팡 2
    assert on[2] == "9003"                                                               # ③ 셰고가 주제(키보드)
    assert on.index("9005") < on.index("9004")                                          # ④ 최신 먼저
    assert p["tiers"]["1"] == 2


def test_room_caps_turn_on(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    p = SR.build("chezgoga", up=FakeUp(_products(), {"SALE": 998}), size_of=_size)
    assert p["room"] == 2 and p["on"] == 2 and p["by_reason"]["no_room"] >= 1
    assert [x["channel_no"] for x in p["rows"] if x["action"] == "on"] == ["9001", "9002"]


def test_price_policy_is_display_only(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    p = SR.build("chezgoga", up=FakeUp(_products(), {"SALE": 400}), size_of=_size)
    x = [r for r in p["rows"] if r["channel_no"] == "9001"][0]
    assert x["policy_price"] and x["price_diff"] is True
    csv = SR.csv_text(p)
    assert "정책가" in csv and "9001" in csv and "모름(API 없음)" in csv and csv.startswith("﻿")


def test_run_only_chezgoga_confirm_chunks_stop_and_raw_failures(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    up = FakeUp(_products(), {"SALE": 400, "SUSPENSION": 15}, fail={"o9002"})
    p = SR.build("chezgoga", up=up, size_of=_size)
    assert SR.start("gocosmos", 1, "o")["ok"] is False                                  # 보기만
    assert SR.start("chezgoga", p["on"] + 1, "o")["ok"] is False                        # 건수 다르면 안 감
    import src.uploaders.naver_uploader as N
    monkeypatch.setattr(N, "NaverSmartStoreUploader", lambda account=None: up)
    from src.utils import bg_job
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (fn(), (True, {}))[1])
    d = SR.start("chezgoga", p["on"], "owner@example.com")
    assert d["ok"]
    r = SR.run_state("chezgoga")
    assert r["state"] == "finished" and len(r["done"]) == p["on"] and r["ok_count"] == p["on"] - 1
    fail = [x for x in r["done"] if not x["ok"]][0]
    assert fail["channel_no"] == "9002" and "재고 수량이 0입니다" in fail["raw"]                 # 네이버 원문
    assert r["after_counts"]["SALE"] == 400 + p["on"] - 1                                 # 끝나고 다시 읽음
    puts = [c for c in up.calls if c[0] == "PUT"]
    assert all(c[2] == {"statusType": "SALE"} for c in puts)                             # 가격은 안 보낸다


def test_stop_halts_between_items(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    up = FakeUp(_products(), {"SALE": 400})
    p = SR.build("chezgoga", up=up, size_of=_size)
    import src.uploaders.naver_uploader as N
    monkeypatch.setattr(N, "NaverSmartStoreUploader", lambda account=None: up)
    sent = []

    def runner(origin):
        sent.append(origin)
        if len(sent) == 2:
            SR.stop("chezgoga")
        return {"ok": True}
    from src.utils import bg_job
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (True, {}))
    SR.start("chezgoga", p["on"], "o")
    SR._run("chezgoga", runner)
    r = SR.run_state("chezgoga")
    assert r["state"] == "stopped" and len(sent) == 2 and len(r["done"]) == 2


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["email"], s["user_role"] = "own", "owner@example.com", "admin"
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    return c


def test_admin_page_summary_csv_and_view_only_gocosmos(admin, state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    SR.build("chezgoga", up=FakeUp(_products(), {"SALE": 400, "WAIT": 1, "OUTOFSTOCK": 2, "SUSPENSION": 15}), size_of=_size)
    h = admin.get("/seller/admin/smartstore-relist?store=chezgoga", headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "켤 " in h and "건 / 뺄 " in h and "빈자리 597칸" in h and 'data-role="rl-go"' in h and "한 번 더 누르면" in h
    assert "도검(허가 필요) 1" in h and "판매중지 15" in h and "표시만" in h and 'data-role="rl-csv"' in h
    r = admin.get("/seller/admin/smartstore-relist?store=chezgoga&csv=1")
    assert r.status_code == 200 and "text/csv" in r.headers["Content-Type"] and "9001" in r.get_data(as_text=True)
    g = admin.get("/seller/admin/smartstore-relist?store=gocosmos", headers={"Accept": "text/html"}).get_data(as_text=True)
    assert 'data-role="rl-view-only"' in g and 'data-role="rl-go"' not in g
    assert admin.post("/seller/admin/smartstore-relist?store=gocosmos", json={"action": "run", "confirm": 1}).status_code == 409
    assert admin.get("/seller/admin/smartstore-relist?store=chezgoga").get_json()["plan"]["room"] == 597


def test_non_admin_forbidden(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: False)
    assert c.get("/seller/admin/smartstore-relist").status_code == 403
    assert c.post("/seller/admin/smartstore-relist", json={"action": "run", "confirm": 1}).status_code == 403
