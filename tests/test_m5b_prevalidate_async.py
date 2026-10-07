"""M5 후속(오너 2026-10-07, 실사용 1호) — 폰 사전검증 「응답을 읽지 못했어요 (HTTP 502)」 → 비동기 + 마켓별 부분 결과.

- `async: true` → 즉시 202 + job_id. 마켓마다 따로·동시에, 마켓당 시간 상한. 도착하는 대로 job에 쌓인다.
- 시간 초과·예외 마켓은 「검증 못 함」(transport) — 막힘이 아니다. 나머지 마켓 결과는 그대로.
- 동기 경로(데스크톱)는 예전 동작 + 25초 상한(워커 120초에 죽어 502가 되는 대신 시간 초과 JSON).
- 잡 스레드도 요청 세션을 본다 — 공개 가입자의 비동기 검증이 오너 서버 자격(Z6)을 보면 안 된다.
"""
from __future__ import annotations

import os
import time

import pytest

SIX = ["coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos", "shopify", "woocommerce"]


class _R:
    def __init__(self, m, ok=True, **kw):
        self.market, self.ok = m, ok
        self.error_code = kw.get("error_code", "")
        self.message = kw.get("message", "통과")
        self.hint = ""
        self.reach_ok = self.reach_ms = None
        self.reach_detail = ""
        self.details = []
        self.action_url = ""
        self.hold = kw.get("hold", False)
        self.fixes = kw.get("fixes", [])


class _Disp:
    def __init__(self, slow=(), boom=(), hold=()):
        self.slow, self.boom, self.hold = set(slow), set(boom), set(hold)
        self.calls = []

    def prevalidate(self, product, markets):
        self.calls.append(list(markets))
        out = []
        for m in markets:
            if m in self.slow:
                time.sleep(3)
            if m in self.boom:
                raise RuntimeError("마켓 API 연결 끊김")
            if m in self.hold:
                out.append(_R(m, ok=False, hold=True, fixes=["ship_ratio"], message="배송비 비율 초과"))
            else:
                out.append(_R(m))
        return out


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_PV_MARKET_TIMEOUT_SEC", 0.8)
    monkeypatch.setattr(V, "_PV_JOB_DEADLINE_SEC", 5.0)
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_account_codes_forbidden", lambda m: None)


def _client(uid="m5b-seller", **extra):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, **extra)
    return c


def _run(c, markets, disp, monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: disp)
    r = c.post("/seller/collect/prevalidate", json={"product": {"title": "슬립 원피스", "price": "328"},
                                                     "markets": markets, "async": True})
    assert r.status_code == 202, r.get_json()
    d = r.get_json()
    assert d["ok"] and d["job_id"] and d["poll"].endswith(d["job_id"]) and d["poll_sec"] == 3
    seen = []
    for _ in range(80):
        j = c.get(d["poll"]).get_json()
        seen.append(len(j["results"]))
        if j["state"] == "done":
            return j, seen
        time.sleep(0.1)
    pytest.fail(f"잡이 안 끝남: {j}")


def test_one_market_times_out_others_arrive(monkeypatch):
    disp = _Disp(slow=["smartstore:gocosmos"])
    j, _ = _run(_client(), SIX, disp, monkeypatch)
    by = {r["market"]: r for r in j["results"]}
    assert set(by) == set(SIX) and j["pending"] == []
    assert by["smartstore:gocosmos"]["transport"] == "timeout" and "검증 못 함" in by["smartstore:gocosmos"]["message"]
    assert by["smartstore:gocosmos"]["ok"] is False and by["smartstore:gocosmos"]["hold"] is False
    assert all(by[m]["ok"] for m in SIX if m != "smartstore:gocosmos")         # 나머지 5곳 통과 그대로
    assert sorted(map(tuple, disp.calls)) == sorted((m,) for m in SIX)         # 마켓마다 따로 불렀다


def test_all_time_out_then_nothing_registrable(monkeypatch):
    j, _ = _run(_client(), ["coupang:woojoo", "shopify"], _Disp(slow=["coupang:woojoo", "shopify"]), monkeypatch)
    assert [r["transport"] for r in j["results"]] == ["timeout", "timeout"]
    assert not any(r["ok"] for r in j["results"])


def test_exception_in_one_market_is_transport_error(monkeypatch):
    j, _ = _run(_client(), ["coupang:woojoo", "shopify"], _Disp(boom=["shopify"]), monkeypatch)
    by = {r["market"]: r for r in j["results"]}
    assert by["coupang:woojoo"]["ok"] and by["shopify"]["transport"] == "error"
    assert "RuntimeError" in by["shopify"]["message"]


def test_hold_is_not_transport(monkeypatch):
    j, _ = _run(_client(), ["coupang:woojoo", "shopify"], _Disp(hold=["coupang:woojoo"]), monkeypatch)
    by = {r["market"]: r for r in j["results"]}
    assert by["coupang:woojoo"]["hold"] and by["coupang:woojoo"]["fixes"] == ["ship_ratio"]
    assert "transport" not in by["coupang:woojoo"]


def test_job_is_owner_scoped(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _Disp())
    d = _client("owner-a").post("/seller/collect/prevalidate",
                                json={"product": {"title": "x"}, "markets": ["shopify"], "async": True}).get_json()
    assert _client("someone-else").get(d["poll"]).status_code == 404
    assert _client().get("/seller/collect/prevalidate/job/nope").status_code == 404


def test_stuck_job_is_closed_on_poll(monkeypatch):
    """잡 스레드가 죽었어도(배포 재시작 등) 마감이 지나면 폴링이 남은 마켓을 「검증 못 함」으로 닫는다."""
    import src.seller_console.views as V
    from src.db import image_translate_queue_pg as st
    st.state_set(V._PV_JOB_KEY + "stuck1", {"state": "running", "owner": "m5b-seller", "markets": ["shopify"],
                                            "results": {}, "started_ts": time.time() - 999})
    j = _client().get("/seller/collect/prevalidate/job/stuck1").get_json()
    assert j["state"] == "done" and j["results"][0]["transport"] == "timeout"


def test_sync_path_unchanged_but_capped(monkeypatch):
    import src.seller_console.views as V
    disp = _Disp()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: disp)
    d = _client().post("/seller/collect/prevalidate", json={"product": {"title": "x"}, "markets": ["shopify", "coupang"]}).get_json()
    assert d["ok"] and [r["market"] for r in d["results"]] == ["shopify", "coupang"] and d["all_ok"]
    assert disp.calls == [["shopify", "coupang"]]                              # 데스크톱은 예전대로 한 번에
    monkeypatch.setattr(V, "_PV_SYNC_DEADLINE_SEC", 0.5)
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _Disp(slow=["shopify"]))
    t0 = time.time()
    r = _client().post("/seller/collect/prevalidate", json={"product": {"title": "x"}, "markets": ["shopify"]})
    assert time.time() - t0 < 2.5 and r.status_code == 200
    assert r.get_json()["timeout"] is True and "초 안에 끝나지 않았어요" in r.get_json()["error"]


def test_async_job_keeps_owner_env_gate(monkeypatch):
    """Z6: 비동기 잡 스레드에서도 공개 가입자는 오너 서버 자격을 못 본다(요청 세션이 잡으로 넘어간다)."""
    import src.seller_console.views as V
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "shpss_owner_m5b")
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    seen = {}

    class _Spy(_Disp):
        def prevalidate(self, product, markets):
            seen[markets[0]] = os.environ.get("SHOPIFY_CLIENT_SECRET")
            return [_R(m) for m in markets]
    j, _ = _run(_client("stranger-m5b", user_email="stranger@example.com", user_role="seller"), ["shopify"], _Spy(), monkeypatch)
    assert seen == {"shopify": None} and j["results"][0]["ok"]
    seen.clear()
    _run(_client("mom-m5b", user_email="mom@example.com", user_role="seller"), ["shopify"], _Spy(), monkeypatch)
    assert seen == {"shopify": "shpss_owner_m5b"}                              # 가족은 그대로 오너 자격


def test_card_js_polls_and_unlocks_on_partial():
    from pathlib import Path
    h = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    for must in ("async: true", "m5-retry-market", "m5-uncheck-market", "검증 못 함", "pvPoll", "3000"):
        assert must in h, must
