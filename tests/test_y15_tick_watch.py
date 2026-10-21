"""Y15(오너 2026-10-21 야간) — 틱 멈춤 재발 방지 · 미등록 전부 사전검증(check_item, 한 틱 무거운 일 하나).

운영 10-21: 10:20~12:43 UTC 틱 2시간 반 공백 — Render 메일은 12:43에야 왔고, 그 전 유일한 신호는 틱 기록 공백.
인스턴스가 왜 응답을 못 했는지는 미확인(추정 금지) — 여기서는 나이만 보인다.
"""
import json
from datetime import datetime, timedelta, timezone

from src.services import tick_watch as TW

NOW = datetime(2026, 10, 21, 12, 40, tzinfo=timezone.utc)


def _runs(at):
    return {"kohganeproxxxxy-singapore": {"translate-pilot-tick": {"last_at": at.isoformat()}}}


def test_status_fresh_tick_line_only():
    st = TW.status(NOW, leases=[{"name": "translate-pilot-tick", "holder": "svc:13", "updated_at": NOW - timedelta(minutes=4)}],
                   runs=_runs(NOW - timedelta(minutes=3)))
    assert st["seen"] and not st["stale"] and st["age_min"] == 3
    assert st["line"] == "마지막 틱 21:37" and st["todo"] == ""                 # KST
    assert st["leases"][0] == {"name": "translate-pilot-tick", "holder": "svc:13", "age_min": 4}


def test_status_stale_after_30_minutes_says_no_cause():
    last = datetime(2026, 10, 21, 10, 20, tzinfo=timezone.utc)                  # 운영 실측 마지막 틱
    st = TW.status(NOW, leases=[{"name": "translate-pilot-tick", "updated_at": last}], runs={})
    assert st["stale"] and st["age_min"] == 140
    assert st["todo"].startswith("틱 멈춤 140분") and "원인 미확인" in st["todo"]
    assert "cron" not in st["todo"]                                            # 원인 추정 금지


def test_status_never_seen_is_not_stale():
    st = TW.status(NOW, leases=[], runs={})
    assert st["seen"] is False and st["stale"] is False and st["line"] == ""


def test_dashboard_tick_lines_admin_only(monkeypatch):
    from src.seller_console import home_bundles as HB
    monkeypatch.setattr(TW, "status", lambda *a, **k: {"seen": True, "stale": True, "age_min": 140,
                                                       "line": "마지막 틱 19:20 · 140분 전", "todo": "틱 멈춤 140분 — x"})
    out = {"running": {"n": 0, "lines": [], "show": False}, "attention": {"n": 0, "todo": [], "groups": []}}
    HB._tick_lines(out)
    assert out["running"]["show"] and out["running"]["lines"] == ["마지막 틱 19:20 · 140분 전"]
    assert out["attention"]["n"] == 1 and out["attention"]["todo"][0]["kind"] == "tick_stale"
    assert out["attention"]["groups"][0]["label"] == "틱 멈춤 140분"
    called = []
    monkeypatch.setattr(HB, "_tick_lines", lambda o: called.append(1))
    monkeypatch.setattr(HB, "_rows", lambda ids: [])
    HB.build({"u1"})                                                          # 관리자 아님(기본) — 안 붙인다
    assert called == []


def test_health_deep_carries_tick_ages(monkeypatch):
    monkeypatch.setattr(TW, "status", lambda *a, **k: {"seen": True, "age_min": 5, "stale": False,
                                                       "leases": [{"name": "imgko-auto", "holder": "svc:13", "age_min": 5}]})
    from src.order_webhook import app
    js = app.test_client().get("/health/deep").get_json()
    t = js["ticks"]
    assert t["last_tick_age_min"] == 5 and t["stale"] is False and t["stale_after_min"] == 30
    assert t["leases"] == [{"name": "imgko-auto", "age_min": 5}]               # 보유자(서비스:pid)는 공개 헬스에 안 낸다
    assert "checks" in js and "status" in js                                  # 기존 응답 그대로


def _item(extra, iid="4863d363-274a-431f-a8fe-4b4b531c9bd9"):
    return {"id": iid, "extra_json": json.dumps(extra, ensure_ascii=False)}


def test_check_item_furniture_fetches_dims_then_queues_prevalidate(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    sofa = {"title": "懒人沙发豆袋", "title_ko": "빈백 소파 1인용"}
    monkeypatch.setattr(D, "_item", lambda iid: (_item(sofa), "u1"))
    rows, pv = [], []
    monkeypatch.setattr(O, "enqueue", lambda row: rows.append(row) or True)
    r = O.check_item("4863d363", ["coupang:gogane"], fetch=lambda iid: {"ok": True, "dims_cm": None},
                     prevalidate=lambda iid, m: pv.append(iid) or {"ok": True})
    assert r["step"] == "dims_fetch" and r["prevalidate_queued"] and pv == []     # 이번 틱엔 사전검증 안 띄움
    assert rows == [{"op": "prevalidate", "item_id": "4863d363-274a-431f-a8fe-4b4b531c9bd9", "markets": ["coupang:gogane"],
                     "reason": "check_item — 치수 수집 뒤"}]
    # 이미 서버 치수 수집이 돌았으면(결과 「없음」이어도) 바로 사전검증
    monkeypatch.setattr(D, "_item", lambda iid: (_item(dict(sofa, dims_auto={"dims_cm": None})), "u1"))
    r2 = O.check_item("4863d363", ["coupang:gogane"], fetch=lambda iid: 1 / 0,
                      prevalidate=lambda iid, m: {"ok": True, "job_id": "j1"})
    assert r2 == {"ok": True, "job_id": "j1", "step": "prevalidate"}
    assert "check_item" in O.HEAVY_OPS and "check_item" in O.OPS


def test_check_item_non_furniture_goes_straight_to_prevalidate(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    monkeypatch.setattr(D, "_item", lambda iid: (_item({"title": "手机壳", "title_ko": "휴대폰 케이스"}), "u1"))
    r = O.check_item("x1", [], fetch=lambda iid: 1 / 0, prevalidate=lambda iid, m: {"ok": True, "job_id": "j2"})
    assert r["step"] == "prevalidate" and r["job_id"] == "j2"
