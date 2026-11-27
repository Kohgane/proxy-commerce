"""오너 11-27 11:51 — 셰고가 판매 재개 「0건」(1,679줄 전부 「원본 주소 없음」) 계약.

① 원가·소싱처를 볼트 장부에서도 찾는다 — 볼트가 요약 조각을 `ops:oneshot:queue`에 덧붙이고(`relist_ledger_load`) 서버가 캐시.
   허용 칸만(상품번호·원가·통화·주소·갱신일·볼트 사유·쿠팡 판매) — 손님 정보·비밀값 칸은 버린다. 줄마다 원가 출처 표기.
   못 찾은 줄은 「원가 넣기」로 그 줄만 다시 판정(오너 입력은 장부가 덮지 않음).
② 사유별 개수를 맨 위에 · 켤 것이 0이면 왜 0인지 한 줄.
③ 뺄 줄 골라 「켤 목록으로」(오너 확인) — 도검·렌즈·금지 브랜드·볼트 반려 기록은 못 옮김 · 빈자리 넘으면 안 옮김.
④ 다시 만드는 중엔 위 목록을 「이전 목록(시각)」 · 진행 숫자가 그대로면(걸음이 돌아도) 5분 뒤 「멈췄어요」.
⑤ 호환 액세서리(「Apple Watch용 밴드」)는 금지 브랜드가 아니다 — 판매 재개와 등록 사전검증이 같은 규칙.
"""
from __future__ import annotations

import pytest

from tests.test_owner1126_relist import FakeUp, _cleanup, _env, _ours, _size  # noqa: F401


@pytest.fixture
def state(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    monkeypatch.delattr(st, "state_update", raising=False)
    return s


def _mirrors(monkeypatch, codes):
    """판매중지 줄마다 판매자 관리 코드(오라클 미러 = `CP-<sid>` 또는 하이픈 없는 `CP<sid>`)."""
    up = FakeUp([{"ch": str(30000 + i), "origin": str(40000 + i), "name": n, "price": 200000} for i, (n, _c) in enumerate(codes)],
                {"SALE": 400})
    real = up._api_request

    def api(method, path, data=None):
        res = real(method, path, data)
        if path == "/v1/products/search":
            for i, c in enumerate(res["contents"]):
                c["channelProducts"][0]["sellerManagementCode"] = codes[i][1]
        return res
    up._api_request = api
    return up


def test_ledger_rows_keep_only_allowed_fields_and_owner_cost_wins(state):
    from src.services import oneshot_ops as O
    from src.services import relist_ledger as RL
    assert "relist_ledger_load" in O.OPS and "relist_ledger_load" in O.REQUEUE_SAFE_OPS
    out = O._run({"op": "relist_ledger_load", "item_id": "chezgoga:sourcing_map:1", "store": "chezgoga", "part": 1, "parts": 1,
                  "src": "sourcing_map", "rows": [
                      {"code": "CP15000000001", "cost": "12.5", "currency": "usd", "url": "https://shop.example.jp/p/1",
                       "buyer_name": "홍길동", "phone": "010-1234-5678", "api_key": "sk-xxx", "vault_reason": "자리 바꾸기(60일 안 팔림)"},
                      {"origin_no": "40001", "cost": "3000", "currency": "JPY"},
                      {"name": "번호 없는 줄", "cost": 1, "currency": "USD"}]})
    assert out["ok"] and out["kept"] == 2 and out["dropped"] == 1
    idx = RL.index("chezgoga")
    row = idx["cd:CP-15000000001"]["볼트 소싱맵"]                                                     # 하이픈 없는 미러 코드도 같은 꼴로
    assert set(row) <= {"code", "cost", "currency", "url", "vault_reason", "src"} and row["src"] == "볼트 소싱맵"
    assert "홍길동" not in str(state) and "010-1234" not in str(state) and "sk-xxx" not in str(state)
    RL.set_owner_cost("chezgoga", "30009", "20", "USD")
    RL.load_part("chezgoga", 1, 1, "cost_pin", [{"channel_no": "30009", "cost": "99", "currency": "USD"}])
    got = RL.find(RL.index("chezgoga"), {"channel_no": "30009"})
    assert got["cost"] == 20.0 and got["src"] == "오너 입력"                                  # 오너 입력이 장부보다 먼저
    assert RL.load_part("chezgoga", 1, 1, "owner", [])["ok"] is False                     # 「오너 입력」은 화면에서만
    assert RL.load_part("nope", 1, 1, "cost_pin", [])["ok"] is False


def test_mirror_with_vault_cost_is_judged_and_labelled(state, monkeypatch):
    SR = _env(monkeypatch)
    from src.services import relist_ledger as RL
    RL.load_part("chezgoga", 1, 1, "sourcing_map", [
        {"code": "CP15000000001", "cost": "40", "currency": "USD", "url": "https://shop.example.com/a", "vault_reason": "자리 비움(1,000칸)"},
        {"code": "CP-15000000002", "cost": "500", "currency": "USD"},                  # 마진 미달 → 지금 원가로 다시 계산해도 미달
        {"code": "CP-15000000003", "vault_reason": "카테고리 오매칭 되돌림", "vault_job": "NVWINSTOP1121"}])
    RL.load_part("chezgoga", 1, 1, "coupang_mirror", [{"code": "CP-15000000001", "cp_sold": 3}])
    up = _mirrors(monkeypatch, [("가죽 카드지갑", "CP15000000001"), ("비싼 원가 램프", "CP-15000000002"),
                                ("칼 카테고리로 갔던 케이스", "CP-15000000003"), ("장부에 없는 미러", "CP-15000000004")])
    p = SR.build("chezgoga", up=up, size_of=_size)
    by = {x["channel_no"]: x for x in p["rows"]}
    a = by["30000"]
    assert a["action"] == "on" and a["cost_src"] == "볼트 소싱맵" and a["vault_reason"] == "자리 비움(1,000칸)"
    assert a["sold_cp"] == 3 and a["tier"] == 1 and a["src_url"] == "https://shop.example.com/a"     # 쿠팡 판매 결합 → ① 팔림
    assert by["30001"]["exclude"] == ["margin_low"]
    assert "vault_hard" in by["30002"]["exclude"] and "NVWINSTOP1121" in " ".join(by["30002"]["exclude_detail"])
    assert by["30003"]["exclude"] == ["mirror"] and "원가 넣기" in by["30003"]["exclude_detail"][0]
    assert p["ledger_hit"] == 2 and p["ledger"]["rows"] == 3 and p["mirrors"] == 4
    assert "볼트 소싱맵" in SR.csv_text(p)


def test_why_zero_line_names_the_biggest_gap(state, monkeypatch):
    SR = _env(monkeypatch)
    up = _mirrors(monkeypatch, [("미러 A", "CP-1"), ("미러 B", "CP15000000002"), ("미러 C", "CP-15000000003"), ("기록 없음", "")])
    p = SR.build("chezgoga", up=up, size_of=_size)
    assert p["on"] == 0
    line = SR.why_zero(p)
    assert line.startswith("4건 중 4건이 우리 기록·볼트 장부에 원가가 없어요") and "쿠팡 미러 2" in line and "원가 넣기" in line
    p2 = dict(p, on=1)
    assert SR.why_zero(p2) == ""


def test_owner_pick_moves_unlocked_rows_and_refuses_brand_and_room(state, monkeypatch):
    SR = _env(monkeypatch)
    up = _mirrors(monkeypatch, [("미러 지갑", "CP-15000000001"), ("Supreme 백팩", "CP-15000000002"), ("미러 램프", "CP-15000000003")])
    p = SR.build("chezgoga", up=up, size_of=_size)
    assert p["by_reason"]["brand"] == 1
    out = SR.owner_pick("chezgoga", ["30000", "30001"], by="owner@x")
    assert out["ok"] and out["moved"] == 1 and out["locked"][0]["channel_no"] == "30001"
    p = SR.plan("chezgoga")
    a = next(x for x in p["rows"] if x["channel_no"] == "30000")
    assert a["action"] == "on" and a["owner_ok"] and a["our_reason"] == "오너 확인" and a["owner_prev"]["exclude"] == ["mirror"]
    assert p["on"] == 1 and p["owner_ok"] == 1 and "mirror" in p["by_reason"]
    assert SR.start("chezgoga", 1, by="t", runner=lambda o: {"ok": True})["total"] == 1   # 실행 대상에 들어간다(오너 탭 그대로)
    from src.services import durable_job as DJ
    DJ.save(SR._RUN_KEY.format("chezgoga"), {"state": "finished"})
    state[SR._PLAN_KEY.format("chezgoga")]["room"] = 1
    assert SR.owner_pick("chezgoga", ["30002"])["ok"] is False                         # 빈자리 1칸 — 더 못 옮김
    back = SR.owner_unpick("chezgoga", ["30000"])
    assert back["back"] == 1 and next(x for x in SR.plan("chezgoga")["rows"] if x["channel_no"] == "30000")["exclude"] == ["mirror"]


def test_set_cost_rejudges_one_row(state, monkeypatch):
    SR = _env(monkeypatch)
    up = _mirrors(monkeypatch, [("미러 지갑", "CP-15000000001"), ("미러 램프", "CP-15000000002")])
    SR.build("chezgoga", up=up, size_of=_size)
    bad = SR.set_cost("chezgoga", "30000", "abc", "USD", up=up, size_of=_size)
    assert bad["ok"] is False and "원가" in bad["error"]
    low = SR.set_cost("chezgoga", "30001", "900", "USD", up=up, size_of=_size)
    assert low["ok"] and low["row"]["action"] == "skip" and low["row"]["exclude"] == ["margin_low"] and "마진 하한" in low["verdict"]
    ok = SR.set_cost("chezgoga", "30000", "40", "USD", "https://shop.example.com/w", up=up, size_of=_size)
    assert ok["ok"] and ok["row"]["action"] == "on" and ok["row"]["cost_src"] == "오너 입력" and ok["on"] == 1
    from src.services import relist_ledger as RL
    assert "오너 입력" in RL.index("chezgoga")["ch:30000"]                               # 다음 목록 만들기에도 쓰인다
    assert all(m != "PUT" for m, _p, _d in up.calls)                                       # 네이버에는 읽기만


def test_edits_refused_while_build_runs(state, monkeypatch):
    SR = _env(monkeypatch)
    from src.services import durable_job as DJ
    DJ.save(SR._BUILD_KEY.format("chezgoga"), {"state": "running", "kind": "relist_build"})
    assert "만드는 중" in SR.owner_pick("chezgoga", ["1"])["error"]
    assert "만드는 중" in SR.set_cost("chezgoga", "1", "1", "USD")["error"]


def test_stall_counts_progress_not_steps(state, monkeypatch):
    """④ 걸음이 돌아도 진행 숫자가 그대로면 진전이 아니다 — `progress_at`이 안 바뀌어 5분 뒤 「멈췄어요」."""
    from src.services import durable_job as DJ
    calls = {"n": 0}

    def step(key, rec, deadline):
        calls["n"] += 1
        if calls["n"] >= 3:
            rec["state"] = "done"
        return rec                                                 # 진행 칸 그대로
    DJ.register("t_stuck", step)
    DJ.save("t:stuck", {"state": "running", "kind": "t_stuck", "progress": {"n": 0, "label": "판매중지 읽는 중 0"},
                        "progress_at": "2026-11-27T00:00:00+00:00", "heartbeat_at": "2026-11-27T00:00:00+00:00"})
    DJ.drive("t:stuck", budget=0)
    rec = DJ.get("t:stuck")
    assert rec["progress_at"] == "2026-11-27T00:00:00+00:00" and rec["heartbeat_at"] != rec["progress_at"]
    assert DJ.status("t:stuck")["stalled"] is True

    def moving(key, rec, deadline):
        rec["progress"] = {"n": int(rec["progress"]["n"]) + 100, "label": "읽는 중"}
        return rec
    DJ.register("t_move", moving)
    DJ.save("t:move", {"state": "running", "kind": "t_move", "progress": {"n": 0}, "progress_at": "2026-11-27T00:00:00+00:00"})
    DJ.drive("t:move", budget=0)
    assert DJ.status("t:move")["stalled"] is False


H = {"Accept": "text/html"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    app.config["TESTING"] = True
    return app.test_client()


def test_screen_counts_zero_line_checkboxes_cost_form_and_previous_label(state, monkeypatch, client):
    SR = _env(monkeypatch)
    up = _mirrors(monkeypatch, [("미러 지갑", "CP-15000000001"), ("Supreme 백팩", "CP-15000000002"), ("미러 램프", "CP-15000000003")])
    SR.build("chezgoga", up=up, size_of=_size)
    h = client.get("/seller/admin/smartstore-relist?store=chezgoga", headers=H).get_data(as_text=True)
    assert 'data-role="rl-why-mirror"' in h and 'data-role="rl-why-brand"' in h and 'data-role="rl-zero"' in h
    assert "3건 중 3건이 우리 기록·볼트 장부에 원가가 없어요" in h
    assert h.count('data-role="rl-pick"') == 3 and h.count("disabled title=\"금지 브랜드") == 1
    assert h.count('data-role="rl-cost"') == 2 and "고른 0건 켤 목록으로" in h and "아직 못 받았어요" in h
    assert 'data-role="rl-prev"' not in h
    f = client.get("/seller/admin/smartstore-relist?store=chezgoga&why=brand", headers=H).get_data(as_text=True)
    assert f.count('data-role="rl-skip-row"') == 1 and "Supreme" in f
    from src.services import durable_job as DJ
    DJ.save(SR._BUILD_KEY.format("chezgoga"), {"state": "running", "kind": "relist_build", "progress": {"n": 0, "label": "판매중지 읽는 중 0"},
                                              "heartbeat_at": "2026-11-27T00:00:00+00:00"})
    h2 = client.get("/seller/admin/smartstore-relist?store=chezgoga", headers=H).get_data(as_text=True)
    assert 'data-role="rl-prev"' in h2 and "이전 목록(" in h2 and "멈췄어요" in h2
    r = client.post("/seller/admin/smartstore-relist?store=chezgoga", json={"action": "pick", "channel_nos": ["30000"]})
    assert r.status_code == 409 and "만드는 중" in r.get_json()["error"]
    DJ.save(SR._BUILD_KEY.format("chezgoga"), {"state": "done"})
    r = client.post("/seller/admin/smartstore-relist?store=chezgoga", json={"action": "pick", "channel_nos": ["30000"]})
    assert r.status_code == 200 and r.get_json()["moved"] == 1


@pytest.mark.parametrize("title,hit", [
    ("빕준 Apple Watch용 실리콘 스포츠 밴드 41mm", False),
    ("빕준 갤럭시워치 호환 Samsung 메탈 스트랩", False),
    ("빕준 Garmin Forerunner 265 band 교체 스트랩", False),
    ("Apple 정품 MagSafe 충전기", True),
    ("Supreme 백팩", True),
    # 11-27 운영 표본(diag relist:chezgoga) — 지금 규칙으로 남았던 오탐 4 · 진짜 브랜드 상품은 그대로
    ("빕준 애플워치 밴드 스트랩 가죽 Airfoil Leather Band –Samsung Watch Ultra 해외직구 정품", False),
    ("충전기 트웰브사우스 TWELVE SOUTH ButterFly 2-in-1 MagSafe Charger 애플 액세서리 해외직구", False),
    ("Samsung Galaxy Watch 7 정품 스트랩 포함", True),
])
def test_registration_scan_uses_same_compat_rule(monkeypatch, title, hit):
    from src.services import risk_gate as RG
    monkeypatch.setattr(RG, "_blacklist", lambda: ["apple", "애플", "samsung", "garmin", "supreme"])
    monkeypatch.setattr(RG, "allowlist", lambda: set())
    got = RG.scan({"title_ko": title, "coupang_name": title})
    assert any(h.get("key") == "blacklist" or str(h.get("label") or "").startswith("브랜드 블랙") for h in got["hits"]) is hit


def _push():
    import importlib.util
    spec = importlib.util.spec_from_file_location("relist_ledger_push", "ops/oracle_a1/relist_ledger_push.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_vault_push_only_appends_queue_and_keeps_allowed_fields():
    """볼트 오라클 작업(RELISTPUSH)의 쓰기는 `ops:oneshot:queue` 덧붙이기 하나 · 싣는 칸은 허용 칸만 · 400줄씩."""
    m = _push()
    doc = {"at": "2026-11-27T12:00:00+09:00", "read": 900, "parts": {
        "sourcing_map": [{"code": "CP-1500000000%d" % (i % 10), "cost": 10, "currency": "USD", "buyer": "홍길동", "phone": "010-1"} for i in range(850)],
        "vault_log": [{"origin_no": "40001", "vault_reason": "자리 비움(1,000칸 한도)"}], "bad src!": [{"code": "x"}]}}
    cs = m.chunks(doc)
    assert [(c[0], c[1], c[2], len(c[3])) for c in cs] == [("sourcing_map", 1, 3, 400), ("sourcing_map", 2, 3, 400),
                                                           ("sourcing_map", 3, 3, 50), ("vault_log", 1, 1, 1)]
    assert all(set(r) <= set(m.KEEP) for c in cs for r in c[3]) and "홍길동" not in str(cs)
    sql = m.queue_sql("chezgoga", "2026-11-27T12:00:00", cs[-1], True)
    up = sql.upper()
    assert up.count("UPDATE APP_STATE") == 1 and "'ops:oneshot:queue'" in sql and '"rebuild": true' in sql
    for bad in ("DELETE", "DROP", "TRUNCATE", "ALTER", "COLLECT_HISTORY", "ORDERS", "USER_TOKENS", "MARKET_LINKS"):
        assert bad not in up, bad
    assert m.READ.startswith("BEGIN READ ONLY;") and "UPDATE" not in m.READ.upper()


def test_last_part_rebuilds_list(state, monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import smartstore_relist as SR
    seen = []
    monkeypatch.setattr(SR, "start_build", lambda store, by_uid="": (seen.append(store), {"ok": True, "started": True})[1])
    out = O._run({"op": "relist_ledger_load", "item_id": "chezgoga:cost_pin:1:t", "store": "chezgoga", "part": 1, "parts": 1,
                  "src": "cost_pin", "rows": [{"code": "CP-15000000001", "cost": 30, "currency": "USD"}], "rebuild": True})
    assert out["ok"] and seen == ["chezgoga"] and out["rebuild"]["started"]


@pytest.mark.parametrize("title,word,hit", [
    ("버켄스탁 보스턴 슈퍼그립 클로그 프로페셔널 논슬립 정품", "보스", False),
    ("보스 QuietComfort 울트라 헤드폰", "보스", True),
    ("[해외직구] Mungo & Maud 멍고앤마우드 Ping Pong Ball Cat Toy 영국 럭셔리 애견용품", "ping", False),
    ("PING G430 드라이버 헤드커버", "ping", True),
    ("[해외직구] 포터 PORTER HELLO KITTY x PORTER SACKPACK 386-26903", "hello kitty", True),
])
def test_brand_word_inside_other_word_is_not_brand(title, word, hit):
    """11-27 운영 표본: 「보스턴」·「Ping Pong」은 금지 브랜드 아님(판매 재개·등록 같은 함수) · 진짜 브랜드 상품은 그대로."""
    from src.services import risk_gate as RG
    assert bool(RG.blacklist_words(title, [word])) is hit
