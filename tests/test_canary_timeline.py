"""쿠팡 성공률 캐너리 측정 — 한 상품의 단계별 시각·소요를 **저장된 값만으로**(오너 2026-09-28).

수집 → 보강 완료 → 번역 첫·마지막 장 → 등록 성공(마켓별). 기록 없는 단계는 비워 둔다(지어낸 시각 0).
"""
from __future__ import annotations

import json


def _seed(seller, extra, collected="2026-09-28T05:00:00+00:00"):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", seller_id=seller, url="https://item.taobao.com/item.htm?id=640000000001",
                   title="수행방패", price="29.9", currency="CNY", extra=extra)
    iid = iid[0] if isinstance(iid, tuple) else iid
    rows = S._in_memory if hasattr(S, "_in_memory") else None
    for r in (rows or []):
        if r.get("id") == iid:
            r["collected_at"] = collected
    return iid


def test_timeline_from_stored_times(monkeypatch):
    from src.order_webhook import app
    seller = "u-canary-tl"
    iid = _seed(seller, {
        "image_check": {"ok": True, "at": "2026-09-28T05:02:30+00:00"},
        "images_ko": [{"idx": 0, "status": "done", "at": "2026-09-28T05:03:00+00:00"},
                      {"idx": 1, "status": "done", "at": "2026-09-28T05:04:10+00:00"},
                      {"idx": 2, "status": "failed", "at": "2026-09-28T05:05:00+00:00"}],
        "uploaded": [{"market": "coupang", "label": "쿠팡", "at": "2026-09-28T05:10:00+00:00"}],
    })
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    d = c.get(f"/seller/collect/preview/{iid}/timeline").get_json()
    steps = {s["step"]: s for s in d["steps"]}
    assert d["ok"] and list(steps) == ["수집", "보강 완료", "번역 첫 장", "번역 마지막 장", "등록 성공 · 쿠팡"]
    assert steps["보강 완료"]["since_collect_s"] == 150
    assert steps["번역 마지막 장"]["since_collect_s"] == 250 and steps["번역 마지막 장"]["since_prev_s"] == 70
    assert steps["등록 성공 · 쿠팡"]["since_collect_s"] == 600      # 실패한 장(05:05)은 번역 시각에 안 든다


def test_missing_steps_stay_empty():
    from src.seller_console.views import item_timeline
    t = item_timeline({"id": "x", "collected_at": "2026-09-28T05:00:00+00:00", "extra_json": "{}"})
    steps = {s["step"]: s for s in t["steps"]}
    assert steps["수집"]["since_collect_s"] == 0
    assert steps["보강 완료"] == {"step": "보강 완료", "at": "", "since_collect_s": None, "since_prev_s": None}
    assert not any(k.startswith("등록 성공") for k in steps)


def test_timeline_is_owner_scoped():
    from src.order_webhook import app
    iid = _seed("u-canary-other", {})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-canary-me"
    assert c.get(f"/seller/collect/preview/{iid}/timeline").status_code == 404
