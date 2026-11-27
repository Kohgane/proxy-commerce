"""오너 11-27 02:07 — 「다시 가져오기 안 뜬다 · 너무 오래 걸린다」 계약.

② 셰고가 「목록 만들기」: 줄(app_state)에 세우고 걸음마다 저장 → 일꾼이 죽어도 틱이 **저장한 쪽부터** 잇는다(처음부터 다시 금지) ·
   사진 크기는 켤 후보에만(동시 2) · 5분 넘게 진전 없으면 「멈췄어요 — 이어서 하기」 · 끝나면 푸시 한 통.
③ 재시작에 끊긴 예전 기록(「running」만 남은 것)도 거부하지 않고 이어서.
① 서버가 다시 읽을 수 있는 소싱처면 카드 맨 위에 늘 「다시 가져오기」 · 목록 줄 ⋯(길게 누르기)로 같은 동작.
"""
from __future__ import annotations

import pytest

from tests.test_owner1126_relist import FakeUp, _cleanup, _env, _ours, _products, _seed, _size  # noqa: F401 — 같은 흉내·시드·정리


class _Died(BaseException):
    """일꾼이 죽는 흉내 — drive의 `except Exception`에 안 잡힌다(스레드가 통째로 사라짐)."""


@pytest.fixture
def state(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    return s


def _many(n):
    return [{"ch": str(20000 + i), "origin": "o" + str(20000 + i), "name": f"상품 {i}", "price": 200000} for i in range(n)]


def test_build_resumes_from_saved_page_after_worker_death(state, monkeypatch):
    SR = _env(monkeypatch)
    from src.services import durable_job as DJ
    from src.utils import bg_job
    for i in range(30):
        _ours(str(20000 + i))                                                             # 우리 기록 있는 30건만 켤 수 있다
    up = FakeUp(_many(350), {"SALE": 990})
    pages, died = [], {"n": 0}
    real = up._api_request

    def api(method, path, data=None):
        if path == "/v1/products/search":
            pages.append(data["page"])
            if data["page"] == 3 and not died["n"]:
                died["n"] = 1
                raise _Died()
        return real(method, path, data)
    up._api_request = api
    import src.uploaders.naver_uploader as N
    monkeypatch.setattr(N, "NaverSmartStoreUploader", lambda account=None: up)
    import src.services.coupang_image_check as CIC
    sized = []
    monkeypatch.setattr(CIC, "head_size", lambda u: (sized.append(u), {"long_side": 1200})[1])
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (fn(), (True, {}))[1])
    with pytest.raises(_Died):
        SR.start_build("chezgoga", by_uid="own")
    st = SR.build_state("chezgoga")
    assert st["state"] == "running" and st["progress"]["n"] == 200                       # 2쪽(200건)까지 저장됨
    key = SR._BUILD_KEY.format("chezgoga")
    rec = DJ.get(key)
    rec["heartbeat_at"] = rec["progress_at"] = "2026-11-26T08:00:00+00:00"                # 일꾼이 사라진 뒤 시간이 흘렀다
    DJ.save(key, rec)
    assert DJ.status(key)["stalled"] is True                                              # 화면 「멈췄어요 — 이어서 하기」
    sent = []
    import src.notifications.apns as A
    monkeypatch.setattr(A, "notify", lambda uid, t, b, p="": sent.append((uid, t, p)))
    out = DJ.tick()                                                                       # 10분 틱 — 멈춘 줄을 잇는다
    assert key in out["woke"]
    assert pages.count(1) == 1 and pages.count(2) == 1 and pages[:4] == [1, 2, 3, 3]      # 처음부터 다시 읽지 않는다
    p = SR.plan("chezgoga")
    assert p["read"] == 350 and p["room"] == 10 and p["on"] == 10
    assert len(sized) <= 10 + 2 and p["photos_checked"] <= 12                             # 사진은 켤 후보에만(전수 아님)
    assert SR.build_state("chezgoga")["state"] == "done"
    assert sent and sent[0][0] == "own" and "목록 완료 — 켤 10 · 뺄 340" in sent[0][1] and "smartstore-relist" in sent[0][2]


def test_photo_check_only_candidates_and_small_one_is_replaced(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    up = FakeUp(_products(), {"SALE": 998})                                               # 빈자리 2
    seen = []

    def size(u):
        seen.append(u)
        return _size(u)
    p = SR.build("chezgoga", up=up, size_of=size)
    assert p["on"] == 2 and len(seen) <= 4                                                # 15줄 전수가 아니라 후보만
    assert all("photos_small" not in x["exclude"] for x in p["rows"] if x["action"] == "on")


def test_old_stuck_running_record_resumes_instead_of_refusing(state, monkeypatch):
    SR = _env(monkeypatch)
    _seed()
    up = FakeUp(_products(), {"SALE": 400})
    p = SR.build("chezgoga", up=up, size_of=_size)
    import src.uploaders.naver_uploader as N
    monkeypatch.setattr(N, "NaverSmartStoreUploader", lambda account=None: up)
    targets = [x for x in p["rows"] if x["action"] == "on"]
    # 예전 스레드 실행이 2건 하고 사라진 기록(kind·하트비트 없음)
    state[SR._RUN_KEY.format("chezgoga")] = {"state": "running", "store": "chezgoga", "total": len(targets),
                                             "targets": [{"origin_no": x["origin_no"], "channel_no": x["channel_no"], "name": x["name"]} for x in targets],
                                             "done": [{"channel_no": targets[0]["channel_no"], "name": "", "ok": True, "raw": ""},
                                                      {"channel_no": targets[1]["channel_no"], "name": "", "ok": True, "raw": ""}]}
    from src.utils import bg_job
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (fn(), (True, {}))[1])
    d = SR.start("chezgoga", p["on"], "o", by_uid="own")
    assert d["ok"] and d.get("resumed")
    r = SR.run_state("chezgoga")
    assert r["state"] == "finished" and len(r["done"]) == p["on"]
    puts = [c for c in up.calls if c[0] == "PUT"]
    assert len(puts) == p["on"] - 2                                                       # 이미 한 2건은 다시 안 보냄
    assert targets[0]["origin_no"] not in " ".join(c[1] for c in puts)


def test_reenrich_batch_is_server_job_and_resumes(state, monkeypatch):
    from src.services import taobao_reenrich_batch as TB
    from src.services import durable_job as DJ
    from src.utils import bg_job
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (True, {}))                     # 스레드는 바로 죽었다(실행 안 됨)
    rows = [{"item_id": f"i{n}", "seller_id": "s", "title": f"t{n}"} for n in range(5)]
    calls = []
    assert TB.start(rows, "o", runner=lambda uid, iid: (calls.append(iid), {"state": "done"})[1], by_uid="own")["ok"]
    assert calls == [] and DJ.status(TB.KEY)["state"] == "running"
    rec = DJ.get(TB.KEY)
    rec["heartbeat_at"] = "2026-11-26T08:00:00+00:00"
    DJ.save(TB.KEY, rec)
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (fn(), (True, {}))[1])
    DJ.tick()
    st = TB.status()
    assert st["state"] == "finished" and st["ok_count"] == 5 and calls == ["i0", "i1", "i2", "i3", "i4"]
    assert "타오바오 재보강 완료 — 성공 5/5" in st["push"]["title"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


def _row(url, **ex):
    from src.seller_console import collect_history_store as S
    e = {"title_ko": "상품", "images": ["https://m.media-amazon.com/images/I/a._AC_SL1500_.jpg"]}
    e.update(ex)
    return S.append(source="share", url=url, title="x", price="1", currency="KRW", image="", seller_id="default", extra=e)


def test_card_top_refetch_always_for_server_sources(client, monkeypatch):
    amz = _row("https://www.amazon.com/dp/B0C38WV1F6")
    other = _row("https://item.rakuten.co.jp/shop/x/")
    h = client.get(f"/seller/m/item/{amz}").get_data(as_text=True)
    assert 'data-role="m5-top-refetch"' in h and 'data-kind="amazon"' in h and "다시 가져오기" in h
    assert 'data-role="m5-top-refetch"' not in client.get(f"/seller/m/item/{other}").get_data(as_text=True)
    from src.services import taobao_auto as TA
    tb = _row("https://item.taobao.com/item.htm?id=123456789")
    monkeypatch.setattr(TA, "enabled", lambda: False)
    assert 'data-role="m5-top-refetch"' not in client.get(f"/seller/m/item/{tb}").get_data(as_text=True)
    monkeypatch.setattr(TA, "enabled", lambda: True)
    kicked = []
    monkeypatch.setattr(TA, "kick", lambda uid, iid: (kicked.append(iid), True)[1])
    assert 'data-kind="taobao"' in client.get(f"/seller/m/item/{tb}").get_data(as_text=True)
    d = client.post(f"/seller/collect/{tb}/recollect", json={"mode": "queue"}).get_json()
    assert d["ok"] and d["server_refetch"] and d["kind"] == "taobao" and kicked == [tb]


def test_list_row_more_button_and_sheet(client, monkeypatch):
    amz = _row("https://www.amazon.com/dp/B0C38WV1F6")
    h = client.get("/seller/collect/history").get_data(as_text=True)
    assert f'data-role="ch-row-more" data-item="{amz}" data-kind="amazon"' in h
    assert 'data-role="ch-row-sheet"' in h and 'data-role="ch-sheet-refetch"' in h and "touchstart" in h


def test_admin_screens_say_server_runs_and_show_running_button(client, state, monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    SR = _env(monkeypatch)
    state[SR._BUILD_KEY.format("chezgoga")] = {"state": "running", "kind": "relist_build", "phase": "fetch",
                                               "heartbeat_at": "2026-11-26T08:00:00+00:00", "progress_at": "2026-11-26T08:00:00+00:00",
                                               "progress": {"n": 300, "total": 1679, "label": "판매중지 읽는 중 300/1,679"}}
    h = client.get("/seller/admin/smartstore-relist?store=chezgoga", headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "서버에서 돌아요 — 창을 닫아도 계속되고" in h and "판매중지 읽는 중 300/1,679" in h and "멈췄어요" in h
    assert 'data-role="rl-build-resume"' in h and "목록 만드는 중…" in h
    j = client.get("/seller/admin/smartstore-relist?store=chezgoga&progress=1").get_json()
    assert j["build"]["stalled"] is True and j["build"]["progress"]["n"] == 300


def test_all_long_jobs_are_durable_kinds():
    """③ 완료 조건 — 5분 넘을 수 있는 관리자·벌크 작업은 전부 durable 종류(재시작에 죽어도 틱·부팅이 잇는다)."""
    from src.services import durable_job as DJ
    for kind in ("relist_build", "relist_run", "taobao_reenrich", "bulk_collect", "ocr_census", "ncat_table"):
        assert DJ._step_for(kind) is not None, kind


def test_ocr_census_resumes_after_death(state, monkeypatch):
    from src.services import ocr_compare_diag as D
    from src.services import durable_job as DJ
    from src.services import detail_image_plan as dip, image_text_precheck as P, image_translate_tencent as tc
    from src.utils import bg_job
    pages = [("it1", "gallery", i, f"https://img/{i}.jpg") for i in range(12)]
    monkeypatch.setattr(D, "ocr_skipped_pages", lambda limit=300: pages)
    seen = []
    monkeypatch.setattr(tc, "fetch_image", lambda u: (seen.append(u), (b"x", ""))[1])
    monkeypatch.setattr(dip, "fix_url", lambda u: u)
    monkeypatch.setattr(dip, "prepare_for_tencent", lambda raw: (b"x",))
    monkeypatch.setattr(P, "han_text", lambda data: (True, "中文"))
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (True, {}))                       # 스레드는 바로 죽었다
    assert D.start_census(by_uid="own") is True and D.start_census() is False             # 이미 줄에 있음
    rec = DJ.get(D.CENSUS_JOB)
    rec.update(i=7, heartbeat_at="2026-11-26T08:00:00+00:00")                             # 7장까지 하고 죽은 기록
    rec["cnt"]["han"] = 7
    DJ.save(D.CENSUS_JOB, rec)
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (fn(), (True, {}))[1])
    DJ.tick()
    res = D.last_census()
    assert res["count"]["han"] == 12 and len(seen) == 5                                   # 남은 5장만 다시 읽음


def test_restarts_page_shows_raw_reason(client, monkeypatch):
    import src.seller_console.views as V
    from src.utils import restart_log as RL
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    monkeypatch.setattr(RL, "rows", lambda: [
        {"at": "2026-11-26T09:09:50+00:00", "kind": "exit", "reason": "워커 RSS 451MB ≥ 420MB", "pid": 611, "worker_mb": 451,
         "inst_mb": 600, "worker_limit": 420, "inst_limit": 900, "up_min": 32.5},
        {"at": "2026-11-26T09:10:02+00:00", "kind": "boot", "pid": 637, "mb": 160, "after_exit_sec": 12.0, "reason": "워커 RSS 451MB ≥ 420MB"}])
    h = client.get("/seller/admin/diag/restarts", headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "일꾼이 왜 새로 떴나" in h and "11-26 18:10:02" in h and "내린 뒤 12.0초" in h and "워커 RSS 451MB" in h
    monkeypatch.setattr(V, "_is_admin_user", lambda: False)
    assert client.get("/seller/admin/diag/restarts").status_code == 403


def test_old_thread_record_resumes_from_screen_button(client, state, monkeypatch):
    """17:38에 1/26에서 멈춘 예전 스레드 기록(종류·목록 없음) — 화면 「이어서 하기」가 끝낸 1건 뒤부터 잇는다."""
    import src.seller_console.views as V
    from src.services import taobao_reenrich_batch as TB
    from src.utils import bg_job
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    state[TB.KEY] = {"state": "running", "total": 3, "rows": [{"item_id": f"i{n}", "seller_id": "s", "title": ""} for n in range(3)],
                     "done": [{"item_id": "i0", "title": "", "state": "done", "ok": True, "reason": ""}]}
    calls = []
    TB._RUNNER_OVERRIDE["run"] = lambda uid, iid: (calls.append(iid), {"state": "done"})[1]
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (fn(), (True, {}))[1])
    try:
        d = client.post("/seller/admin/taobao-reenrich", json={"resume": True}).get_json()
    finally:
        TB._RUNNER_OVERRIDE.pop("run", None)
    assert d["ok"] and calls == ["i1", "i2"] and TB.status()["state"] == "finished" and TB.status()["ok_count"] == 3


def test_tick_adopts_legacy_stuck_record(state, monkeypatch):
    from src.services import durable_job as DJ
    from src.services import taobao_reenrich_batch as TB
    from src.utils import bg_job
    state[TB.KEY] = {"state": "running", "total": 2, "rows": [{"item_id": "a", "seller_id": "s", "title": ""}, {"item_id": "b", "seller_id": "s", "title": ""}],
                     "done": [{"item_id": "a", "title": "", "state": "done", "ok": True, "reason": ""}]}
    TB._RUNNER_OVERRIDE["run"] = lambda uid, iid: {"state": "done"}
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (fn(), (True, {}))[1])
    try:
        out = DJ.tick()
    finally:
        TB._RUNNER_OVERRIDE.pop("run", None)
    assert TB.KEY in out["woke"] and TB.status()["state"] == "finished" and len(TB.status()["done"]) == 2


def test_mirror_products_say_coupang_ledger_not_no_source(state, monkeypatch):
    """⑤ 표본 검수: 셰고가 1,679건 전부 「원본 주소 없음」 — 대부분 오라클 미러(판매자 코드 `CP-<쿠팡번호>`)였다."""
    SR = _env(monkeypatch)
    up = FakeUp(_many(3), {"SALE": 400})
    real = up._api_request

    def api(method, path, data=None):
        res = real(method, path, data)
        if path == "/v1/products/search":
            for c in res["contents"]:
                if c["originProductNo"] != "o20002":
                    c["channelProducts"][0]["sellerManagementCode"] = "CP-1500" + c["originProductNo"][-1]
        return res
    up._api_request = api
    p = SR.build("chezgoga", up=up, size_of=_size)
    by = {x["channel_no"]: x for x in p["rows"]}
    assert by["20000"]["exclude"] == ["mirror"] and "CP-15000 미러" in by["20000"]["exclude_detail"][0]
    assert by["20002"]["exclude"] == ["no_source"]
    assert p["mirrors"] == 2 and p["ours"] == 0 and p["by_reason"] == {"mirror": 2, "no_source": 1}
