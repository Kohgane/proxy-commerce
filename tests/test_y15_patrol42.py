"""Y15 순찰 42(오너 2026-10-23) — 등록 대장 주인 칸 · 반려감시 주인 키 조회(쓰기 0) · 화면은 내 줄만 · /health/deep queued."""
import pytest


@pytest.fixture(autouse=True)
def _ledger_mem(monkeypatch):
    from src.db import market_registrations_pg as REG
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(REG, "enabled", lambda: False)
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    monkeypatch.setenv("FAMILY_EMAILS", "fam@example.com")
    REG.reset_memory()
    mc._shared_cache.clear()
    yield
    REG.reset_memory()
    mc._shared_cache.clear()


def _seed():
    from src.db import market_registrations_pg as REG
    REG.record("111", account="gogane", title="오너 옛 줄")                          # 칸 생기기 전 줄 = 주인 빈 값
    REG.record("222", account="gogane", title="셀러 줄", owner_seller_id="u-plain")


# ── 대장 주인 칸 ────────────────────────────────────────────────────────────────

def test_record_keeps_owner_and_rereg_without_owner_does_not_erase_it():
    from src.db import market_registrations_pg as REG
    _seed()
    REG.record("222", account="gogane", title="다시 등록")                         # 빈 값으로 다시 와도
    rows = {r["sid"]: r for r in REG.watch_queue(account="gogane")}
    assert rows["222"]["owner"] == "u-plain" and rows["111"]["owner"] == ""


def test_owner_scope_shared_sees_all_plain_sees_own_only():
    from src.auth.identity import OWNER_USER_ID
    from src.db import market_registrations_pg as REG
    _seed()
    assert REG.owner_scope([]) is None and REG.owner_scope({OWNER_USER_ID}) is None
    assert REG.owner_scope({"u-plain", "plain@example.com"}) == ["plain@example.com", "u-plain"]
    mine = REG.watch_queue(account="gogane", owners=REG.owner_scope({"u-plain"}))
    assert [r["sid"] for r in mine] == ["222"]                                       # 오너 옛 줄은 안 보인다
    assert {r["sid"] for r in REG.watch_queue(account="gogane", owners=None)} == {"111", "222"}
    assert REG.watch_queue(account="gogane", owners=[]) == []                          # 판정이 깨지면 닫는다


# ── 반려감시: 주인 키로 조회 · 쓰기 0 ─────────────────────────────────────────────

class _ReadOnlyUploader:
    """조회(get_status_histories) 말고 다른 메서드를 부르면 테스트가 깨진다 — 쓰기 0 확인."""
    calls: list = []

    def __init__(self, access_key, secret_key, vendor_id, account):
        self.key = access_key

    def get_status_histories(self, sid):
        type(self).calls.append((sid, self.key))
        return [{"status": "APPROVING", "comment": ""}]

    def __getattr__(self, name):
        raise AssertionError(f"반려감시가 조회 밖 메서드를 불렀다: {name}")


def _run(monkeypatch, seller_keys):
    import os
    from src.pipeline import coupang_replicate as CR
    from src.pricing import cron as C
    from src.seller_console import market_credentials as mc
    from src.uploaders import coupang_uploader as CU
    _ReadOnlyUploader.calls = []
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "SERVER-KEY")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "server-secret")
    monkeypatch.setattr(CR, "_account_creds", lambda acct: (os.environ.get("COUPANG_ACCESS_KEY", ""),
                                                           os.environ.get("COUPANG_SECRET_KEY", ""), "A1"))
    monkeypatch.setattr(CU, "CoupangUploader", _ReadOnlyUploader)
    monkeypatch.setattr(mc, "all_credential_env", lambda sid: dict(seller_keys) if sid == "u-plain" else {})
    monkeypatch.setattr(C, "_reject_notify_fn", lambda acct: None)
    from src.order_webhook import app
    if not C._reject_lock.acquire(blocking=False):
        pytest.skip("다른 반려감시가 락을 잡고 있다")
    return C._run_reject_watch(app, "gogane", 10, 30)


def test_cron_reads_each_row_with_its_owner_keys(monkeypatch):
    _seed()
    out = _run(monkeypatch, {"COUPANG_ACCESS_KEY": "SELLER-KEY", "COUPANG_SECRET_KEY": "seller-secret"})
    assert out["ok"] and out["scanned"] == 2
    assert sorted(_ReadOnlyUploader.calls) == [("111", "SERVER-KEY"), ("222", "SELLER-KEY")]


def test_cron_never_reads_a_plain_sellers_row_with_server_keys(monkeypatch):
    _seed()
    out = _run(monkeypatch, {})                                                      # 이 셀러는 자기 키가 없다
    assert _ReadOnlyUploader.calls == [("111", "SERVER-KEY")]                        # 서버 키로 대신 보지 않는다
    row = next(r for r in out["rows"] if r["sid"] == "222")
    assert "주인 쿠팡 키 없음" in row["error"] and "마켓 연동에서 내 키를 넣어 주세요" in row["error"]
    from src.db import market_registrations_pg as REG
    assert REG.get("222")["status"] == "submitted"                                   # 조회 실패는 상태를 안 바꾼다


# ── 화면: 내 줄만 ────────────────────────────────────────────────────────────────

def test_dashboard_and_reject_watch_page_show_only_my_rows(monkeypatch):
    from src.db import market_registrations_pg as REG
    from src.seller_console import home_bundles as HB
    REG.record("333", account="gogane", title="오너 반려 줄")
    REG.mark_checked("333", status="rejected", reject_comment="이미지 규격")
    REG.record("444", account="gogane", title="셀러 반려 줄", owner_seller_id="u-plain")
    REG.mark_checked("444", status="rejected", reject_comment="이미지 규격")
    assert [r["title"] for r in REG.recent_rejected(owners=REG.owner_scope({"u-plain"}))] == ["셀러 반려 줄"]
    seen = []
    monkeypatch.setattr(REG, "enabled", lambda: True)                                 # 대시보드는 대장이 붙었을 때만 읽는다
    monkeypatch.setattr(REG, "recent_rejected", lambda **kw: seen.append(kw.get("owners")) or [])
    HB._ledger_rejections(seller_ids={"u-plain"})
    HB._ledger_rejections(seller_ids=set())
    assert seen == [["u-plain"], None]                                                # 일반 셀러 = 내 줄 · 서버 자신 = 전부
    monkeypatch.setattr(REG, "enabled", lambda: False)
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"], s["user_email"], s["user_role"] = "u-plain", "plain@example.com", "seller"
        html = c.get("/seller/sourcing/reject-watch").get_data(as_text=True)
    assert "셀러 반려 줄" in html and "오너 반려 줄" not in html


# ── /health/deep: 돌 게 없음 vs 멈춤 ───────────────────────────────────────────────

def test_queued_for_known_leases_and_none_for_unknown(monkeypatch):
    from src.services import tick_watch as TW
    _seed()
    assert TW.queued_for("reject-watch") == 2
    assert TW.queued_for("no-such-lease") is None
    monkeypatch.setattr(TW, "_q_optko", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    assert TW.queued_for("optko-auto") is None                                        # 못 읽으면 0이라 단정하지 않는다


# ── d5af2185 오너 옵션 값 결정 ──────────────────────────────────────────────────────

def test_owner_option_overrides_use_editor_slot_and_keep_originals():
    from src.services import oneshot_ops as O
    from src.uploaders.coupang_options import resolve_option_value
    w, b = "白色【移动充Pro版】四合一多形态 · 6000mAh双向充电", "黑色【移动充Pro版】四合一多形态 · 6000mAh双向充电"
    ex = {"options": [{"name": "颜色分类", "values": [w, b, "白色【台灯版】阅读/学习"]}], "skus": [{"spec": [w]}]}
    r = O._owner_option_overrides(ex, {w: "화이트 충전 Pro 4in1 6000mAh", b: "블랙 충전 Pro 4in1 6000mAh",
                                       "없는 값": "x"}, "u1")
    assert r["set"] == 2 and r["rows"][2] == {"value": "없는 값", "ok": False, "why": "지금 옵션에 없는 값"}
    assert ex["options"][0]["values"][:2] == [w, b] and ex["skus"][0]["spec"] == [w]            # 원문 그대로
    assert ex["owner_fields_log"][-1]["before"] == {"option_value_overrides": {w: None, b: None}}
    got = resolve_option_value(w, values_ko="화이트 [이동식 충전기 Pro 버전] 4-in-1 멀티 포맷 · 6000mAh 양방향 충전",
                               override=ex["option_value_overrides"][w])
    assert got["value"] == "화이트 충전 Pro 4in1 6000mAh"                                      # 오너 값이 1순위


@pytest.mark.skipif(not __import__("os").getenv("DATABASE_URL"), reason="PG 레인 전용")
def test_pg_owner_filter_and_coalesce(monkeypatch):
    import uuid
    from src.db import market_registrations_pg as REG, pg
    monkeypatch.setattr(REG, "enabled", lambda: True)
    pg.init_schema()
    a, b = "t42-" + uuid.uuid4().hex[:8], "t42-" + uuid.uuid4().hex[:8]
    try:
        REG.record(a, account="t42", title="서버 줄")
        REG.record(b, account="t42", title="셀러 줄", owner_seller_id="u-pg")
        REG.record(b, account="t42", title="다시", owner_seller_id="")             # 빈 값으로 다시 와도 주인 유지
        assert [r["sid"] for r in REG.watch_queue(account="t42", owners=["u-pg"])] == [b]
        assert {r["sid"]: r["owner"] for r in REG.watch_queue(account="t42")} == {a: "", b: "u-pg"}
        assert REG.watch_queue(account="t42", owners=[]) == []
        assert sum(c["n"] for c in REG.account_counts(owners=["u-pg"]) if c["account"] == "t42") == 1
    finally:
        with pg.tx() as cur:
            cur.execute("DELETE FROM market_registrations WHERE account='t42'")


def test_owner_vendor_ids_shown_only_to_shared_viewers():
    from src.auth.identity import OWNER_USER_ID
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        for uid, shown in (("u-plain", False), (OWNER_USER_ID, True)):
            with c.session_transaction() as s:
                s["user_id"], s["user_email"], s["user_role"] = uid, f"{uid}@example.com", "seller"
            html = c.get("/seller/sourcing/reject-watch").get_data(as_text=True)
            assert ("A01381223" in html) is shown and ("A01504840" in html) is shown, uid
            assert ("우주대행" in html) is shown and (">내 쿠팡<" in html) is not shown, uid
