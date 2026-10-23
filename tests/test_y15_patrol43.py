"""Y15 순찰 43(오너 2026-10-23) — 틱 공백 30분 텔레그램(서버 타이머·인스턴스 둘이어도 한 번) · /health/deep instance · 등록 파이프 공유 전용."""
from datetime import datetime, timedelta, timezone


def _status(age, last="2026-10-23T04:00:34+00:00"):
    return lambda now=None: {"seen": True, "age_min": age, "last_at": last}


def test_gap_alert_once_per_gap_even_with_two_instances(monkeypatch):
    from src.services import tick_watch as TW
    taken, sent = set(), []

    def take(key, cap):                                          # app_state 원자적 상한 증가와 같은 모양
        if key in taken:
            return False, 1
        taken.add(key)
        return True, 1

    send = lambda msg, urgency: sent.append((msg, urgency)) or True
    assert TW.check_gap(status_fn=_status(29), take_fn=take, send_fn=send)["alert"] is False   # 30분 안 = 조용
    a = TW.check_gap(status_fn=_status(31), take_fn=take, send_fn=send)                        # 인스턴스 1
    b = TW.check_gap(status_fn=_status(36), take_fn=take, send_fn=send)                        # 인스턴스 2 · 5분 뒤
    assert a["alert"] and not b["alert"] and b["why"] == "이 공백은 이미 알림"
    assert sent == [("틱 31분 공백 — 도메인/cron 확인 (마지막 틱 13:00 KST)", "warning")]
    c = TW.check_gap(status_fn=_status(31, "2026-10-23T09:00:00+00:00"), take_fn=take, send_fn=send)
    assert c["alert"] and len(sent) == 2                                                       # 다음 공백은 또 알린다
    none = TW.check_gap(status_fn=lambda now=None: {"seen": False}, take_fn=take, send_fn=send)
    assert none["alert"] is False and len(sent) == 2                                           # 기록 없음 = 단정 안 함


def test_gap_watch_thread_is_off_in_tests_and_on_by_default(monkeypatch):
    from src.services import tick_watch as TW
    assert TW.start_gap_watch() is False                         # conftest TICK_GAP_WATCH=0
    monkeypatch.setenv("TICK_GAP_WATCH", "1")
    monkeypatch.setattr(TW, "_GAP_THREAD", {"t": None})
    assert TW.start_gap_watch(interval_sec=3600) is True and TW._GAP_THREAD["t"].daemon
    assert TW.start_gap_watch(interval_sec=3600) is False        # 두 번 띄우지 않는다


def test_health_deep_says_which_instance_answered(monkeypatch):
    from src.order_webhook import app
    monkeypatch.setenv("RENDER_INSTANCE_ID", "srv-test-abc12")
    js = app.test_client().get("/health/deep").get_json()
    inst = js["instance"]
    assert inst["id"] == "srv-test-abc12" and inst["id_source"] == "RENDER_INSTANCE_ID"
    started = datetime.fromisoformat(inst["started_at"])
    assert started <= datetime.now(timezone.utc) + timedelta(seconds=1) and isinstance(inst["pid"], int)
    monkeypatch.delenv("RENDER_INSTANCE_ID")
    assert app.test_client().get("/health/deep").get_json()["instance"]["id_source"] == "hostname"


def test_register_pipe_is_shared_only_with_korean_403():
    from src.auth.identity import OWNER_USER_ID
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"], s["user_email"], s["user_role"] = "u-plain", "plain@example.com", "seller"
        r = c.get("/seller/sourcing/register-pipe")
        assert r.status_code == 403 and "이 화면은 열 수 없어요" in r.get_data(as_text=True)
        r = c.post("/seller/sourcing/register-pipe/register", data={"urls": "https://x/1"})
        assert r.status_code == 403 and r.get_json()["error"] == "이 계정에서는 볼 수 없는 화면이에요."
        assert 'href="/seller/sourcing/register-pipe"' not in c.get("/seller/sourcing/reject-watch").get_data(as_text=True)
        with c.session_transaction() as s:
            s["user_id"], s["user_email"] = OWNER_USER_ID, "owner@example.com"
        assert c.get("/seller/sourcing/register-pipe").status_code == 200
