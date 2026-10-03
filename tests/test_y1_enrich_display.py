"""Y1(교체, 오너 2026-10-04) — 재보강 뒤 표시가 옛 값으로 남던 것 · 시각 UTC 표기 · 빈 페이지 보강 = 완료 아님.

실측(운영 DB, 오너 목록 51건): 「보강 필요」 배너 5건 — 전부 이미 보강 완료(`uncollected`가 price만 지워져 남음) ·
상세 이미지에 가게 아이콘·추적 픽셀(`…-24-24.png`·`s.gif`·`tps-120-60`) 섞인 행 37건(쓰레기만 4건).
재현 행 301c02cd(share 10-02 10:18 · 69.90 CNY): 10-03 16:05Z(=01:05 KST) 재수집으로 제목은 왔고 상세 이미지는 쓰레기 2장.
"""
from __future__ import annotations

import json

from src.collectors.collect_status import bot_wall_reason, is_junk_asset, real_detail_images, still_uncollected

ICON = "https://gtms04.alicdn.com/tps/i4/TB1wA25HpXXXXcwXVXXCBGNFFXX-24-24.png_.webp"
GIF = "https://g.alicdn.com/s.gif"
TPS = "https://gw.alicdn.com/imgextra/i1/O1CN01VD9Iap25oweneR31D_!!6000000007574-2-tps-120-60.png_.webp"
REAL = "https://img.alicdn.com/imgextra/i2/2211654478308/O1CN01NxMLJO2BF7WOmzgwU_!!2211654478308.jpg"
REAL_TPS = "https://img.alicdn.com/x/O1CN01-0-tps-750-1000.jpg"


def test_junk_assets_are_recognised_and_real_images_kept():
    assert all(is_junk_asset(u) for u in (ICON, GIF, TPS, ""))
    assert not is_junk_asset(REAL) and not is_junk_asset(REAL_TPS)
    assert real_detail_images([ICON, REAL, GIF, REAL_TPS]) == [REAL, REAL_TPS]


def test_banner_reflects_actual_values():
    ex = {"uncollected": ["price", "images", "options", "description"], "price": "69.90",
          "images": [REAL], "options": [{"name": "颜色", "values": ["黑"]}], "description": "", "detail_images": [ICON, GIF]}
    assert still_uncollected(ex) == ["description"]                       # 쓰레기 상세 이미지는 「채움」이 아니다
    ex["detail_images"].append(REAL)
    assert still_uncollected(ex) == []


def test_bot_wall_is_judged_only_by_title_and_detail_hits():
    wall = {"title": "", "page_diag": {"sel": {"title": 0, "detail": 0, "gallery": 0},
                                      "resources": ["https://pass.tmall.com/add?x", "https://pass.fliggy.com/y"]}}
    assert bot_wall_reason(wall).startswith("보강 실패: 봇 확인 페이지")
    ok_with_beacon = {"title": "黑洞小夜灯", "page_diag": {"sel": {"title": 9, "detail": 13},
                                                       "resources": ["https://pass.tmall.com/add?x"]}}
    assert bot_wall_reason(ok_with_beacon) == ""                          # 공통 비컨은 근거 아님
    assert bot_wall_reason({"title": ""}) == ""                           # 진단 없으면 판정 안 함


def _client_and_item(seller, extra):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id=seller,
                   title="", price="69.90", currency="CNY", extra=extra)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c, iid, S


def test_empty_page_enrich_is_discarded_and_requeued(monkeypatch):
    import src.api.extension_api as E
    seller = "owner-y1-wall"
    extra = {"title": "", "uncollected": ["images", "options", "description"], "images": [], "enrich_state": "pending"}
    c, iid, S = _client_and_item(seller, extra)
    monkeypatch.setattr(E, "_require_token", lambda scopes=None: {"user_id": seller})
    r = c.post("/api/v1/collect/enrich", json={"item_id": iid, "title": "", "detail_images": [ICON],
                                               "page_diag": {"sel": {"title": 0, "detail": 0}}})
    d = r.get_json()
    assert d["ok"] is False and d["requeued"] and "봇 확인 페이지" in d["error"]
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert ex["enrich_state"] == "pending" and ex["enrich_rerun"] is True and not ex.get("detail_images")  # 덮어쓰기 0
    assert ex["enrich_attempts"] == 1                                       # 같은 벽 무한 반복 방지(상한 3)
    from src.collectors.collect_status import enrich_axes
    assert enrich_axes(ex)["enrich_state"] == "pending"                     # 재보강 큐(확장 폴러)가 집는다
    h = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert 'data-role="enrich-fail"' in h and "KST" in h


def test_good_enrich_clears_banner_and_drops_junk(monkeypatch):
    import src.api.extension_api as E
    seller = "owner-y1-good"
    extra = {"title": "", "uncollected": ["price", "images", "options", "description"], "images": [],
             "detail_images": [ICON, GIF], "enrich_state": "pending"}
    c, iid, S = _client_and_item(seller, extra)
    monkeypatch.setattr(E, "_require_token", lambda scopes=None: {"user_id": seller})
    r = c.post("/api/v1/collect/enrich", json={
        "item_id": iid, "title": "【BLACKHOLES】黑洞小夜灯", "price": "69.90", "currency": "CNY",
        "images": [REAL], "detail_images": [ICON, REAL_TPS], "options": [{"name": "颜色", "values": ["黑"]}],
        "description": "黑洞小夜灯 星空投影 卧室氛围灯 USB供电 详细说明", "page_diag": {"sel": {"title": 9, "detail": 13}}})
    assert r.get_json()["ok"]
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert ex["uncollected"] == [] and ex["detail_images"] == [REAL_TPS] and ex["enrich_state"] == "done"
    h = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert "앱 공유 글에는 제목과 링크만" not in h


def test_stale_banner_is_recomputed_at_render():
    seller = "owner-y1-stale"
    extra = {"title": "x", "title_ko": "블랙홀 무드등", "uncollected": ["images", "options", "description"],
             "images": [REAL], "options": [{"name": "颜色", "values": ["黑"]}], "description": "상세 설명입니다",
             "enrich_state": "done", "recollected_at": "2026-10-03T16:05:09Z",
             "merge_log": [{"at": "2026-10-03T16:05:09Z", "path": "recollect", "changed": {"title": "비어 있음→ICE"}, "kept": {}}]}
    c, iid, _ = _client_and_item(seller, extra)
    h = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert "앱 공유 글에는 제목과 링크만" not in h
    assert "마지막 갱신 2026-10-04 01:05 KST" in h                          # UTC 16:05 → KST 01:05
    assert "마지막 갱신 2026-10-03 16:05" not in h
    st = c.get(f"/seller/collect/{iid}/state").get_json()
    assert st["title"] == "블랙홀 무드등"


def test_outbound_payload_drops_junk_detail_images():
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    pd = build_dispatch_payload({"title": "블랙홀 무드등", "detail_images": [ICON, REAL, GIF]})
    assert pd["detail_images"] == [REAL]


def test_drawer_reload_and_parent_update_wiring():
    from pathlib import Path
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    ch = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    assert "kgp: 'item-updated'" in pv and "location.reload()" in pv
    assert "e.data.kgp === 'item-updated'" in ch and "kgpDrawerTitle" in ch
