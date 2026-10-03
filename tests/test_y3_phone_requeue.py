"""Y3(오너 2026-10-04) — 폰(확장 없음)의 「원본에서 다시 수집」: 새 탭 안내 대신 **재보강 큐** + 「대기 n번째」.

R1 백그라운드 보강 = 확장 폴러 `GET /api/v1/collect/enrich/pending` — 이 라우트가 큐 모드로 넣은 행을 실제로 집는지 잰다.
"""
from __future__ import annotations

import json


def test_queue_mode_puts_item_where_the_extension_poller_looks(monkeypatch):
    import src.api.extension_api as E
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "owner-y3"
    done = {"title": "블랙홀 무드등", "enrich_state": "done", "enriched": True,
            "images": ["https://img.alicdn.com/a.jpg"], "price": "69.90"}
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id=seller,
                   title="블랙홀 무드등", price="69.90", currency="CNY", extra=done)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    d = c.post(f"/seller/collect/{iid}/recollect?mode=queue", json={}).get_json()
    assert d["ok"] and d["queued"] and d["position"] == 1
    assert d["message"] == "PC 확장이 켜지면 자동으로 다시 보강됩니다 (대기 1번째)" and "open_url" not in d
    monkeypatch.setattr(E, "_require_token", lambda scopes=None: {"user_id": seller})
    pend = c.get("/api/v1/collect/enrich/pending").get_json()
    assert iid in [it["item_id"] for it in pend["items"]]
    st = c.get(f"/seller/collect/{iid}/state").get_json()
    assert st["enrich_rerun_waiting"] is True and st["enrich_rerun_done_at"] == ""
    # 확장이 다시 보강하면 표시가 내려간다
    c.post("/api/v1/collect/enrich", json={"item_id": iid, "title": "黑洞小夜灯", "gallery": ["https://img.alicdn.com/b.jpg"],
                                           "page_diag": {"sel": {"title": 9, "detail": 13}}})
    st = c.get(f"/seller/collect/{iid}/state").get_json()
    assert st["enrich_rerun_waiting"] is False and st["enrich_rerun_done_at"] >= d["requested_at"]


def test_pc_mode_still_opens_the_source():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "owner-y3-pc"
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=1", seller_id=seller,
                   title="x", price="1", currency="CNY", extra={"title": "x"})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    d = c.post(f"/seller/collect/{iid}/recollect").get_json()
    assert d["ok"] and d["open_url"].startswith("https://item.taobao.com") and not d.get("queued")


def test_drawer_picks_queue_mode_without_extension_marker():
    from pathlib import Path
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "data-kgp-ext" in pv and "?mode=queue" in pv and "enrich_rerun_done_at" in pv
