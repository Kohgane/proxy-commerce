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
    try:
        assert SR.start("chezgoga", 1, by="t", runner=lambda o: {"ok": True})["total"] == 1   # 실행 대상에 들어간다(오너 탭 그대로)
    finally:
        SR._RUNNER_OVERRIDE.pop("chezgoga", None)                                          # 다른 시험에 흉내 실행기가 남지 않게
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
    _t = RG.tokens()
    monkeypatch.setattr(RG, "tokens", lambda: {**_t, "product_level": []})          # 호환 규칙만 본다(상품 단위 브랜드 목록과 별개)
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
    monkeypatch.setattr(SR, "start_build", lambda store, by_uid="": (seen.append((store, by_uid)), {"ok": True, "started": True})[1])
    from src.auth import identity as _idn
    monkeypatch.setattr(_idn, "OWNER_USER_ID", "owner-uid-1")
    out = O._run({"op": "relist_ledger_load", "item_id": "chezgoga:cost_pin:1:t", "store": "chezgoga", "part": 1, "parts": 1,
                  "src": "cost_pin", "rows": [{"code": "CP-15000000001", "cost": 30, "currency": "USD"}], "rebuild": True})
    assert out["ok"] and seen == [("chezgoga", "owner-uid-1")] and out["rebuild"]["started"]      # 끝나면 오너에게 푸시


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


@pytest.mark.parametrize("text,iid", [
    ("var url = 'https://item.taobao.com/item.htm?ut_sk=1.x&amp;id=789012345678&amp;sourceType=item'", "789012345678"),
    ("https://m.tb.cn/h.x?tk=a&url=https%3A%2F%2Fa.m.taobao.com%2Fi654321098765.htm%3Fp%3D1", "654321098765"),
    ("location.href='https://detail.tmall.com/item.htm?spm=a&id=612345678901'", "612345678901"),
    ('{"itemId":"698765432109","title":"x"}', "698765432109"),
    ("redirect=https%3A%2F%2Fitem.taobao.com%2Fitem.htm%3Fft%3Dt%26id%3D723456789012", "723456789012"),
    ("https://e.tb.cn/h.8qaTtW938JXlfnK?tk=otdQT7DEulq", ""),
])
def test_taobao_share_page_id_forms(text, iid):
    """오너 11-27 오후 ③: e.tb.cn → m.tb.cn 본문의 상품 주소 꼴(`&amp;id=`·`%26id%3D`·`/i<번호>.htm`·`itemId`) — 「상품번호 해석 실패」 수리."""
    from src.collectors.taobao_mtop import id_in_text
    assert id_in_text(text) == iid


def test_short_link_resolves_through_relay_location_hops():
    """직결로 안 열리는 e.tb.cn → 릴레이가 돌려준 Location을 따라가 상품번호(읽기만)."""
    from src.collectors.taobao_mtop import item_id_via_relay

    class R:
        def __init__(self, status, text="", loc=""):
            self.status_code, self.text, self.headers = status, text, ({"Location": loc} if loc else {})
    hops = {"https://e.tb.cn/h.x?tk=1": R(302, loc="https://m.tb.cn/h.x?tk=1"),
            "https://m.tb.cn/h.x?tk=1": R(200, "<script>var url='https://item.taobao.com/item.htm?ut=1&amp;id=1060535477134'</script>")}
    seen = []
    iid, how = item_id_via_relay("https://e.tb.cn/h.x?tk=1", send=lambda m, u, h, j, d, t: (seen.append((m, u)), hops[u])[1])
    assert iid == "1060535477134" and "릴레이" in how and all(m == "GET" for m, _u in seen)
    iid, how = item_id_via_relay("https://e.tb.cn/h.y", send=lambda *a: R(200, "<html>로그인</html>"))
    assert iid == "" and "못 찾음" in how


def test_allowlisted_brands_pass_in_relist_and_registration(monkeypatch):
    """오너 11-27 15:18 0-1: Apotheke Fragrance · Imaginary Authors 허용 — 판매 재개·등록 사전검증 같은 목록(대소문자 무관)."""
    from src.services import risk_gate as RG
    monkeypatch.setattr(RG, "_blacklist", lambda: ["Apotheke Fragrance", "Imaginary Authors", "supreme"])
    _t = RG.tokens()
    monkeypatch.setattr(RG, "tokens", lambda: {**_t, "product_level": []})
    assert {"Apotheke Fragrance", "아포테케", "Imaginary Authors", "이매지너리오써스"} <= {a for a in RG.allowlist()}
    assert RG.active_blacklist() == ["supreme"]
    assert RG.blacklist_words("[해외직구] Apotheke Fragrance 아포테케 프래그런스 오일버너 BRASS") == []
    assert RG.blacklist_words("Supreme 백팩") == ["supreme"]
    got = RG.scan({"title_ko": "[해외직구] Imaginary Authors 이매지너리 오서스 A City On Fire 오 드 퍼퓸 50ml"})
    assert not any(h.get("key") == "blacklist" for h in got["hits"])
    from src.services import smartstore_relist as SR
    assert "Apotheke Fragrance" not in SR._rules()[1]


def test_rejected_product_blocks_that_product_only(state, monkeypatch, tmp_path):
    """오너 11-27 15:18 0-2: 반려·소명 났던 그 상품만 막는다 — 같은 브랜드 다른 상품은 통과 · 판매 재개는 「반려 이력(날짜·사유)」로 뺌(못 고름)."""
    import json
    from src.services import risk_gate as RG
    f = tmp_path / "rej.json"
    f.write_text(json.dumps({"rows": [{"brand": "Imaginary Authors", "market": "쿠팡", "date": "2026-10-02", "reason": "상표권 침해 신고",
                                       "seller_code": "CP-15000000001", "url": "https://imaginaryauthors.com/products/a-city-on-fire"}]}),
                 encoding="utf-8")
    monkeypatch.setattr(RG, "_REJ_FILE", f)
    RG._rej_cache.update(at=0.0, rows=None)
    monkeypatch.setattr(RG, "_blacklist", lambda: [])
    hit = RG.scan({"title_ko": "Imaginary Authors A City On Fire 50ml", "url": "https://imaginaryauthors.com/products/a-city-on-fire?v=1"})
    assert any(h["key"] == "rejected_product" and h["grade"] == "block" for h in hit["hits"])
    other = RG.scan({"title_ko": "Imaginary Authors Bull's Blood 50ml", "url": "https://imaginaryauthors.com/products/bulls-blood"})
    assert not any(h["key"] == "rejected_product" for h in other["hits"])
    SR = _env(monkeypatch)
    up = _mirrors(monkeypatch, [("Imaginary Authors A City On Fire", "CP15000000001"), ("Imaginary Authors Bull's Blood", "CP-15000000002")])
    p = SR.build("chezgoga", up=up, size_of=_size)
    by = {x["channel_no"]: x for x in p["rows"]}
    assert "rejected_hist" in by["30000"]["exclude"] and "2026-10-02" in " ".join(by["30000"]["exclude_detail"])
    assert "rejected_hist" not in by["30001"]["exclude"]
    assert SR.owner_pick("chezgoga", ["30000"])["locked"][0]["channel_no"] == "30000"
    RG._rej_cache.update(at=0.0, rows=None)


def test_live_source_price_wins_and_soldout_skips(state, monkeypatch):
    """오너 11-27 15:18 0-3: 소싱처 현재가(실측)가 옛 장부 원가보다 먼저 · 출처 「소싱처 실측(날짜)」 · 품절이면 사유로 뺌."""
    SR = _env(monkeypatch)
    from src.services import relist_ledger as RL
    RL.load_part("chezgoga", 1, 1, "sourcing_map", [{"code": "CP-15000000001", "cost": "400", "currency": "USD"},
                                                    {"code": "CP-15000000002", "cost": "40", "currency": "USD"}])
    RL.load_part("chezgoga", 1, 1, "source_live", [
        {"code": "CP-15000000001", "cost": "42", "currency": "USD", "updated": "2026-11-27", "src_state": "ok", "via": "shopify .js"},
        {"code": "CP-15000000002", "cost": "39", "currency": "USD", "updated": "2026-11-27", "src_state": "soldout"}])
    up = _mirrors(monkeypatch, [("지갑", "CP-15000000001"), ("램프", "CP-15000000002")])
    p = SR.build("chezgoga", up=up, size_of=_size)
    by = {x["channel_no"]: x for x in p["rows"]}
    assert by["30000"]["cost"] == 42.0 and by["30000"]["cost_src"] == "소싱처 실측(11-27)" and by["30000"]["action"] == "on"
    assert "src_soldout" in by["30001"]["exclude"] and "품절" in " ".join(by["30001"]["exclude_detail"])


def test_src_live_job_only_appends_queue_and_reads_shopify_js(monkeypatch):
    """SRCLIVE1127(오라클): 쓰기는 큐 덧붙이기 하나 · Shopify `.js`(가격 센트·재고)+`/cart.js`(통화) · 아마존은 실측 못 함(지어내지 않음)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("src_live_1127", "ops/oracle_a1/src_live_1127.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    up = m.SQL.upper()
    assert up.count("UPDATE APP_STATE") == 1 and "'ops:oneshot:queue'" in m.SQL
    for bad in ("DELETE", "DROP", "TRUNCATE", "ALTER", "COLLECT_HISTORY", "ORDERS"):
        assert bad not in up

    class R:
        def __init__(self, status, data=None, ctype="application/json"):
            self.status_code, self._d, self.headers, self.ok, self.text = status, data, {"Content-Type": ctype}, status < 400, ""

        def json(self):
            return self._d
    pages = {"https://shop.example.com/products/a.js": R(200, {"variants": [{"price": 4200, "available": True}, {"price": 3900, "available": False}]}),
             "https://shop.example.com/cart.js": R(200, {"currency": "USD"}),
             "https://shop.example.com/products/gone.js": R(404)}
    monkeypatch.setattr(m.S, "get", lambda u, timeout=20: pages[u])
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    monkeypatch.setattr(m, "_pace", lambda host, gap=0.8: None)
    assert m.read("https://shop.example.com/products/a?variant=1") == {"cost": 42.0, "currency": "USD", "state": "ok", "via": "shopify .js"}
    assert m.read("https://shop.example.com/products/gone")["state"] == "gone"
    assert m.read("https://www.amazon.com/dp/B0X")["state"] == "unknown"


def test_product_level_brands_leave_blacklist_but_their_rejected_products_stay_blocked(monkeypatch):
    """오너 11-27 15:18 0-2: 근거가 특정 상품이면 브랜드 줄을 빼고 그 상품만 — 브랜드 단위 근거(CASETiFY 등)는 그대로."""
    from src.services import risk_gate as RG
    RG._rej_cache.update(at=0.0, rows=None)
    monkeypatch.setattr(RG, "_blacklist", lambda: ["Patagonia", "Nike", "CASETiFY", "Peter Millar"])
    assert RG.active_blacklist() == ["CASETiFY", "Peter Millar"]
    assert RG.blacklist_words("Patagonia Nano Puff Jacket") == []
    assert RG.blacklist_words("CASETiFY 아이폰 케이스") == ["CASETiFY"]
    hit = RG.scan({"title_ko": "Patagonia Better Sweater", "uploaded": [{"market": "coupang:gogane", "product_id": "16302192201"}]})
    assert any(h["key"] == "rejected_product" for h in hit["hits"])                    # 반려 났던 그 상품은 막힘
    other = RG.scan({"title_ko": "Patagonia Nano Puff", "uploaded": [{"market": "coupang:gogane", "product_id": "16399999999"}]})
    assert not any(h["key"] in ("rejected_product", "blacklist") for h in other["hits"])   # 같은 브랜드 다른 상품은 통과


def test_name_only_cost_does_not_turn_on_but_owner_can_pick(state, monkeypatch):
    """오너 11-27 15:18 0-3: 이름만으로 맞춘 원가는 「원가 이름 일치 — 확인 필요」 — 저절로 켜지 않고, 오너가 골라 켤 수 있다."""
    SR = _env(monkeypatch)
    from src.services import relist_ledger as RL
    RL.load_part("chezgoga", 1, 1, "sourcing_map_name", [{"code": "CP-15000000001", "cost": "40", "currency": "USD"}])
    RL.load_part("chezgoga", 1, 1, "sourcing_map", [{"code": "CP-15000000002", "cost": "40", "currency": "USD"}])
    up = _mirrors(monkeypatch, [("이름으로 찾은 지갑", "CP-15000000001"), ("품번으로 찾은 지갑", "CP-15000000002")])
    p = SR.build("chezgoga", up=up, size_of=_size)
    by = {x["channel_no"]: x for x in p["rows"]}
    assert by["30000"]["exclude"] == ["cost_name_only"] and "이름으로 찾음" in by["30000"]["exclude_detail"][0]
    assert by["30001"]["action"] == "on"
    assert SR.owner_pick("chezgoga", ["30000"])["moved"] == 1                               # 잠금 아님 — 확인하고 켤 수 있다


def test_brand_search_job_only_appends_queue_and_needs_real_overlap(monkeypatch):
    """BRANDSEARCH1127(오라클): 공식몰 이름 검색 — 쓰기는 큐 덧붙이기 하나 · 가게 상품 제목의 70% 이상이 우리 이름에(겹친 낱말 3개+) · 결과는 「이름 일치(확인 필요)」."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("brand_search_1127", "ops/oracle_a1/brand_search_1127.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    up = m.SQL.upper()
    assert up.count("UPDATE APP_STATE") == 1 and "'ops:oneshot:queue'" in m.SQL and "DELETE" not in up

    class R:
        def __init__(self, data, status=200):
            self.status_code, self._d, self.ok, self.headers = status, data, status < 400, {}

        def json(self):
            return self._d
    sugg = {"resources": {"results": {"products": [{"title": "Red, White & Blue Cotton Dog & Cat Harness", "url": "/products/rwb-harness?x=1"},
                                                    {"title": "Navy Waxed Canvas Leash", "url": "/products/leash"}]}}}
    pages = {"https://foundmyanimal.com/products/rwb-harness.js": R({"variants": [{"price": 6800, "available": True}]}),
             "https://foundmyanimal.com/cart.js": R({"currency": "USD"})}
    monkeypatch.setattr(m, "_get", lambda u, timeout=20: sugg_r if "suggest.json" in u else pages[u])
    sugg_r = R(sugg)
    got, why = m.search("foundmyanimal.com", "[해외직구] Found My Animal 파운드마이애니멀 Red, White &amp; Blue Cotton Dog &amp; Cat Harness – Adjustable")
    assert why == "" and got["cost"] == 68.0 and got["currency"] == "USD" and got["url"].endswith("/products/rwb-harness")
    sugg_r = R({"resources": {"results": {"products": [{"title": "Completely Different Bowl", "url": "/products/bowl"}]}}})
    got, why = m.search("foundmyanimal.com", "Found My Animal Red White Blue Harness")
    assert got is None and why == "비슷한 상품 없음"                                          # 틀린 상품의 원가를 붙이지 않는다
    from src.services import relist_ledger as RL
    assert RL.SRC_KO["name_match"] == "이름 일치(확인 필요)"


def test_src_live2_reads_whole_shop_catalog_checkpoints_and_only_appends_queue(monkeypatch, tmp_path):
    """SRCLIVE2(오라클 · 1판이 기록 0줄로 끝나 결과를 잃은 뒤): 쓰기는 큐 덧붙이기 하나 · Shopify는 가게 전체 `products.json`
    (소수 문자열 가격·available)로 핸들 맞춤 · 목록에 없는 것만 `.js`(404=내려감) · 아마존은 실측 못 함 · 가게마다 중간 저장 →
    다시 띄우면 오늘 읽은 줄은 다시 안 읽음 · `--dry`는 큐를 안 건드림."""
    import importlib.util
    import json as _j
    spec = importlib.util.spec_from_file_location("src_live2_1127", "ops/oracle_a1/src_live2_1127.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    up = m.SQL.upper()
    assert up.count("UPDATE APP_STATE") == 1 and "'ops:oneshot:queue'" in m.SQL
    for bad in ("DELETE", "DROP", "TRUNCATE", "ALTER", "COLLECT_HISTORY", "ORDERS"):
        assert bad not in up

    class R:
        def __init__(self, status, data=None, ctype="application/json", text=""):
            self.status_code, self._d, self.headers, self.ok, self.text = status, data, {"Content-Type": ctype}, status < 400, text

        def json(self):
            return self._d
    calls = []

    def fake(url, timeout=25):
        calls.append(url)
        if "products.json" in url:
            return R(200, {"products": [{"handle": "Dog-Leash", "variants": [{"price": "38.25", "available": True},
                                                                          {"price": "30.00", "available": False}]}]}
                     if "page=1" in url else {"products": []})
        if url.endswith("/cart.js"):
            return R(200, {"currency": "USD"})                            # 11-28: cart.js 통화는 믿지 않는다 — 상품 페이지 JSON-LD로 확인
        if url.endswith("/products/Dog-Leash"):
            return R(200, None, "text/html", '<script type="application/ld+json">{"offers":{"price":"38.25","priceCurrency":"EUR"}}</script>')
        if url.endswith("missing.js"):
            return R(404)
        return R(200, None, "text/html", '<script type="application/ld+json">{"offers":{"price":"12.5","priceCurrency":"usd",'
                                          '"availability":"https://schema.org/OutOfStock"}}</script>')
    monkeypatch.setattr(m, "_get", fake)
    (tmp_path / "vault" / "srv_snap" / "apply_out").mkdir(parents=True)
    (tmp_path / "vault" / "srv_snap" / "apply_out" / "relistledger_data_chezgoga.txt").write_text(_j.dumps({"parts": {"sourcing_map": [
        {"channel_no": "1", "url": "https://x.de/products/dog-leash?variant=9"},
        {"channel_no": "2", "url": "https://x.de/products/missing"},
        {"channel_no": "3", "url": "https://www.amazon.com/dp/B0X"},
        {"channel_no": "4", "url": "https://y.com/item/1"}]}}))
    monkeypatch.setenv("KG_HOME", str(tmp_path))
    pushed = []
    monkeypatch.setattr(m, "psql", lambda sql: pushed.append(sql) or "")
    assert m.main(["chezgoga", "--dry"]) == 0 and pushed == []
    rows = _j.loads((tmp_path / "ora_state" / "srclive2_chezgoga.json").read_text())["rows"]
    assert rows["1"] == {"cost": 38.25, "currency": "EUR", "state": "ok", "via": "shopify products.json(시장 가게 기본)"}
    assert rows["2"]["state"] == "gone" and rows["3"]["state"] == "unknown" and rows["4"]["state"] == "soldout"
    assert not any("dog-leash.js" in u for u in calls)                 # 목록에 있으면 상품마다 안 읽음
    n = len(calls)
    assert m.main(["chezgoga"]) == 0 and len(calls) == n               # 이어쓰기 — 오늘 읽은 줄은 다시 안 읽음
    assert len(pushed) == 1 and "relist_ledger_load" in pushed[0] and '"src": "source_live"' in pushed[0] and '"rebuild": true' in pushed[0]
    assert "B0X" not in pushed[0]                                      # 아마존(실측 못 함)은 넣지 않음


def test_src_live2_stops_hammering_blocked_ip_and_merges_other_ip_results(monkeypatch, tmp_path):
    """11-27 23:50 실측: 오라클 IP가 Shopify에 막혀 첫 가게부터 429만 26번 → 2판은 가게 목록이 429로 끝까지 막히면 상품마다 다시 두드리지 않고,
    두 곳째부터는 남은 Shopify 가게를 건너뛴다(429로 못 읽은 줄은 다음 실행이 다시 읽음). 블루호스트(`--bh`)는 DB에 안 쓰고 볼트 파일에만,
    오라클(`--from-file`)이 그 결과를 합쳐 넣는다."""
    import importlib.util
    import json as _j

    def load():
        spec = importlib.util.spec_from_file_location("src_live2_1127", "ops/oracle_a1/src_live2_1127.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        monkeypatch.setattr(m.time, "sleep", lambda s: None)
        return m

    class R:
        def __init__(self, status, data=None, ctype="application/json"):
            self.status_code, self._d, self.headers, self.ok = status, data, {"Content-Type": ctype}, status < 400
            self.text = data if isinstance(data, str) else ""

        def json(self):
            return self._d
    (tmp_path / "vault" / "srv_snap" / "apply_out").mkdir(parents=True)
    (tmp_path / "vault" / "srv_snap" / "apply_out" / "relistledger_data_chezgoga.txt").write_text(_j.dumps({"parts": {"sourcing_map": [
        {"channel_no": str(i), "url": f"https://s{i}.com/products/p{i}"} for i in range(1, 5)]}}))
    monkeypatch.setenv("KG_HOME", str(tmp_path))
    m = load()
    calls = []
    monkeypatch.setattr(m.S, "get", lambda u, timeout=25, headers=None: calls.append(u) or R(429), raising=False)
    pushed = []
    monkeypatch.setattr(m, "psql", lambda sql: pushed.append(sql) or "")
    assert m.main(["chezgoga"]) == 0
    assert not any("p1.js" in u or "p2.js" in u for u in calls)          # 목록이 막히면 상품마다 안 두드림
    assert not any("s3.com" in u or "s4.com" in u for u in calls)        # 두 곳 막히면 나머지 Shopify 가게는 건너뜀
    assert pushed == [] and m.STATS["429로 포기"] == 2

    m2 = load()                                                          # 블루호스트 — 다른 IP
    monkeypatch.setattr(m2.S, "get", lambda u, timeout=25, headers=None: R(200, {"currency": "USD"}) if u.endswith("cart.js") else
                        R(200, '<script type="application/ld+json">{"offers":{"price":"9.50","priceCurrency":"USD"}}</script>', "text/html")
                        if "/products/p" in u and "products.json" not in u else
                        R(200, {"products": [{"handle": f"p{i}", "variants": [{"price": "9.50", "available": i != 2}]} for i in range(1, 5)]}),
                        raising=False)
    monkeypatch.setattr(m2, "psql", lambda sql: (_ for _ in ()).throw(AssertionError("블루호스트는 DB에 안 쓴다")))
    (tmp_path / "ora_state").rename(tmp_path / "ora_state_oracle")
    assert m2.main(["chezgoga", "--bh"]) == 0
    f = tmp_path / "vault" / "srv_snap" / "apply_out" / "srclive2_data_chezgoga.txt"
    rows = _j.loads(f.read_text())["rows"]
    assert rows["1"]["cost"] == 9.5 and rows["2"]["state"] == "soldout" and len(rows) == 4

    (tmp_path / "ora_state").rename(tmp_path / "ora_state_bh")
    (tmp_path / "ora_state_oracle").rename(tmp_path / "ora_state")
    m3 = load()
    monkeypatch.setattr(m3.S, "get", lambda u, timeout=25, headers=None: (_ for _ in ()).throw(AssertionError("합친 줄은 다시 안 읽음 " + u)), raising=False)
    pushed3 = []
    monkeypatch.setattr(m3, "psql", lambda sql: pushed3.append(sql) or "")
    assert m3.main(["chezgoga", "--from-file", str(f)]) == 0
    assert len(pushed3) == 1 and '"src": "source_live"' in pushed3[0] and '"rebuild": true' in pushed3[0] and '"cost": 9.5' in pushed3[0]


def test_src_live2_reads_each_shop_in_the_market_of_its_ledger_currency(monkeypatch, tmp_path):
    """11-28 블루호스트 실측: 쿠키 없으면 가게가 그 IP 나라 시장(EUR 등)으로 값을 보인다 → 장부 원가 통화의 시장(`localization=US` 등)으로 읽는다.
    EUR처럼 나라 하나로 못 정하면 가게 기본 · `--market none`이면 쿠키 없음 · 어느 시장으로 읽었는지 줄에 남긴다."""
    import importlib.util
    import json as _j
    spec = importlib.util.spec_from_file_location("src_live2_1127", "ops/oracle_a1/src_live2_1127.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    class R:
        def __init__(self, data, text=""):
            self.status_code, self._d, self.headers, self.ok, self.text = 200, data, {"Content-Type": "application/json"}, True, text

        def json(self):
            return self._d
    seen = {}

    def get(u, timeout=25, headers=None):
        host = u.split("/")[2]
        seen.setdefault(host, set()).add((headers or {}).get("Cookie", ""))
        if u.endswith("cart.js"):
            return R({"currency": "EUR"})                                   # cart.js는 IP 나라 통화일 수 있다 — 안 쓴다
        if u.endswith("/products/p"):                                       # 같은 쿠키의 상품 페이지가 목록 가격과 같은 통화를 말한다
            us = "US" in (headers or {}).get("Cookie", "")
            return R(None, '<script type="application/ld+json">{"offers":{"price":"39.95","priceCurrency":"%s"}}</script>' % ("USD" if us else "EUR"))
        return R({"products": [{"handle": "p", "variants": [{"price": "39.95", "available": True}]}]})
    monkeypatch.setattr(m.S, "get", get, raising=False)
    (tmp_path / "vault" / "srv_snap" / "apply_out").mkdir(parents=True)
    (tmp_path / "vault" / "srv_snap" / "apply_out" / "relistledger_data_chezgoga.txt").write_text(_j.dumps({"parts": {"sourcing_map": [
        {"channel_no": "1", "url": "https://us.example.com/products/p", "cost": 34.95, "currency": "USD"},
        {"channel_no": "2", "url": "https://eu.example.com/products/p", "cost": 30, "currency": "EUR"}]}}))
    monkeypatch.setenv("KG_HOME", str(tmp_path))
    monkeypatch.setattr(m, "psql", lambda sql: "")
    assert m.main(["chezgoga", "--dry"]) == 0
    assert seen["us.example.com"] == {"localization=US"} and seen["eu.example.com"] == {""}
    rows = _j.loads((tmp_path / "ora_state" / "srclive2_chezgoga.json").read_text())["rows"]
    assert rows["1"]["currency"] == "USD" and "시장 US" in rows["1"]["via"] and "가게 기본" in rows["2"]["via"]
    seen.clear()
    assert m.main(["chezgoga", "--dry", "--fresh", "--market", "none"]) == 0      # --fresh = 오늘 읽은 줄도 다시
    assert seen["us.example.com"] == {""}
