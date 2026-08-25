"""tests/test_reject_watch_auto.py — P4 갭 수리: 등록 대장 · 자동 감시 · 알림 · 크론.

카나리 10차 관통으로 **실제 등록이 나가기 시작**했다. 그런데 서버가 무엇을 등록했는지 기억하지 않아
반려감시가 오너의 수동 sid 입력에 의존했다(분류·처방 코어는 #652에서 이미 완성).

이 파일이 고정하는 계약:
  1. 등록 성공분이 **등록 대장**에 적재된다(실패분은 안 된다).
  2. 감시가 대장에서 대상을 **스스로** 꺼내 조회·분류하고 결과를 되쓴다.
  3. **반려가 있을 때만** 알린다. 채널 미설정이면 `notified=False` + 사유(가짜 발송 0).
  4. '대상 없음'과 '조회 실패'를 구분한다(없음 확인 ≠ 수집 실패).
  5. 크론은 **즉시 202**(동기 대량 라우트 타임아웃 지뢰) + 중복 진입 스킵.
  6. 처방 실행은 여전히 **0**(승인 게이트 뒤).
"""
from __future__ import annotations

import pytest

from src.db import market_registrations_pg as REG
from src.pipeline import register_pipe as RP
from src.pipeline import reject_watch as RW


@pytest.fixture(autouse=True)
def _clean_registry():
    REG.reset_memory()
    yield
    REG.reset_memory()


# ── 1. 등록 대장 적재 ────────────────────────────────────────────────────────────
_ROWS = [{"url": "https://www.amazon.com/dp/B0AAAAAAA1", "title_ko": "원목 식탁",
          "sale_krw": 71900, "excluded": False},
         {"url": "https://www.amazon.com/dp/B0BBBBBBB2", "title_ko": "스텐 텀블러",
          "sale_krw": 27200, "excluded": False}]

_ENRICH = {"images": ["https://i/1.jpg"], "description_html": "<p>d</p>", "category_code": "GEN"}


def _register(dispatch, record_fn=None, **kw):
    return RP.register_source_rows(_ROWS, dispatch_fn=dispatch, enrich_fn=lambda r: dict(_ENRICH),
                                   approved=True, account="gogane", sleep_fn=lambda s: None,
                                   record_fn=record_fn, **kw)


def test_successful_registration_recorded_in_registry():
    out = _register(lambda pd, a: {"success": True, "product_id": "SP1",
                                   "url": "https://coupang/SP1"},
                    record_fn=lambda e: REG.record(e["product_id"], account=e["account"],
                                                   vendor_sku=e["vendor_sku"], title=e["title"],
                                                   source_url=e["source_url"],
                                                   market_url=e["market_url"]))
    assert out["registered"] == 1                                   # 카나리 1건
    row = REG.get("SP1")
    assert row and row["status"] == "submitted"
    assert row["title"] == "원목 식탁" and row["account"] == "gogane"


def test_failed_registration_not_recorded():
    """실패분은 대장에 안 들어간다 — 없는 상품을 감시하지 않는다."""
    calls = []
    out = _register(lambda pd, a: {"success": False, "error": "거부"},
                    record_fn=lambda e: calls.append(e))
    assert out["registered"] == 0 and calls == []
    assert REG.counts() == {}


def test_registry_failure_is_reported_not_swallowed():
    """대장 적재 실패는 등록을 롤백하지 않되 **행에 사유**를 남긴다(조용한 실패 금지)."""
    def _boom(entry):
        raise RuntimeError("DB 연결 끊김")
    out = _register(lambda pd, a: {"success": True, "product_id": "SP9"}, record_fn=_boom)
    r = out["results"][0]
    assert r["registered"] is True and r["product_id"] == "SP9"      # 등록은 유지(롤백 금지)
    assert "등록 대장 적재 실패" in r["registry_error"]


def test_vendor_sku_recorded_from_url():
    _register(lambda pd, a: {"success": True, "product_id": "SP2"},
              record_fn=lambda e: REG.record(e["product_id"], vendor_sku=e["vendor_sku"]))
    assert REG._MEM["coupang|SP2"]["vendor_sku"] == "B0AAAAAAA1"     # #663 ASIN


def test_watch_queue_and_status_transitions():
    REG.record("SP1", account="gogane", title="t1")
    REG.record("SP2", account="woojoo", title="t2")
    assert {q["sid"] for q in REG.watch_queue()} == {"SP1", "SP2"}
    assert [q["sid"] for q in REG.watch_queue(account="gogane")] == ["SP1"]
    REG.mark_checked("SP1", status="approved")
    assert [q["sid"] for q in REG.watch_queue()] == ["SP2"]          # 확정분은 큐에서 빠진다
    assert REG.counts() == {"approved": 1, "submitted": 1}


# ── 2·3·4. 자동 감시 오케스트레이션 ──────────────────────────────────────────────
_HIST_REJECT = {"data": [{"statusName": "승인반려", "comment": "대표 이미지 해상도가 규격에 미달합니다."}]}
_HIST_NONE = {"data": [{"statusName": "심사중", "comment": ""}]}


def _watch(queue, history, **kw):
    return RW.watch_registered(queue_fn=lambda n: queue, history_fn=history, **kw)


def test_watch_pulls_from_registry_and_writes_back():
    REG.record("SP1", account="gogane", title="케이스")
    recorded = []
    out = RW.watch_registered(
        queue_fn=lambda n: REG.watch_queue(limit=n),
        history_fn=lambda sid, acct: _HIST_REJECT,
        record_fn=lambda sid, **kw: (recorded.append((sid, kw)), REG.mark_checked(sid, **kw))[1])
    assert out["ok"] and out["scanned"] == 1
    assert out["rows"][0]["kind"] == "image_spec"
    assert out["rows"][0]["prescription"] == "reupload"
    assert out["recorded"] == 1
    saved = REG.get("SP1")
    assert saved["status"] == "rejected" and saved["reject_kind"] == "image_spec"
    assert saved["prescription"] == "reupload"
    assert "해상도" in saved["reject_comment"]


def test_empty_queue_is_normal_not_failure():
    """'대상 없음'을 '조회 실패'로 보고하지 않는다(없음 확인 ≠ 수집 실패)."""
    out = _watch([], lambda sid, acct: _HIST_REJECT)
    assert out["ok"] is True and out["scanned"] == 0
    assert "없음" in out["alert"] and "error" not in out


def test_queue_read_failure_is_reported_as_failure():
    def _boom(n):
        raise RuntimeError("PG 연결 실패")
    out = RW.watch_registered(queue_fn=_boom, history_fn=lambda sid, acct: {})
    assert out["ok"] is False and "감시 큐 조회 실패" in out["error"]


def test_history_fetch_failure_does_not_mark_status():
    """조회 실패 건은 상태를 바꾸지 않는다 — 확인 실패를 '확인함'으로 만들지 않는다."""
    REG.record("SP1", title="x")

    def _boom(sid, acct):
        raise RuntimeError("타임아웃")
    seen = {}
    RW.watch_registered(queue_fn=lambda n: REG.watch_queue(limit=n), history_fn=_boom,
                        record_fn=lambda sid, **kw: seen.update(kw) or REG.mark_checked(sid, **kw))
    assert seen["status"] == ""                                     # 상태 미변경
    assert REG.get("SP1")["status"] == "submitted"                  # 여전히 감시 대상


def test_notify_only_when_rejection_present():
    sent = []
    out = _watch([{"sid": "S1", "title": "t", "account": "gogane"}],
                 lambda sid, acct: _HIST_NONE, notify_fn=lambda a, r: sent.append(a))
    assert out["notified"] is False and sent == []                  # 반려 없음 → 알림 0(잡음 0)
    out2 = _watch([{"sid": "S2", "title": "t", "account": "gogane"}],
                  lambda sid, acct: _HIST_REJECT, notify_fn=lambda a, r: sent.append(a))
    assert out2["notified"] is True and len(sent) == 1


def test_notify_failure_is_honest_not_fake_success():
    """채널 미설정이면 notified=False + 사유. 감시 자체는 성공."""
    def _fail(alert, rows):
        raise RuntimeError("TELEGRAM_BOT_TOKEN 미설정")
    out = _watch([{"sid": "S1", "title": "t", "account": "gogane"}],
                 lambda sid, acct: _HIST_REJECT, notify_fn=_fail)
    assert out["ok"] is True and out["scanned"] == 1
    assert out["notified"] is False and "알림 발송 실패" in out["notify_error"]


def test_time_budget_stops_and_reports_remaining():
    """예산 초과 시 중단하고 남은 수를 알린다([[동기 대량 라우트 타임아웃 지뢰]])."""
    clock = iter([0.0, 0.0, 9.0, 9.0, 9.0])
    q = [{"sid": f"S{i}", "title": "t", "account": "gogane"} for i in range(5)]
    out = RW.watch_registered(queue_fn=lambda n: q, history_fn=lambda sid, acct: _HIST_REJECT,
                              time_budget_sec=5.0, monotonic_fn=lambda: next(clock))
    assert out["budget_exhausted"] is True
    assert out["scanned"] == 1 and out["remaining_hint"] == 4


def test_watch_never_applies_prescription():
    """감시는 조회·분류·기록·알림까지 — 실행 0(비가역은 승인 게이트 뒤)."""
    import inspect
    src = inspect.getsource(RW.watch_registered)
    for forbidden in ("apply_prescription", "delete_fn", "reupload_fn", "reissue_fn"):
        assert forbidden not in src, forbidden
    row = {"sid": "S1", "kind": "trademark"}
    assert RW.apply_prescription(row, delete_fn=lambda s: "deleted")["applied"] is False


# ── 5. 크론 라우트 ───────────────────────────────────────────────────────────────
def _client(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from src.order_webhook import app
    return app.test_client()


def test_cron_returns_202_immediately(monkeypatch):
    import src.pricing.cron as CRON
    spawned = {}
    monkeypatch.setattr(CRON, "_spawn_reject_watch",
                        lambda app, account, limit, budget: spawned.update(
                            {"account": account, "limit": limit}))
    if CRON._reject_lock.locked():
        try:
            CRON._reject_lock.release()
        except RuntimeError:
            pass
    r = _client(monkeypatch).post("/cron/reject-watch?account=woojoo&limit=7")
    assert r.status_code == 202                                     # 즉답 = 크론 성공 판정
    d = r.get_json()
    assert d["status"] == "accepted" and d["account"] == "woojoo"
    assert spawned == {"account": "woojoo", "limit": 7}
    try:
        CRON._reject_lock.release()
    except RuntimeError:
        pass


def test_cron_rejects_unknown_account(monkeypatch):
    r = _client(monkeypatch).post("/cron/reject-watch?account=nobody")
    assert r.status_code == 400


def test_cron_skips_when_already_running(monkeypatch):
    import src.pricing.cron as CRON
    monkeypatch.setattr(CRON, "_spawn_reject_watch", lambda *a: None)
    assert CRON._reject_lock.acquire(blocking=False)
    try:
        r = _client(monkeypatch).post("/cron/reject-watch")
        assert r.status_code == 202 and r.get_json()["skipped"] is True
    finally:
        CRON._reject_lock.release()


def test_cron_secret_enforced(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    from src.order_webhook import app
    r = app.test_client().post("/cron/reject-watch")
    assert r.status_code == 401


def test_notify_fn_does_not_claim_success_without_channel(monkeypatch):
    """실 발송기: 채널 미설정이면 예외 → notified=False로 이어진다(가짜 발송 0)."""
    import src.pricing.cron as CRON
    monkeypatch.setattr("src.notifications.telegram.send_telegram", lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        CRON._reject_notify_fn("gogane")("반려 1건", [{"sid": "S1", "kind_ko": "이미지 규격",
                                                      "comment": "x"}])


def test_schema_stage6_wired():
    from pathlib import Path
    assert "schema_stage6.sql" in Path("src/db/pg.py").read_text(encoding="utf-8")
    sql = Path("src/db/schema_stage6.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS market_registrations" in sql
    assert "uq_mktreg_active" in sql and "set_updated_at" in sql
